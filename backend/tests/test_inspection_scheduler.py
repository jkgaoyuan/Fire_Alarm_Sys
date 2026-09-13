"""
巡检定时调度器（3.6 B-2 / B-3，FR-033 / FR-035）
================================================

覆盖两件事：
1. `generate_daily_tasks(db, target_date)` —— 每日生成的主体逻辑
2. `next_run_at(now)` —— 纯函数，决定「下一次什么时候跑」

**不测后台循环**（`while True` + `sleep` 没法在单测里跑）。调度器的可测性就是
按这个边界切的：循环是薄编排，逻辑全在上面两个入口里。测试直接注入 `db_session`，
与 `tests/test_device_report.py` 直接调 `scan_offline_devices(db_session, ...)` 同范式。

时区是本模块的重点：容器跑 UTC，业务要 UTC+8，`target_date` 必须由调用方按
业务时区算好传入（TC-SCH-010）。
"""
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.inspection import InspectionTask
from app.services import inspection_service
from app.services.inspection_scheduler import next_run_at
from app.services.inspection_service import (
    _is_duplicate_task_error,
    generate_daily_tasks,
    is_cycle_due,
)
from tests.inspection_helpers import create_inspection_user, make_plan


CST = timezone(timedelta(hours=8))


async def task_count(db, plan_id: int | None = None) -> int:
    stmt = select(func.count()).select_from(InspectionTask)
    if plan_id is not None:
        stmt = stmt.where(InspectionTask.plan_id == plan_id)
    return (await db.execute(stmt)).scalar_one()


# ==================== 生成逻辑 ====================

@pytest.mark.asyncio
async def test_generates_for_enabled_plans_only(db_session):
    """
    TC-SCH-001 / TC-SCH-002: 只为启用中的计划生成当日任务，停用的跳过。

    不修会怎样：停用的计划天天长出新任务，任务列表里全是无法执行的僵尸任务。
    """
    owner = await create_inspection_user(db_session, "sched_owner")
    today = date.today()

    enabled = await make_plan(
        db_session, plan_name="启用计划", responsible_user_id=owner.id
    )
    disabled = await make_plan(
        db_session, plan_name="停用计划", responsible_user_id=owner.id, is_enabled=False
    )

    stats = await generate_daily_tasks(db_session, today)

    assert stats["plans"] == 1, "停用的计划不该参与生成"
    assert stats["created"] == 1
    assert await task_count(db_session, enabled.id) == 1
    assert await task_count(db_session, disabled.id) == 0


@pytest.mark.asyncio
async def test_respects_plan_validity_window(db_session):
    """
    TC-SCH-003: 只在计划有效期内生成任务。

    不修会怎样：手工生成时用户自选日期尚可接受，但自动生成若不看
    start_date/end_date，一个去年就结束的计划会天天被建任务。
    """
    owner = await create_inspection_user(db_session, "sched_window")
    today = date.today()

    expired = await make_plan(
        db_session,
        plan_name="已结束",
        responsible_user_id=owner.id,
        end_date=today - timedelta(days=1),
    )
    not_started = await make_plan(
        db_session,
        plan_name="未开始",
        responsible_user_id=owner.id,
        start_date=today + timedelta(days=1),
    )
    in_window = await make_plan(
        db_session,
        plan_name="有效期内",
        responsible_user_id=owner.id,
        start_date=today - timedelta(days=10),
        end_date=today + timedelta(days=10),
    )

    stats = await generate_daily_tasks(db_session, today)

    assert stats["plans"] == 1
    assert await task_count(db_session, expired.id) == 0
    assert await task_count(db_session, not_started.id) == 0
    assert await task_count(db_session, in_window.id) == 1


@pytest.mark.asyncio
async def test_is_idempotent(db_session):
    """
    TC-SCH-004: 重复执行不重复建任务。

    不修会怎样：启动补跑 + 定时触发 + 多 worker 会让同一天的任务翻倍。
    """
    owner = await create_inspection_user(db_session, "sched_idem")
    plan = await make_plan(db_session, plan_name="幂等", responsible_user_id=owner.id)
    today = date.today()

    first = await generate_daily_tasks(db_session, today)
    second = await generate_daily_tasks(db_session, today)

    assert first["created"] == 1
    assert second["created"] == 0 and second["skipped"] == 1
    assert await task_count(db_session, plan.id) == 1


@pytest.mark.asyncio
async def test_tasks_are_committed(db_session):
    """
    TC-SCH-005: 生成的任务必须真正提交（返回时不得留着未结束的事务）。

    不修会怎样：`generate_tasks_for_plan` 只 flush 不 commit，而 `get_db` 在
    finally 里只 close 不 commit → 事务回滚。线上表现为
    「接口说生成了 N 条、库里 0 行」。

    **为什么用 `in_transaction()` 而不是「rollback 后行还在」**：
    SQLite/aiosqlite 方言下 SQLAlchemy 的 savepoint 是用提交模拟的，
    `begin_nested()` 里 flush 出来的行**扛得住后续 rollback**（实测：套 savepoint
    的行 rollback 后仍在，不套的才被丢弃）。所以「rollback 后还在」在 SQLite 上
    恒为真，是个测不出问题的假守护。`in_transaction()` 才是可靠信号：
    实测提交后为 False、仅 flush 为 True。
    """
    owner = await create_inspection_user(db_session, "sched_commit")
    await make_plan(db_session, plan_name="提交校验", responsible_user_id=owner.id)

    await generate_daily_tasks(db_session, date.today())

    assert db_session.in_transaction() is False, "generate_daily_tasks 返回时事务仍未提交"
    assert await task_count(db_session) == 1


@pytest.mark.asyncio
async def test_one_failing_plan_does_not_abort_the_batch(db_session, monkeypatch):
    """
    TC-SCH-006 / TC-SCH-007: 单个计划失败不影响其它计划，统计如实记录。

    不修会怎样：一个坏计划（如责任人被删导致 FK 违例）会让整批任务全部丢失，
    而且异常冒到调度器循环里只留一行日志，第二天照旧。

    这里用 monkeypatch 造失败而不是靠 FK 违例：SQLite 默认不启用外键约束
    （PRAGMA foreign_keys=OFF），真插坏数据不会报错，测不出隔离性。
    """
    owner = await create_inspection_user(db_session, "sched_isolate")
    today = date.today()

    good_a = await make_plan(db_session, plan_name="好计划A", responsible_user_id=owner.id)
    bad = await make_plan(db_session, plan_name="坏计划", responsible_user_id=owner.id)
    good_b = await make_plan(db_session, plan_name="好计划B", responsible_user_id=owner.id)

    real_generate = inspection_service.generate_tasks_for_plan

    async def flaky(db, plan_id, target_date):
        if plan_id == bad.id:
            raise RuntimeError("模拟该计划生成失败")
        return await real_generate(db, plan_id, target_date)

    monkeypatch.setattr(inspection_service, "generate_tasks_for_plan", flaky)

    stats = await generate_daily_tasks(db_session, today)

    assert stats["plans"] == 3
    assert stats["created"] == 2
    assert stats["failed"] == 1
    assert stats["errors"][0]["plan_id"] == bad.id
    assert "模拟该计划生成失败" in stats["errors"][0]["error"]
    # 关键：坏计划没有拖垮好计划
    assert await task_count(db_session, good_a.id) == 1
    assert await task_count(db_session, good_b.id) == 1
    assert await task_count(db_session, bad.id) == 0


@pytest.mark.asyncio
async def test_no_enabled_plans_is_a_noop(db_session):
    """TC-SCH-007: 没有可选计划时返回零统计而不是报错。"""
    stats = await generate_daily_tasks(db_session, date.today())

    assert stats["plans"] == 0
    assert stats["created"] == stats["skipped"] == stats["failed"] == 0
    assert stats["errors"] == []


# ==================== 周期规则（3.6 计划 §3.2） ====================

def test_is_cycle_due_follows_calendar_rules():
    """
    TC-SCH-012: 周期规则按自然日历判断，不是「每天都生成」。

    不修会怎样：`generate_daily_tasks` 若不看 cycle_type，一个 weekly 计划
    会被每天建一条任务——一周 7 条而不是 1 条，任务列表和执行率全失真。
    计划文档 §3.2 规定：weekly→每周一、monthly→每月1日、
    quarterly→每季度首月1日、yearly→每年1月1日。
    """
    monday = date(2026, 9, 14)
    tuesday = date(2026, 9, 15)
    first_of_month = date(2026, 10, 1)
    year_start = date(2027, 1, 1)

    assert monday.weekday() == 0 and tuesday.weekday() == 1, "用例前提：周一/周二"

    # daily：天天生成
    assert is_cycle_due("daily", monday)
    assert is_cycle_due("daily", tuesday)

    # weekly：仅周一
    assert is_cycle_due("weekly", monday)
    assert not is_cycle_due("weekly", tuesday)

    # monthly：仅每月 1 日
    assert is_cycle_due("monthly", first_of_month)
    assert not is_cycle_due("monthly", tuesday)

    # quarterly：仅 1/4/7/10 月的 1 日
    assert is_cycle_due("quarterly", first_of_month)  # 10 月 1 日
    assert is_cycle_due("quarterly", date(2026, 7, 1))
    assert not is_cycle_due("quarterly", date(2026, 5, 1))  # 5 月不在季度首月

    # yearly：仅 1 月 1 日
    assert is_cycle_due("yearly", year_start)
    assert not is_cycle_due("yearly", first_of_month)

    # 未知取值：跳过并告警，不按日生成垃圾任务
    assert not is_cycle_due("fortnightly", monday)


@pytest.mark.asyncio
async def test_generate_respects_cycle_type(db_session):
    """TC-SCH-012: 周二只给 daily 计划生成，weekly 计划不生成。"""
    owner = await create_inspection_user(db_session, "sched_cycle")
    tuesday = date(2026, 9, 15)
    assert tuesday.weekday() == 1

    daily = await make_plan(
        db_session, plan_name="每日", responsible_user_id=owner.id, cycle_type="daily",
        start_date=date(2026, 9, 1),
    )
    weekly = await make_plan(
        db_session, plan_name="每周", responsible_user_id=owner.id, cycle_type="weekly",
        start_date=date(2026, 9, 1),
    )

    stats = await generate_daily_tasks(db_session, tuesday)

    assert stats["plans"] == 1, "周二不该给 weekly 计划生成任务"
    assert await task_count(db_session, daily.id) == 1
    assert await task_count(db_session, weekly.id) == 0


# ==================== 冲突分类 ====================

def test_duplicate_error_classifier_covers_postgres_branch():
    """
    TC-SCH-013: Postgres 的 23505（唯一违例）必须被识别为「已存在」。

    这条分支在 SQLite 上永远跑不到（SQLite 的 IntegrityError 没有 sqlstate），
    所以用假对象直接覆盖，否则生产路径零覆盖——而生产跑的是 Postgres。
    """
    class FakeOrig:
        sqlstate = "23505"

    class FakeOrigFk:
        sqlstate = "23503"  # FK 违例，必须**不能**被当成「已存在」

    assert _is_duplicate_task_error(IntegrityError("stmt", {}, FakeOrig()))
    assert not _is_duplicate_task_error(IntegrityError("stmt", {}, FakeOrigFk()))
    assert not _is_duplicate_task_error(
        IntegrityError("stmt", {}, Exception("FOREIGN KEY constraint failed"))
    )


def test_duplicate_error_classifier_covers_sqlite_text():
    """TC-SCH-013: SQLite 无 sqlstate，回退到文案匹配。"""
    assert _is_duplicate_task_error(
        IntegrityError("stmt", {}, Exception("UNIQUE constraint failed: inspection_tasks.plan_id"))
    )
    assert _is_duplicate_task_error(
        IntegrityError("stmt", {}, Exception("uq_inspection_tasks_plan_date"))
    )


# ==================== next_run_at 边界 ====================

def test_next_run_today_when_time_not_reached():
    """TC-SCH-008: 当天生成时刻还没到 → 返回当天（业务时区）"""
    now = datetime(2026, 9, 13, 0, 1, tzinfo=CST)

    assert next_run_at(now, time(0, 5)) == datetime(2026, 9, 13, 0, 5, tzinfo=CST)


def test_next_run_tomorrow_when_time_passed():
    """TC-SCH-009: 当天生成时刻已过 → 顺延次日"""
    now = datetime(2026, 9, 13, 9, 0, tzinfo=CST)

    assert next_run_at(now, time(0, 5)) == datetime(2026, 9, 14, 0, 5, tzinfo=CST)


def test_next_run_at_exact_time_rolls_to_tomorrow():
    """TC-SCH-009: 恰好等于触发时刻视为「已过」，顺延次日（避免原地空转）"""
    now = datetime(2026, 9, 13, 0, 5, tzinfo=CST)

    assert next_run_at(now, time(0, 5)) == datetime(2026, 9, 14, 0, 5, tzinfo=CST)


def test_next_run_rejects_naive_datetime():
    """
    TC-SCH-010: naive datetime 必须报错，不能默默按某个时区解释。

    不修会怎样：naive 与 tz-aware 比较会抛 TypeError 或按本地时区猜，
    调度时刻会静默偏移 8 小时。
    """
    with pytest.raises(ValueError, match="tzinfo"):
        next_run_at(datetime(2026, 9, 13, 9, 0), time(0, 5))


def test_next_run_normalises_utc_input_to_business_timezone():
    """
    TC-SCH-010: 传入 UTC 时刻时，返回值必须是**业务时区**的 00:05，而不是 UTC 00:05。

    不修会怎样：原样继承入参时区会让「UTC 00:05」＝北京的 08:05，
    与 PRD 的 UTC+8 00:05 差 8 小时——而且只在有人传非业务时区时暴露。

    UTC 09-13 16:00 == 北京 09-14 00:00，此刻当天的 00:05 还没到 →
    应返回北京 09-14 00:05（＝UTC 09-13 16:05）。
    """
    utc_now = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)

    result = next_run_at(utc_now, time(0, 5))

    assert result.astimezone(CST) == datetime(2026, 9, 14, 0, 5, tzinfo=CST)
    assert result.utcoffset() == timedelta(hours=8), "返回值应是业务时区而非入参时区"


def test_business_today_differs_from_utc_today_before_8am():
    """
    TC-SCH-010: 业务时区的「今天」与容器的 UTC「今天」在凌晨会差一天。

    这正是必须显式传 target_date 的原因：容器 09-13 16:30 UTC 时，
    北京已是 09-14 00:30——PRD 要求生成的是 **09-14** 的任务，
    而 `date.today()`（UTC）会给出 09-13。
    """
    from app.core.timezone import today_in_app_tz

    utc_instant = datetime(2026, 9, 13, 16, 30, tzinfo=timezone.utc)

    assert utc_instant.date() == date(2026, 9, 13)
    assert utc_instant.astimezone(CST).date() == date(2026, 9, 14)
    assert isinstance(today_in_app_tz(), date)


# ==================== 唯一约束 ====================

@pytest.mark.asyncio
async def test_duplicate_plan_date_is_rejected_by_db(db_session):
    """
    TC-SCH-011: (plan_id, task_date) 唯一约束真的存在于库上。

    不修会怎样：这条不变量此前只写在注释里，去重全靠 check-then-act；
    多 worker 同时启动时两个进程都能通过检查并各插一条。
    """
    owner = await create_inspection_user(db_session, "sched_uq")
    today = date.today()
    plan = await make_plan(db_session, plan_name="唯一约束", responsible_user_id=owner.id)

    db_session.add(
        InspectionTask(plan_id=plan.id, task_date=today, responsible_user_id=owner.id)
    )
    await db_session.commit()

    db_session.add(
        InspectionTask(plan_id=plan.id, task_date=today, responsible_user_id=owner.id)
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_generate_treats_unique_violation_as_skipped(db_session):
    """
    TC-SCH-011: 并发下撞唯一约束时，`generate_tasks_for_plan` 按「已存在」返回空列表。

    不修会怎样：手动接口连点两次「生成任务」会 500；调度器启动补跑撞上
    正在执行的定时任务也会让整轮失败。
    """
    owner = await create_inspection_user(db_session, "sched_race")
    today = date.today()
    plan = await make_plan(db_session, plan_name="竞态", responsible_user_id=owner.id)

    # 先手工插一条，绕过 service 的 check-then-act，制造「已存在但没被查到」的局面
    db_session.add(
        InspectionTask(plan_id=plan.id, task_date=today, responsible_user_id=owner.id)
    )
    await db_session.commit()

    result = await inspection_service.generate_tasks_for_plan(db_session, plan.id, today)

    assert result == [], "撞唯一约束应被视为「已存在」"
    assert await task_count(db_session, plan.id) == 1
