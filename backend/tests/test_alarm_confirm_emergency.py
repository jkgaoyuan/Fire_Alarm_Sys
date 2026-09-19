"""
报警确认 → 应急事件自动创建（3.5-B2 / FR-027）接线测试

**本文件测的是「接线」，不是 `create_emergency_event` 本身**（后者已有
test_emergency_event.py 覆盖）。区别是关键：这个缺陷能长期存活，正是因为
既有用例全部**直接调 service 函数**，没有一条走 `confirm_alarm` 这条真实入口。

计划 3.5-B2 原文：`alarm_service.confirm_alarm()` 真实火警分支自动创建事件与时间轴。
"""

from datetime import date

import pytest
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.models.emergency import EmergencyEvent, EmergencyTimeline
from app.schemas.alarm import AlarmConfirmRequest
from app.services import alarm_service, emergency_service
from tests.device_helpers import create_device_type, create_device_user, create_org
from tests.monitor_helpers import ALARM_ONLY_PERMS, create_alarm, create_device


@pytest.fixture
async def env(db_session):
    org = await create_org(db_session, "确认联动大楼")
    device_type = await create_device_type(db_session)
    device = await create_device(db_session, org, device_type, "DEV-CEM-001")
    chief = await create_device_user(
        db_session, username="confirm_chief", perm_codes=ALARM_ONLY_PERMS, data_scope="all"
    )
    return {"org": org, "device": device, "chief": chief}


async def _events_for(db, alarm_id: int) -> list[EmergencyEvent]:
    stmt = select(EmergencyEvent).where(EmergencyEvent.alarm_id == alarm_id)
    return list((await db.execute(stmt)).scalars().all())


async def test_confirm_real_fire_creates_emergency_event(db_session, fake_redis, env):
    """
    FR-027 主干：确认为真实火警 → 自动建应急事件。

    这条红过整整几个版本：`create_emergency_event` 在生产代码里**零调用方**，
    前端却写着「确认为真实火警后，系统将自动创建应急处置事件」。
    """
    alarm = await create_alarm(db_session, env["device"], "fire")

    await alarm_service.confirm_alarm(
        db_session, fake_redis, alarm.id, env["chief"], AlarmConfirmRequest(confirm_result="real")
    )

    events = await _events_for(db_session, alarm.id)
    assert len(events) == 1
    event = events[0]
    assert event.status == "processing"
    assert event.created_by == env["chief"].id
    assert event.event_no.startswith("EV-")


async def test_confirm_real_fire_seeds_alarm_and_confirm_timeline(db_session, fake_redis, env):
    """事件建出来必须带 2 个初始时间轴节点（火警产生 / 确认真实火警）"""
    alarm = await create_alarm(db_session, env["device"], "fire")

    await alarm_service.confirm_alarm(
        db_session, fake_redis, alarm.id, env["chief"], AlarmConfirmRequest(confirm_result="real")
    )

    event = (await _events_for(db_session, alarm.id))[0]
    stmt = select(EmergencyTimeline).where(EmergencyTimeline.event_id == event.id)
    nodes = list((await db_session.execute(stmt)).scalars().all())

    assert [n.node_type for n in nodes] == ["alarm", "confirm"]


async def test_confirm_false_alarm_creates_no_event(db_session, fake_redis, env):
    """误报不产生应急事件 —— 只有真实火警才进入处置闭环"""
    alarm = await create_alarm(db_session, env["device"], "fire")

    await alarm_service.confirm_alarm(
        db_session,
        fake_redis,
        alarm.id,
        env["chief"],
        AlarmConfirmRequest(confirm_result="false_alarm", false_reason="重复触发"),
    )

    assert await _events_for(db_session, alarm.id) == []


async def test_confirm_drill_alarm_as_real_is_rejected(db_session, fake_redis, env):
    """
    演练告警不得确认为真实火警。

    3.8 规格：drill 报警「不进入真实统计、不创建应急事件」。既然本就不建事件，
    却允许在界面上确认为「现场属实」，就是在制造一条与处置台账对不上的记录
    （用户实测踩到的正是这条：DEV-TEST 的演练告警被确认为 real，然后什么也没发生）。
    """
    alarm = await create_alarm(db_session, env["device"], "fire", is_drill=True)

    with pytest.raises(AuthError) as exc:
        await alarm_service.confirm_alarm(
            db_session,
            fake_redis,
            alarm.id,
            env["chief"],
            AlarmConfirmRequest(confirm_result="real"),
        )
    assert exc.value.code == 400
    assert "演练" in exc.value.message

    await db_session.refresh(alarm)
    assert alarm.status == "pending"
    assert await _events_for(db_session, alarm.id) == []


async def test_drill_alarm_can_still_be_marked_false_alarm(db_session, fake_redis, env):
    """拒绝 real 之后演练告警仍要能被清掉，否则会永久卡在 pending"""
    alarm = await create_alarm(db_session, env["device"], "fire", is_drill=True)

    confirmed = await alarm_service.confirm_alarm(
        db_session,
        fake_redis,
        alarm.id,
        env["chief"],
        AlarmConfirmRequest(confirm_result="false_alarm", false_reason="演练触发"),
    )

    assert confirmed.status == "false_alarm"


async def test_event_no_uses_business_timezone_not_container_utc(
    db_session, fake_redis, env, monkeypatch
):
    """
    事件编号的日期段取自**业务时区**，不是容器本地时间。

    容器跑 UTC，北京时间 00:00–08:00 之间「今天是几号」会差一天 ——
    沿用在 `emergency_service` 里写死的 `datetime.now()` 会产出
    `EV-<昨天>-001` 这种编号。口径已收敛在 `app/core/timezone.py`
    （该模块的硬规矩：业务时区只用于「今天是几号」，不用于写时间戳；
    事件编号正是「今天是几号」）。
    """
    sentinel = date(2031, 3, 4)
    monkeypatch.setattr(emergency_service, "today_in_app_tz", lambda: sentinel)

    alarm = await create_alarm(db_session, env["device"], "fire")
    await alarm_service.confirm_alarm(
        db_session, fake_redis, alarm.id, env["chief"], AlarmConfirmRequest(confirm_result="real")
    )

    event = (await _events_for(db_session, alarm.id))[0]
    assert event.event_no.startswith("EV-20310304-")


async def test_alarm_status_and_event_commit_together(db_session, fake_redis, env):
    """
    报警状态与应急事件同事务：不能出现「报警已确认、事件没建」的中间态。

    这是接线方式的约束 —— `create_emergency_event` 只 flush 不 commit，
    必须在 `confirm_alarm` 的 commit 之前调用才落在同一事务里。
    """
    alarm = await create_alarm(db_session, env["device"], "fire")

    confirmed = await alarm_service.confirm_alarm(
        db_session, fake_redis, alarm.id, env["chief"], AlarmConfirmRequest(confirm_result="real")
    )

    assert confirmed.status == "confirmed"
    assert len(await _events_for(db_session, alarm.id)) == 1
