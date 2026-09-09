"""
实时推送 WebSocket 端点（3.3 B-14）

挂载在 `/ws/devices`，不走 `/api/v1` 前缀（PRD FR-013 给定的地址）。
握手用一次性 ticket（计划 3.3），重连用 last_msg_id 补发（PRD 2.2）。
"""

from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.redis import get_redis_pool
from app.db.session import get_db
from app.models.user import User
from app.services import event_stream, monitor_service, ws_broadcaster
from app.ws.auth import WS_CLOSE_UNAUTHORIZED, consume_ticket
from app.ws.connection_manager import WSConnection, manager

router = APIRouter()


async def _load_user(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def _replay(
    websocket: WebSocket, conn: WSConnection, redis: aioredis.Redis, last_msg_id: str
) -> None:
    """断线重连补发；超出上限或断点已被裁剪时要求前端走 REST 全量刷新"""
    ok, frames = await event_stream.plan_replay(redis, last_msg_id)
    if not ok:
        await websocket.send_json(
            event_stream.build_event(
                "resync_required",
                {"reason": "replay_overflow", "last_msg_id": last_msg_id},
            )
        )
        return
    for frame in frames:
        if conn.can_see(frame):
            await websocket.send_json(frame)


@router.websocket("/ws/devices")
async def devices_websocket(
    websocket: WebSocket,
    ticket: str | None = Query(None),
    last_msg_id: str | None = Query(None),
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> None:
    """设备状态与报警实时推送"""
    user_id = await consume_ticket(redis, ticket)
    if user_id is None:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return

    user = await _load_user(db, user_id)
    if user is None or user.status != "active":
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return

    org_ids = await monitor_service.resolve_visible_org_ids(db, user)
    await ws_broadcaster.ensure_running(redis)
    conn = await manager.connect(websocket, user, org_ids)
    manager.start_heartbeat()

    try:
        if last_msg_id:
            await _replay(websocket, conn, redis, last_msg_id)

        while True:
            payload = await websocket.receive_json()
            action = payload.get("action") if isinstance(payload, dict) else None
            if action == "ping":
                await conn.send(event_stream.build_event("pong", {}))
            elif action == "subscribe":
                conn.subscription = _subscription_of(payload)
                if conn.subscription.get("last_msg_id"):
                    await _replay(websocket, conn, redis, conn.subscription["last_msg_id"])
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - 协议错误/半开连接统一按断开处理
        pass
    finally:
        await manager.disconnect(conn.id)


def _subscription_of(payload: dict[str, Any]) -> dict[str, Any]:
    """只保留订阅控制帧里认识的键，避免任意字段驻留在连接上"""
    return {
        key: payload[key]
        for key in ("org_id", "bbox", "last_msg_id")
        if key in payload
    }
