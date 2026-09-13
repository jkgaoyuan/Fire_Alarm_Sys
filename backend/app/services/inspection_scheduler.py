"""
巡检定时调度器（3.6 B-2 / B-3，3.6 FR-033 / FR-035）
====================================================

技术选型：FastAPI lifespan + asyncio.create_task()，暂不引入 Celery
（DEC-043 / PRD v2.0 §2.2）。

两个后台循环：
1. **每日 00:05（业务时区）** 为所有启用中的计划生成当日巡检任务（FR-033）
2. **每小时** 扫描并把逾期未完成的任务标记为漏检（FR-035）

结构参照 `app/tasks/offline_monitor.py`：模块级函数 + 一次性入口 + 配置开关 +
复用全局 `AsyncSessionLocal`；`main.py` lifespan 负责 start/stop。

**可测性是怎么切的**（while True + sleep 的循环没法在单测里跑）：

- `next_run_at()`   —— 纯函数，直接断言边界，不需要任何 mock
- `generate_once()` —— 一次性入口，逻辑主体在
  `inspection_service.generate_daily_tasks(db, date)`；**测试直接调后者**，
  注入测试会话，完全不碰本模块的循环
- `_loop()` / `start()` / `stop()` —— 薄编排，与 offline_monitor 同构

时区：容器默认 UTC，而 PRD 要求 UTC+8 的 00:05。所有「现在几点 / 今天几号」
一律走 `app.core.timezone`，并且把算好的 `target_date` **显式传给 service**，
不让 service 自己问「今天几号」——否则 UTC 的 date.today() 会给出昨天。
"""

import asyncio
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.timezone import app_tz, now_in_app_tz, parse_hhmm, today_in_app_tz
from app.db.session import AsyncSessionLocal
from app.services.inspection_service import generate_daily_tasks, scan_missed_tasks

settings = get_settings()

DEFAULT_GENERATE_TIME = time(0, 5)  # PRD OQ-1：默认 UTC+8 00:05

_generate_task: Optional[asyncio.Task] = None
_scan_task: Optional[asyncio.Task] = None


def generate_time() -> time:
    """每日生成时刻（业务时区）；配置非法时降级到 00:05"""
    return parse_hhmm(
        getattr(settings, "INSPECTION_GENERATE_TIME", "00:05"), DEFAULT_GENERATE_TIME
    )


def next_run_at(now: datetime, at: Optional[time] = None) -> datetime:
    """
    给定当前时刻，返回下一次生成时刻（业务时区的「墙上时间」）。

    - `now` 必须**带 tzinfo**（naive 与 aware 比较会抛 TypeError，早失败好过
      按本地时区猜）。可以是任何时区，函数内部先归一化。
    - **返回值恒为业务时区**（`app_tz()`）。这样「00:05」这个契约不会被调用方
      的时区悄悄改写成别的钟点——若原样继承入参时区，
      `next_run_at(datetime(..., tzinfo=utc))` 会返回「UTC 00:05」，
      也就是北京的 08:05，与 PRD 的 UTC+8 00:05 差了 8 小时。

    边界：触发时刻**已到或已过** → 顺延次日；未到 → 当天。
    （用 `<=` 而非 `<`：恰好在 00:05:00 时若返回当天，循环会 `sleep(0)` 空转。）

    aware 相减与时区无关，所以调用方拿返回值去算 `sleep` 秒数不受影响。
    """
    if now.tzinfo is None:
        raise ValueError(
            "next_run_at() 需要带 tzinfo 的 datetime（见 app/core/timezone.py）"
        )

    tz = app_tz()
    local_now = now.astimezone(tz)  # 任何 aware 输入先归一到业务时区
    target_time = at or generate_time()

    # 用 combine 而不是 replace：replace 会把 fold 一起带过来，跨 DST 时可能算错
    today_target = datetime.combine(local_now.date(), target_time, tzinfo=tz)

    if today_target <= local_now:
        return datetime.combine(
            local_now.date() + timedelta(days=1), target_time, tzinfo=tz
        )
    return today_target


async def generate_once(target_date: Optional[date] = None) -> Dict[str, Any]:
    """
    执行一轮「生成当日任务」，返回统计。

    不传 `target_date` 时按**业务时区**取今天（而不是容器的 `date.today()`）。
    """
    if target_date is None:
        target_date = today_in_app_tz()

    async with AsyncSessionLocal() as db:
        stats = await generate_daily_tasks(db, target_date)

    print(
        f"[INSPECTION] 生成 {stats['date']} 任务：计划 {stats['plans']}，"
        f"新建 {stats['created']}，已存在 {stats['skipped']}，失败 {stats['failed']}"
    )
    for err in stats["errors"]:
        print(f"[WARN] 计划 {err['plan_id']} 生成失败：{err['error']}")

    return stats


async def scan_missed_once() -> Dict[str, Any]:
    """执行一轮漏检扫描，返回统计（`scan_missed_tasks` 自带 commit）"""
    # 显式传 before_date：`scan_missed_tasks` 的默认值是容器本地的
    # `date.today() - 1`（UTC），08:00 北京时间之前会比业务口径少一天。
    # 只在这里传，不改函数默认值——/inspection-missed-stats 接口也走它。
    before_date = today_in_app_tz() - timedelta(days=1)

    async with AsyncSessionLocal() as db:
        result = await scan_missed_tasks(db, before_date=before_date)

    if result["marked_missed"] > 0:
        print(f"[INSPECTION] 漏检扫描：标记 {result['marked_missed']} 条为 missed")
    if result["alert_count"] > 0:
        print(f"[INSPECTION] ALERT：{result['alert_count']} 个计划漏检超过阈值")

    return result


async def _catch_up_then_generate(now: datetime, at: time) -> None:
    """启动补跑（仅当天时刻已过时）→ 转入常规循环"""
    if datetime.combine(now.date(), at, tzinfo=now.tzinfo) <= now:
        try:
            await generate_once()
        except Exception as exc:  # noqa: BLE001 - 补跑失败不能让调度器起不来
            print(f"[WARN] 巡检任务启动补跑失败：{type(exc).__name__}: {exc}")

    await _generate_loop()


async def _generate_loop() -> None:
    """等到下一个生成时刻 → 生成当天任务 → 重复"""
    try:
        while True:
            now = now_in_app_tz()
            target = next_run_at(now)
            await asyncio.sleep(max((target - now).total_seconds(), 0))

            try:
                await generate_once()
            except Exception as exc:  # noqa: BLE001 - 单轮失败不能让循环静默消失
                print(f"[WARN] 巡检任务生成失败：{type(exc).__name__}: {exc}")
    except asyncio.CancelledError:
        return


async def _scan_loop() -> None:
    interval = getattr(settings, "INSPECTION_MISSED_SCAN_INTERVAL_SECONDS", 3600)
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await scan_missed_once()
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] 漏检扫描失败：{type(exc).__name__}: {exc}")
    except asyncio.CancelledError:
        return


def start() -> None:
    """
    幂等启动；`INSPECTION_SCHEDULER_ENABLED=false` 时不注册。

    启动补跑：若当天的生成时刻**已过**（服务在 00:05 时没运行——宕机、重启、
    部署），立刻补跑一次。`generate_daily_tasks` 对已存在的 (plan, date)
    记账为 skipped，因此重复执行安全。
    """
    global _generate_task, _scan_task

    if not getattr(settings, "INSPECTION_SCHEDULER_ENABLED", True):
        print("[INSPECTION] 调度器已禁用（INSPECTION_SCHEDULER_ENABLED=false）")
        return

    now = now_in_app_tz()
    at = generate_time()

    if _generate_task is None or _generate_task.done():
        _generate_task = asyncio.create_task(
            _catch_up_then_generate(now, at), name="inspection-generate"
        )
        print(f"[INSPECTION] 任务生成调度已启动（{now.tzinfo}，每日 {at:%H:%M}）")

    if _scan_task is None or _scan_task.done():
        interval = getattr(settings, "INSPECTION_MISSED_SCAN_INTERVAL_SECONDS", 3600)
        _scan_task = asyncio.create_task(_scan_loop(), name="inspection-missed-scan")
        print(f"[INSPECTION] 漏检扫描已启动（每 {interval}s）")


async def stop() -> None:
    global _generate_task, _scan_task
    tasks = [_generate_task, _scan_task]
    _generate_task = _scan_task = None

    for task in tasks:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def current_timezone() -> ZoneInfo:
    """当前业务时区（便于排查时确认口径）"""
    return app_tz()
