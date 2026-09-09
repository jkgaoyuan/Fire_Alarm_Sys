"""
WebSocket 握手认证（3.3 计划 3.3 节）

浏览器 WebSocket 无法自定义请求头，Access Token 放 query 会进 Nginx access_log。
因此走「一次性 Ticket」：REST 侧用 Bearer 换 ticket，握手时只用一次即销毁。
"""

import secrets

import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()

TICKET_KEY_PREFIX = "ws_ticket:"

WS_CLOSE_UNAUTHORIZED = 4401


def _ticket_key(ticket: str) -> str:
    return f"{TICKET_KEY_PREFIX}{ticket}"


async def issue_ticket(redis: aioredis.Redis, user_id: int) -> str:
    """签发一次性握手 Ticket，TTL 内未使用自动失效"""
    ticket = secrets.token_urlsafe(24)
    await redis.set(_ticket_key(ticket), str(user_id), ex=settings.WS_TICKET_TTL_SECONDS)
    return ticket


async def consume_ticket(redis: aioredis.Redis, ticket: str | None) -> int | None:
    """
    校验并销毁 Ticket，返回 user_id；无效/已过期/已使用返回 None。
    使用 GETDEL 保证「一次握手一次消费」，并发重放时只有一次能拿到值。
    Redis < 6.2 无该命令时退回 GET + DELETE。
    """
    if not ticket:
        return None
    key = _ticket_key(ticket)
    try:
        value = await redis.getdel(key)
    except Exception:  # noqa: BLE001 - 服务端不支持 GETDEL
        value = await redis.get(key)
        if value is not None:
            await redis.delete(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
