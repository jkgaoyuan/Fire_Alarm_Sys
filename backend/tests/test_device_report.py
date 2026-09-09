"""
设备上报与离线检测（3.3 B-13）测试

覆盖：上报的状态/日志/报警联动、同类去重、恢复不新建、last_report_at 刷新、
退役与未知设备拒绝、离线扫描口径、上报端点的开关与凭据保护。
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.api.v1 import monitor as monitor_api
from app.core.config import get_settings
from app.core.exceptions import AuthError, NotFoundError
from app.models.alarm import Alarm
from app.models.device import Device, DeviceStatusLog
from app.schemas.alarm import DeviceReportRequest
from app.services import event_stream
from app.services.device_report_service import (
    handle_device_report,
    scan_offline_devices,
)
from tests.device_helpers import create_device_type, create_org
from tests.monitor_helpers import create_device, report

settings = get_settings()


@pytest.fixture
async def report_env(db_session):
    org = await create_org(db_session, "上报大楼")
    device_type = await create_device_type(db_session)
    device = await create_device(db_session, org, device_type, "DEV-RPT-001")
    return {"org": org, "type": device_type, "device": device}


async def _stream_types(redis) -> list[str]:
    frames = await event_stream.read_after(redis, "0-1", 100)
    return [frame["type"] for frame in frames]


async def _rows(db, model, *conditions):
    return list((await db.execute(select(model).where(*conditions))).scalars().all())


async def _count(db, model, *conditions) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(model).where(*conditions)
            )
        ).scalar()
        or 0
    )


async def test_report_updates_status_log_and_alarm(db_session, fake_redis, report_env):
    """报警上报同时驱动状态、留痕与报警生成，并提交两条事件"""
    device = report_env["device"]

    result = await handle_device_report(
        db_session,
        fake_redis,
        report(
            device,
            status="normal",
            alarm_type="fire",
            location_description="3F 走廊",
        ),
    )

    assert result["old_status"] == "normal" and result["status"] == "alarm"
    assert result["status_changed"] is True and result["alarm_created"] is True
    assert result["alarm_id"] is not None

    await db_session.refresh(device)
    assert device.status == "alarm" and device.last_report_at is not None

    logs = await _rows(db_session, DeviceStatusLog, DeviceStatusLog.device_id == device.id)
    assert [(log.old_status, log.new_status, log.reason) for log in logs] == [
        ("normal", "alarm", "设备上报")
    ]
    assert [log.changed_by for log in logs] == [None]

    alarms = await _rows(db_session, Alarm, Alarm.id == result["alarm_id"])
    assert len(alarms) == 1
    assert (alarms[0].alarm_type, alarms[0].status, alarms[0].org_id) == (
        "fire",
        "pending",
        report_env["org"].id,
    )
    assert await _stream_types(fake_redis) == ["device_status", "alarm_new"]


async def test_report_dedupes_same_open_alarm(db_session, fake_redis, report_env):
    """抖动重复上报不再制造新报警，也不再广播 alarm_new"""
    device = report_env["device"]
    first = await handle_device_report(db_session, fake_redis, report(device, alarm_type="fire"))
    second = await handle_device_report(db_session, fake_redis, report(device, alarm_type="fire"))

    assert first["alarm_created"] is True and second["alarm_created"] is False
    assert first["alarm_id"] == second["alarm_id"]
    assert second["status_changed"] is False
    assert await _count(db_session, Alarm, Alarm.device_id == device.id) == 1
    assert await _stream_types(fake_redis) == ["device_status", "alarm_new"]


async def test_report_recovery_creates_no_alarm(db_session, fake_redis, report_env):
    """恢复 normal 只改状态；已生成的报警不自动收敛，需人工确认或复位"""
    device = report_env["device"]
    await handle_device_report(db_session, fake_redis, report(device, alarm_type="fault"))
    alarm_id = (await _rows(db_session, Alarm, Alarm.device_id == device.id))[0].id

    result = await handle_device_report(db_session, fake_redis, report(device, status="normal"))
    assert result["status"] == "normal" and result["alarm_id"] is None
    assert result["alarm_created"] is False
    await db_session.refresh(device)
    assert device.status == "normal"
    assert await _count(db_session, Alarm, Alarm.id == alarm_id) == 1

    await fake_redis.flushall()
    again = await handle_device_report(db_session, fake_redis, report(device, status="normal"))
    assert again["status_changed"] is False
    assert await _stream_types(fake_redis) == []


async def test_report_rejects_unknown_and_retired(db_session, fake_redis, report_env):
    """未知设备 404、已退役设备拒收，last_report_at 只在成功上报时刷新"""
    device = report_env["device"]
    stale = datetime.utcnow() - timedelta(minutes=30)
    device.last_report_at = stale
    await db_session.commit()

    by_code = await handle_device_report(
        db_session,
        fake_redis,
        DeviceReportRequest(device_code="DEV-RPT-001", status="fault"),
    )
    assert by_code["device_id"] == device.id and by_code["status"] == "fault"
    await db_session.refresh(device)
    assert device.last_report_at > stale

    with pytest.raises(NotFoundError):
        await handle_device_report(
            db_session,
            fake_redis,
            DeviceReportRequest(device_code="DEV-NOT-EXIST", status="normal"),
        )
    with pytest.raises(NotFoundError):
        await handle_device_report(
            db_session, fake_redis, DeviceReportRequest(device_id=999999, status="normal")
        )

    device.status = "retired"
    await db_session.commit()
    with pytest.raises(AuthError) as exc:
        await handle_device_report(db_session, fake_redis, report(device, status="alarm"))
    assert exc.value.code == 400 and "退役" in exc.value.message


async def test_scan_offline_only_touches_reportable_devices(db_session, fake_redis, report_env):
    """离线扫描只处理有上报能力且超时的设备，已离线与从未上报的跳过"""
    org, device_type = report_env["org"], report_env["type"]
    stale = datetime.utcnow() - timedelta(minutes=10)
    quiet = await create_device(db_session, org, device_type, "DEV-QUIET", last_report_at=None)
    offline = await create_device(
        db_session, org, device_type, "DEV-OFF", status="offline", last_report_at=stale
    )
    lapsed = await create_device(
        db_session, org, device_type, "DEV-LAPSE", last_report_at=stale
    )

    results = await scan_offline_devices(db_session, fake_redis, threshold_seconds=180)

    assert [item["device_code"] for item in results] == ["DEV-LAPSE"]
    assert results[0]["old_status"] == "normal" and results[0]["alarm_id"] is not None
    await db_session.refresh(lapsed)
    await db_session.refresh(quiet)
    await db_session.refresh(offline)
    assert (lapsed.status, quiet.status, offline.status) == ("offline", "normal", "offline")

    logs = await _rows(db_session, DeviceStatusLog, DeviceStatusLog.device_id == lapsed.id)
    assert [(log.new_status, log.reason) for log in logs] == [
        ("offline", "心跳超时自动判定离线")
    ]
    alarms = await _rows(db_session, Alarm, Alarm.device_id == lapsed.id)
    assert [(a.alarm_type, a.status) for a in alarms] == [("fault", "pending")]
    assert await _stream_types(fake_redis) == ["device_status", "alarm_new"]

    await fake_redis.flushall()
    assert await scan_offline_devices(db_session, fake_redis, threshold_seconds=180) == []
    assert await _stream_types(fake_redis) == []


async def test_report_endpoint_switch_and_key(client, db_session, fake_redis, report_env, monkeypatch):
    """端点受 ALLOW_DEVICE_REPORT 开关与 X-Device-Key 双重保护"""
    device = report_env["device"]
    payload = {"device_id": device.id, "status": "alarm", "alarm_type": "fire"}

    monkeypatch.setattr(monitor_api.settings, "DEVICE_REPORT_KEY", "device-secret")
    monkeypatch.setattr(monitor_api.settings, "ALLOW_DEVICE_REPORT", True)

    missing = await client.post("/api/v1/monitor/report", json=payload)
    assert missing.status_code == 401 and missing.json()["code"] == 401

    wrong = await client.post(
        "/api/v1/monitor/report", json=payload, headers={"X-Device-Key": "nope"}
    )
    assert wrong.status_code == 401

    ok = await client.post(
        "/api/v1/monitor/report", json=payload, headers={"X-Device-Key": "device-secret"}
    )
    body = ok.json()
    assert body["code"] == 200
    assert body["data"]["status"] == "alarm" and body["data"]["alarm_created"] is True
    await db_session.refresh(device)
    assert device.status == "alarm"
    assert await _stream_types(fake_redis) == ["device_status", "alarm_new"]

    monkeypatch.setattr(monitor_api.settings, "ALLOW_DEVICE_REPORT", False)
    monkeypatch.setattr(monitor_api.settings, "DEBUG", False)
    closed = await client.post(
        "/api/v1/monitor/report", json=payload, headers={"X-Device-Key": "device-secret"}
    )
    assert closed.status_code == 200 and closed.json()["code"] == 404
