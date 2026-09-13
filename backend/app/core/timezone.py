"""
业务时区工具（3.6 FR-033）
==========================

后端容器默认跑在 UTC，而业务口径是北京时间：PRD FR-033 要求「UTC+8 的 00:05」
生成当日巡检任务。沿用容器本地时间会错两次——按钟点算，00:05 触发实际是北京
08:05；即便算对钟点，`generate_tasks_for_plan` 内部的 `date.today()` 仍返回 UTC
的「昨天」，生成出来的任务日期是错的。

所以把「现在是几点 / 今天是几号」收敛到这一个模块：**时区只在这一层出现**，
调用方拿到的是已经算好的 datetime / date，不自己碰 tzinfo。

调用约定：调度器用 `today_in_app_tz()` 算出 target_date 后**显式传参**给
service 层，而不是让 service 自己去问「今天几号」。

**硬规矩：业务时区只用于「今天是几号」和调度，不要用它写时间戳。**
`InspectionTask.created_at` 等处沿用 `datetime.now()`（容器内即 UTC），与
`Base.created_at` 的 `datetime.utcnow` 口径一致；若把某处顺手改成
`now_in_app_tz()`，`DateTime(timezone=True)` 列里就会混进 +08:00 语义，
全站时间显示整体偏 8 小时。

注：本模块目前只服务巡检调度器。`app/core/security.py:utc_to_cst_iso()` 里还有
一段硬编码的 `timedelta(hours=8)`，把它收敛到此处属于后续工作，本次不动
（避免顺带改变登录日志等既有输出）。
"""

from datetime import date, datetime, time, timedelta, timezone as dt_timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import get_settings

DEFAULT_TIMEZONE = "Asia/Shanghai"
CST_OFFSET = dt_timezone(timedelta(hours=8))  # 兜底：固定 +08:00（中国无夏令时）


def app_tz() -> tzinfo:
    """
    业务时区。

    配置非法时降级到 `Asia/Shanghai` 并打印警告——时区写错不该让服务起不来。
    若连时区数据库都取不到（IANA 名字全部解析失败），再退到固定 `+08:00`：
    中国自 1991 年起无夏令时，固定偏移与 `Asia/Shanghai` 语义完全等价，
    而它不依赖任何时区数据库，一定能构造出来。

    实测 `python:3.10-slim` 自带 `/usr/share/zoneinfo`，正常路径不会走到兜底；
    兜底是防基础镜像变更，不是当前已知故障。

    不缓存结果：`get_settings()` 本身是 lru_cache 的单例，`ZoneInfo` 内部也有
    实例缓存，重复构造开销可忽略；不缓存换来测试里 monkeypatch 配置后立即生效。
    """
    name = getattr(get_settings(), "APP_TIMEZONE", None) or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        print(f"[WARN] APP_TIMEZONE={name!r} 无法解析，降级为 {DEFAULT_TIMEZONE}")

    try:
        return ZoneInfo(DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        print("[WARN] 时区数据库不可用，降级为固定 +08:00")
        return CST_OFFSET


def now_in_app_tz() -> datetime:
    """业务时区的当前时刻（带 tzinfo）"""
    return datetime.now(app_tz())


def today_in_app_tz() -> date:
    """业务口径的「今天」"""
    return now_in_app_tz().date()


def parse_hhmm(value: str, fallback: time = time(0, 5)) -> time:
    """
    解析 "HH:MM" 配置；非法则降级到 fallback 并告警。

    与 `app_tz()` 同样的取舍：配置错误只降级，不抛异常拖垮启动。
    """
    try:
        hour_str, _, minute_str = str(value).partition(":")
        hour, minute = int(hour_str), int(minute_str)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"超出范围: {value!r}")
        return time(hour, minute)
    except (ValueError, TypeError):
        print(f"[WARN] INSPECTION_GENERATE_TIME={value!r} 非法，降级为 {fallback:%H:%M}")
        return fallback
