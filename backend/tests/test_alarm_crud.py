"""
报警模型与状态机（3.3 B-12 / B-16）测试

覆盖：报警生成与快照字段、同设备同类未收敛去重、状态机合法/非法流转、
误报原因必填、分页筛选与数据权限隔离。
"""

import pytest
from pydantic import ValidationError

from app.core.exceptions import AuthError
from app.models.alarm import can_transition
from app.schemas.alarm import AlarmConfirmRequest
from app.services import alarm_service
from tests.device_helpers import (
    create_device_type,
    create_device_user,
    create_org,
)
from tests.monitor_helpers import ALARM_ONLY_PERMS, create_alarm, create_device


@pytest.fixture
async def alarm_env(db_session):
    org = await create_org(db_session, "报警大楼")
    other = await create_org(db_session, "另一栋楼")
    device_type = await create_device_type(db_session)
    device = await create_device(db_session, org, device_type, "DEV-ALM-001")
    stranger = await create_device(db_session, other, device_type, "DEV-ALM-002")
    chief = await create_device_user(
        db_session, username="alarm_chief", perm_codes=ALARM_ONLY_PERMS, data_scope="all"
    )
    officer = await create_device_user(
        db_session,
        username="alarm_officer",
        perm_codes=ALARM_ONLY_PERMS,
        data_scope="dept",
        org=org,
    )
    return {
        "org": org,
        "other": other,
        "type": device_type,
        "device": device,
        "stranger": stranger,
        "chief": chief,
        "officer": officer,
    }


async def test_raise_alarm_snapshots_device_and_org(db_session, fake_redis, alarm_env):
    """报警入库带 org_id/device_code 快照，级别由类型分级推导"""
    env = alarm_env
    alarm, created = await alarm_service.raise_alarm(
        db_session, env["device"], "fire", location_description="3F 走廊"
    )
    await db_session.commit()

    assert created is True
    assert (alarm.status, alarm.alarm_level, alarm.org_id) == (
        "pending",
        "critical",
        env["org"].id,
    )
    assert alarm.device_code == "DEV-ALM-001"
    assert alarm.pending_since is not None

    payload = alarm_service.alarm_payload(alarm)
    assert payload["org_id"] == env["org"].id and payload["alarm_type"] == "fire"
    assert payload["silenced"] is False and payload["is_drill"] is False

    with pytest.raises(AuthError):
        await alarm_service.raise_alarm(db_session, env["device"], "unknown_type")


async def test_raise_alarm_dedupes_open_alarm(db_session, alarm_env):
    """同设备同类型未收敛时复用既有记录，避免报警风暴"""
    device = alarm_env["device"]
    first, created_a = await alarm_service.raise_alarm(db_session, device, "fault")
    await db_session.commit()
    second, created_b = await alarm_service.raise_alarm(db_session, device, "fault")
    await db_session.commit()

    assert (created_a, created_b) == (True, False)
    assert first.id == second.id

    # 换类型不受去重影响
    other, created_c = await alarm_service.raise_alarm(db_session, device, "shield")
    await db_session.commit()
    assert created_c is True and other.id != first.id

    # 已收敛（resolved）后再来同类报警应当新建
    first.status = "resolved"
    await db_session.commit()
    third, created_d = await alarm_service.raise_alarm(db_session, device, "fault")
    await db_session.commit()
    assert created_d is True and third.id != first.id


async def test_confirm_alarm_transitions(db_session, fake_redis, alarm_env):
    """pending → confirmed / false_alarm；终态再确认属非法流转"""
    env = alarm_env
    alarm = await create_alarm(db_session, env["device"], "fire")

    confirmed = await alarm_service.confirm_alarm(
        db_session,
        fake_redis,
        alarm.id,
        env["chief"],
        AlarmConfirmRequest(confirm_result="real"),
    )
    assert confirmed.status == "confirmed"
    assert confirmed.confirmed_by == env["chief"].id
    assert confirmed.confirmed_at is not None
    assert confirmed.false_reason is None

    with pytest.raises(AuthError) as exc:
        await alarm_service.confirm_alarm(
            db_session,
            fake_redis,
            alarm.id,
            env["chief"],
            AlarmConfirmRequest(confirm_result="false_alarm", false_reason="重复触发"),
        )
    assert exc.value.code == 400 and "confirmed" in exc.value.message
    assert can_transition("confirmed", "false_alarm") is False


async def test_false_alarm_requires_reason(db_session, fake_redis, alarm_env):
    """误报原因必填：schema 先拦，服务层把原因写库"""
    alarm = await create_alarm(db_session, alarm_env["device"], "pre_fire")

    with pytest.raises(ValidationError) as exc:
        AlarmConfirmRequest(confirm_result="false_alarm")
    assert "误报" in str(exc.value)

    with pytest.raises(ValidationError):
        AlarmConfirmRequest(confirm_result="false_alarm", false_reason="   ")

    resolved = await alarm_service.confirm_alarm(
        db_session,
        fake_redis,
        alarm.id,
        alarm_env["chief"],
        AlarmConfirmRequest(confirm_result="false_alarm", false_reason="施工扬尘"),
    )
    assert resolved.status == "false_alarm" and resolved.false_reason == "施工扬尘"

    # 误报警不会污染设备状态：设备仍是 normal
    await db_session.refresh(alarm_env["device"])
    assert alarm_env["device"].status == "normal"


async def test_list_alarms_filters_and_data_scope(db_session, alarm_env):
    """类型/状态/演练标记筛选生效；dept 用户只见本区域报警"""
    env = alarm_env
    fire = await create_alarm(db_session, env["device"], "fire")
    fault = await create_alarm(db_session, env["device"], "fault")
    drill = await create_alarm(db_session, env["device"], "pre_fire", is_drill=True)
    away = await create_alarm(db_session, env["stranger"], "fire")

    items, total = await alarm_service.list_alarms(db_session, env["chief"])
    assert total == 3 and {a.id for a in items} == {fire.id, fault.id, away.id}
    assert all(a.is_drill is False for a in items)

    with_drill, _ = await alarm_service.list_alarms(
        db_session, env["chief"], include_drill=True
    )
    assert len(with_drill) == 4

    only_fault, _ = await alarm_service.list_alarms(
        db_session, env["chief"], alarm_type="fault"
    )
    assert [a.id for a in only_fault] == [fault.id]

    pending_only, _ = await alarm_service.list_alarms(
        db_session, env["chief"], status="pending,resolved"
    )
    assert len(pending_only) == 3

    # dept 用户只看得到本区域（另一栋楼的报警不出现，也不泄露存在性）
    scoped, scoped_total = await alarm_service.list_alarms(db_session, env["officer"])
    assert scoped_total == 2 and {a.id for a in scoped} == {fire.id, fault.id}
    with pytest.raises(AuthError) as exc:
        await alarm_service.get_alarm_for_user(db_session, away.id, env["officer"])
    assert exc.value.code == 404
