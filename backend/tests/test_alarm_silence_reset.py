"""
消音与系统复位（3.3 B-16 / FR-016、计划 5.5）测试

覆盖：复位前置校验（未勾选/未恢复/retired/shield）、跨表事务与审计字段、
重复复位幂等、单条消音只留痕不改状态。
"""

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.models.device import DeviceStatusLog
from app.schemas.alarm import AlarmResetRequest
from app.services import alarm_service, event_stream
from tests.device_helpers import create_device_type, create_device_user, create_org
from tests.monitor_helpers import ALARM_ONLY_PERMS, create_alarm, create_device

STALE = datetime.utcnow() - timedelta(hours=1)
FRESH = datetime.utcnow()


@pytest.fixture
async def reset_env(db_session):
    org = await create_org(db_session, "复位大楼")
    device_type = await create_device_type(db_session)
    operator = await create_device_user(
        db_session, username="reset_op", perm_codes=ALARM_ONLY_PERMS, data_scope="all"
    )
    return {"org": org, "type": device_type, "operator": operator}


async def _device_alarm(db, env, **device_kwargs):
    device = await create_device(
        db, env["org"], env["type"], device_kwargs.pop("code", "DEV-RST-001"), **device_kwargs
    )
    alarm = await create_alarm(db, device, "fire")
    return device, alarm


async def _types(redis):
    frames = await event_stream.read_after(redis, "0-1", 100)
    return [f["type"] for f in frames]


async def test_reset_requires_explicit_physical_confirmation(db_session, fake_redis, reset_env):
    """FR-016.2：physical_restored 是必填的人工确认位，未勾选直接拒绝"""
    device, alarm = await _device_alarm(db_session, reset_env, last_report_at=STALE)

    with pytest.raises(ValidationError):
        AlarmResetRequest()

    with pytest.raises(AuthError) as exc:
        await alarm_service.reset_alarm(
            db_session, fake_redis, alarm.id, reset_env["operator"],
            AlarmResetRequest(physical_restored=False),
        )
    assert exc.value.code == 400 and "物理状态" in exc.value.message

    await db_session.refresh(alarm)
    assert alarm.status == "pending" and alarm.reset_by is None


async def test_reset_rejects_when_device_not_recovered(db_session, fake_redis, reset_env):
    """上报新鲜说明回读通道在线：设备仍处 alarm 时禁止复位（5.5 判定）"""
    device, alarm = await _device_alarm(
        db_session, reset_env, code="DEV-RST-002", status="alarm", last_report_at=FRESH
    )
    with pytest.raises(AuthError) as exc:
        await alarm_service.reset_alarm(
            db_session, fake_redis, alarm.id, reset_env["operator"],
            AlarmResetRequest(physical_restored=True),
        )
    assert "设备物理状态未恢复" in exc.value.message
    assert alarm.status == "pending" and device.status == "alarm"


async def test_reset_rejects_retired_and_shield_device(db_session, fake_redis, reset_env):
    """退役/屏蔽设备不参与系统复位，需走各自的解除流程"""
    for status, keyword in (("retired", "退役"), ("shield", "屏蔽")):
        device, alarm = await _device_alarm(
            db_session, reset_env, code=f"DEV-RST-{status}", status=status, last_report_at=STALE
        )
        with pytest.raises(AuthError) as exc:
            await alarm_service.reset_alarm(
                db_session, fake_redis, alarm.id, reset_env["operator"],
                AlarmResetRequest(physical_restored=True),
            )
        assert keyword in exc.value.message
        assert alarm.status == "pending" and device.status == status


async def test_reset_commits_alarm_device_and_audit_together(
    db_session, fake_redis, reset_env
):
    """
    OQ-2：无回读通道（last_report_at 过期）时靠显式勾选 + 审计留痕放行。
    报警 resolved / 设备 normal / 状态日志三者同事务落地并各自广播。
    """
    device, alarm = await _device_alarm(
        db_session, reset_env, code="DEV-RST-003", status="alarm", last_report_at=STALE
    )
    result = await alarm_service.reset_alarm(
        db_session, fake_redis, alarm.id, reset_env["operator"],
        AlarmResetRequest(physical_restored=True, remark="现场复核已恢复"),
    )

    assert result.status == "resolved"
    assert result.reset_by == reset_env["operator"].id
    assert result.reset_remark == "现场复核已恢复"
    assert result.resolved_at is not None and result.pending_since is None
    assert device.status == "normal"

    logs = list(
        (
            await db_session.execute(
                select(DeviceStatusLog).where(DeviceStatusLog.device_id == device.id)
            )
        ).scalars()
    )
    assert [(log.old_status, log.new_status, log.reason) for log in logs] == [
        ("alarm", "normal", "系统复位")
    ]
    assert logs[0].changed_by == reset_env["operator"].id

    assert await _types(fake_redis) == ["alarm_reset", "device_status"]


async def test_reset_is_idempotent(db_session, fake_redis, reset_env):
    """并发/重复复位只生效一次：不再写日志、不再广播"""
    device, alarm = await _device_alarm(
        db_session, reset_env, code="DEV-RST-004", status="alarm", last_report_at=STALE
    )
    first = await alarm_service.reset_alarm(
        db_session, fake_redis, alarm.id, reset_env["operator"],
        AlarmResetRequest(physical_restored=True),
    )
    events = await _types(fake_redis)

    second = await alarm_service.reset_alarm(
        db_session, fake_redis, alarm.id, reset_env["operator"],
        AlarmResetRequest(physical_restored=True, remark="重复点击"),
    )

    assert (first.id, second.id) == (alarm.id, alarm.id)
    assert second.reset_remark is None  # 幂等分支不覆盖首次审计
    assert await _types(fake_redis) == events
    logs = list(
        (
            await db_session.execute(
                select(DeviceStatusLog).where(DeviceStatusLog.device_id == device.id)
            )
        ).scalars()
    )
    assert len(logs) == 1


async def test_silence_records_trace_without_changing_status(
    db_session, fake_redis, reset_env
):
    """FR-016.1 单条消音：只留痕并广播一次，报警状态与复位人不受影响"""
    device, alarm = await _device_alarm(db_session, reset_env, code="DEV-RST-005")

    silenced = await alarm_service.silence_alarm(
        db_session, fake_redis, alarm.id, reset_env["operator"]
    )
    assert silenced.status == "pending"
    assert silenced.silenced_by == reset_env["operator"].id
    assert silenced.silenced_at is not None
    assert silenced.reset_by is None

    frames = await event_stream.read_after(fake_redis, "0-1", 100)
    silence_frames = [f for f in frames if f["type"] == "alarm_silenced"]
    assert len(silence_frames) == 1
    assert silence_frames[0]["data"]["alarm_id"] == alarm.id
    assert silence_frames[0]["data"]["org_id"] == device.org_id

    again = await alarm_service.silence_alarm(
        db_session, fake_redis, alarm.id, reset_env["operator"]
    )
    assert again.silenced_at == silenced.silenced_at
    frames = await event_stream.read_after(fake_redis, "0-1", 100)
    assert len([f for f in frames if f["type"] == "alarm_silenced"]) == 1
