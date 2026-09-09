"""
WebSocket 实时推送（3.3 B-14）测试

覆盖：Ticket 换取与一次性、握手鉴权、状态/报警事件经 Stream 扇出到连接、
客户端 ping 与服务端心跳、断线重连补发、resync_required 两种触发条件。

端点函数直接作为协程被测：TestClient 的独立事件循环与 pytest-asyncio 的
aiosqlite 会话不同循环，跨循环复用会挂死（计划 10.2 的已知约束）。
"""

import asyncio

import pytest

from app.api.ws_devices import devices_websocket
from app.services import event_stream, ws_broadcaster
from app.services.device_report_service import handle_device_report
from app.ws import connection_manager as cm
from app.ws.auth import WS_CLOSE_UNAUTHORIZED, consume_ticket, issue_ticket
from app.ws.connection_manager import manager
from tests.device_helpers import create_device_type, create_device_user, create_org
from tests.monitor_helpers import FakeWebSocket, create_device, report, wait_until

_tasks: list[asyncio.Task] = []


@pytest.fixture(autouse=True)
async def ws_state():
    """每个用例后回收扇出任务、心跳与连接表，避免跨用例串推"""
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
async def ws_env(db_session):
    org = await create_org(db_session, "推送大楼")
    device_type = await create_device_type(db_session)
    device = await create_device(db_session, org, device_type, "DEV-WS-001")
    user = await create_device_user(db_session, username="ws_chief", data_scope="all")
    return {"org": org, "type": device_type, "device": device, "user": user}


async def _connect(db, redis, user_id: int, *, last_msg_id: str | None = None):
    ws = FakeWebSocket()
    ticket = await issue_ticket(redis, user_id)
    task = asyncio.create_task(
        devices_websocket(
            ws, ticket=ticket, last_msg_id=last_msg_id, redis=redis, db=db
        )
    )
    _tasks.append(task)
    assert await wait_until(lambda: ws.accepted), "握手未完成 accept"
    return ws, task


async def _disconnect(ws, task) -> None:
    ws.end()
    await asyncio.wait_for(task, timeout=2)


async def test_ws_ticket_is_one_time(fake_redis, ws_env):
    """Ticket 一次性：消费后立即失效，重放与空值都拿不到用户"""
    user = ws_env["user"]
    ticket = await issue_ticket(fake_redis, user.id)

    assert await fake_redis.ttl(f"ws_ticket:{ticket}") > 0
    assert await consume_ticket(fake_redis, ticket) == user.id
    assert await consume_ticket(fake_redis, ticket) is None
    assert await consume_ticket(fake_redis, None) is None
    assert await fake_redis.get(f"ws_ticket:{ticket}") is None


async def test_handshake_rejects_invalid_ticket(db_session, fake_redis, ws_env):
    """无效 Ticket 与停用用户都在 accept 前以 4401 关闭，不进入连接表"""
    anonymous = FakeWebSocket()
    await devices_websocket(anonymous, ticket=None, redis=fake_redis, db=db_session)
    assert anonymous.accepted is False and anonymous.closed_code == WS_CLOSE_UNAUTHORIZED

    replay = await issue_ticket(fake_redis, ws_env["user"].id)
    await consume_ticket(fake_redis, replay)
    reused = FakeWebSocket()
    await devices_websocket(reused, ticket=replay, redis=fake_redis, db=db_session)
    assert reused.closed_code == WS_CLOSE_UNAUTHORIZED

    user = ws_env["user"]
    user.status = "disabled"
    await db_session.commit()
    disabled = FakeWebSocket()
    ticket = await issue_ticket(fake_redis, user.id)
    await devices_websocket(disabled, ticket=ticket, redis=fake_redis, db=db_session)
    assert disabled.accepted is False and disabled.closed_code == WS_CLOSE_UNAUTHORIZED
    assert manager.count == 0


async def test_report_events_fan_out_to_client(db_session, fake_redis, ws_env):
    """上报 → XADD → 消费者组扇出 → 连接收到 device_status 与 alarm_new"""
    env = ws_env
    ws, task = await _connect(db_session, fake_redis, env["user"].id)

    result = await handle_device_report(
        db_session, fake_redis, report(env["device"], alarm_type="fire")
    )
    assert await wait_until(lambda: {"device_status", "alarm_new"} <= set(ws.types()))

    status_frame = ws.frames_of("device_status")[0]
    assert status_frame["data"]["status"] == "alarm"
    assert status_frame["data"]["old_status"] == "normal"
    assert status_frame["data"]["org_id"] == env["org"].id

    alarm_frame = ws.frames_of("alarm_new")[0]
    assert alarm_frame["data"]["alarm_type"] == "fire"
    assert alarm_frame["data"]["alarm_id"] == result["alarm_id"]
    assert alarm_frame["id"] and alarm_frame["ts"]

    await _disconnect(ws, task)
    assert manager.count == 0


async def test_client_ping_and_server_heartbeat(db_session, fake_redis, ws_env, monkeypatch):
    """客户端 ping 立刻回 pong；服务端按 WS_HEARTBEAT_SECONDS 主动推送心跳"""
    ws, task = await _connect(db_session, fake_redis, ws_env["user"].id)

    ws.push({"action": "ping"})
    assert await wait_until(lambda: ws.frames_of("pong"))
    assert ws.frames_of("pong")[0]["data"] == {}
    before = len(ws.frames_of("pong"))

    monkeypatch.setattr(cm.settings, "WS_HEARTBEAT_SECONDS", 0.05)
    await manager.stop_heartbeat()
    manager.start_heartbeat()
    assert await wait_until(lambda: len(ws.frames_of("pong")) > before), "心跳未按间隔推送"

    await _disconnect(ws, task)


async def test_reconnect_replays_missed_frames(db_session, fake_redis, ws_env):
    """携带 last_msg_id 重连时只补发断点之后的事件，且保持区域过滤"""
    org_id = ws_env["org"].id
    first = await event_stream.publish(fake_redis, "device_status", {"seq": 1, "org_id": org_id})
    await event_stream.publish(fake_redis, "device_status", {"seq": 2, "org_id": org_id})
    await event_stream.publish(fake_redis, "alarm_new", {"seq": 3, "org_id": org_id})

    ws, task = await _connect(
        db_session, fake_redis, ws_env["user"].id, last_msg_id=first
    )
    assert await wait_until(lambda: len(ws.sent) == 2)
    assert [frame["data"]["seq"] for frame in ws.sent] == [2, 3]
    assert ws.types() == ["device_status", "alarm_new"]

    # 会话期间的增量事件继续推送，不会因补发而中断
    await event_stream.publish(fake_redis, "alarm_new", {"seq": 4, "org_id": org_id})
    assert await wait_until(lambda: len(ws.sent) == 3)
    await _disconnect(ws, task)


async def test_replay_overflow_and_trimmed_breakpoint_require_resync(
    db_session, fake_redis, ws_env, monkeypatch
):
    """待补发超上限、或断点已被 MAXLEN 裁剪时，回 resync_required 而不是静默漏推"""
    org_id = ws_env["org"].id
    monkeypatch.setattr(event_stream.settings, "WS_REPLAY_LIMIT", 2)
    first = await event_stream.publish(fake_redis, "device_status", {"seq": 1, "org_id": org_id})
    for seq in range(2, 6):
        await event_stream.publish(fake_redis, "device_status", {"seq": seq, "org_id": org_id})

    overflow, task = await _connect(db_session, fake_redis, ws_env["user"].id, last_msg_id=first)
    assert await wait_until(lambda: overflow.frames_of("resync_required"))
    assert len(overflow.sent) == 1
    frame = overflow.frames_of("resync_required")[0]
    assert frame["data"]["reason"] == "replay_overflow"
    assert frame["data"]["last_msg_id"] == first
    await _disconnect(overflow, task)

    # 放宽上限，让「断点已被裁剪」这条分支单独成立
    monkeypatch.setattr(event_stream.settings, "WS_REPLAY_LIMIT", 50)
    stale, task = await _connect(db_session, fake_redis, ws_env["user"].id, last_msg_id="1-1")
    assert await wait_until(lambda: stale.frames_of("resync_required"))
    assert stale.frames_of("resync_required")[0]["data"]["reason"] == "replay_overflow"
    await _disconnect(stale, task)
