"""
WebSocket 数据权限过滤（3.3 B-14 / 计划 3.4、OQ-1）测试

覆盖：all/dept/self 三种口径下连接收到的事件集合差异、
越权区域报警不推送、区域外设备状态变化静默、无 org_id 的全局帧不过滤。
"""

import asyncio

import pytest

from app.api.ws_devices import devices_websocket
from app.services import event_stream, ws_broadcaster
from app.services.device_report_service import handle_device_report
from app.ws.auth import issue_ticket
from app.ws.connection_manager import manager
from tests.device_helpers import create_device_type, create_device_user, create_org
from tests.monitor_helpers import FakeWebSocket, create_device, report, wait_until

_tasks: list[asyncio.Task] = []


@pytest.fixture(autouse=True)
async def ws_state():
    _tasks.clear()
    yield
    for task in _tasks:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    await ws_broadcaster.shutdown()
    await manager.stop_heartbeat()
    await manager.close_all()


@pytest.fixture
async def scope_env(db_session):
    building_a = await create_org(db_session, "A 栋")
    building_b = await create_org(db_session, "B 栋")
    device_type = await create_device_type(db_session)
    device_a = await create_device(db_session, building_a, device_type, "DEV-A-001")
    device_b = await create_device(db_session, building_b, device_type, "DEV-B-001")
    chief = await create_device_user(db_session, username="scope_chief", data_scope="all")
    officer_a = await create_device_user(
        db_session, username="scope_officer_a", data_scope="dept", org=building_a
    )
    self_user = await create_device_user(
        db_session, username="scope_self", data_scope="self", org=building_a
    )
    homeless = await create_device_user(
        db_session, username="scope_homeless", data_scope="dept", org=None
    )
    return {
        "a": building_a,
        "b": building_b,
        "type": device_type,
        "device_a": device_a,
        "device_b": device_b,
        "chief": chief,
        "officer_a": officer_a,
        "self_user": self_user,
        "homeless": homeless,
    }


async def _connect(db, redis, user_id: int) -> FakeWebSocket:
    ws = FakeWebSocket()
    ticket = await issue_ticket(redis, user_id)
    _tasks.append(
        asyncio.create_task(
            devices_websocket(ws, ticket=ticket, redis=redis, db=db)
        )
    )
    assert await wait_until(lambda: ws.accepted)
    return ws


async def _codes(ws, event_type: str = "device_status") -> list[str]:
    await asyncio.sleep(0.1)  # 扇出任务异步投递，先让事件落地
    return [
        frame["data"]["device_code"]
        for frame in ws.frames_of(event_type)
        if frame["data"].get("device_code")
    ]


async def test_dept_connection_only_receives_own_region(db_session, fake_redis, scope_env):
    """dept 用户只收到本区域事件，all 用户收到全部"""
    chief_ws = await _connect(db_session, fake_redis, scope_env["chief"].id)
    officer_ws = await _connect(db_session, fake_redis, scope_env["officer_a"].id)
    assert manager.count == 2

    await handle_device_report(db_session, fake_redis, report(scope_env["device_a"], status="fault"))
    await handle_device_report(db_session, fake_redis, report(scope_env["device_b"], status="alarm", alarm_type="fire"))

    assert await wait_until(lambda: len(chief_ws.frames_of("device_status")) == 2)
    assert await _codes(chief_ws) == ["DEV-A-001", "DEV-B-001"]
    assert await _codes(officer_ws) == ["DEV-A-001"]
    assert len(officer_ws.frames_of("alarm_new")) == 0
    assert len(chief_ws.frames_of("alarm_new")) == 1
    assert chief_ws.frames_of("alarm_new")[0]["data"]["org_id"] == scope_env["b"].id


async def test_self_scope_degrades_to_region(db_session, fake_redis, scope_env):
    """OQ-1：自动上报的报警没有 created_by，self 在实时场景按区域口径降级为 dept"""
    self_ws = await _connect(db_session, fake_redis, scope_env["self_user"].id)
    officer_ws = await _connect(db_session, fake_redis, scope_env["officer_a"].id)

    await handle_device_report(
        db_session, fake_redis, report(scope_env["device_a"], alarm_type="pre_fire")
    )

    assert await wait_until(lambda: self_ws.frames_of("alarm_new"))
    assert [f["data"]["device_code"] for f in self_ws.frames_of("alarm_new")] == ["DEV-A-001"]
    assert await _codes(self_ws) == await _codes(officer_ws)


async def test_unrestricted_lookup_without_org_receives_no_scoped_event(
    db_session, fake_redis, scope_env
):
    """dept 但无归属区域 → 可见集合为空：区域类事件全部静默，全局帧仍可送达"""
    ws = await _connect(db_session, fake_redis, scope_env["homeless"].id)

    await handle_device_report(db_session, fake_redis, report(scope_env["device_a"], status="fault"))
    await handle_device_report(db_session, fake_redis, report(scope_env["device_b"], status="offline"))
    await event_stream.publish(fake_redis, "device_status", {"device_code": "no-org"})

    assert await wait_until(lambda: len(ws.frames_of("device_status")) == 1)
    assert ws.frames_of("device_status")[0]["data"]["device_code"] == "no-org"

    await manager.send_ping_frames()
    assert await wait_until(lambda: ws.frames_of("pong"))


async def test_out_of_region_alarm_is_silent_for_dept(
    db_session, fake_redis, scope_env
):
    """区域外报警与复位事件不会进入受限连接（越权不泄露存在性）"""
    officer_ws = await _connect(db_session, fake_redis, scope_env["officer_a"].id)
    chief_ws = await _connect(db_session, fake_redis, scope_env["chief"].id)

    result = await handle_device_report(
        db_session, fake_redis, report(scope_env["device_b"], alarm_type="fire")
    )
    assert await wait_until(lambda: chief_ws.frames_of("alarm_new"))

    alarm_id = result["alarm_id"]
    await event_stream.publish(
        fake_redis,
        "alarm_silenced",
        {"alarm_id": alarm_id, "org_id": scope_env["b"].id},
    )
    await asyncio.sleep(0.15)

    assert officer_ws.types() == []
    assert [f["type"] for f in chief_ws.sent] == ["device_status", "alarm_new", "alarm_silenced"]
    assert chief_ws.frames_of("alarm_silenced")[0]["data"]["alarm_id"] == alarm_id
