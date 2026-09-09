"""
Stream → 本进程连接的扇出消费者（3.3 B-14）

每进程一个消费者（consumer name 含 hostname+pid+随机后缀），读到的是全量消息，
再按各连接的数据权限在进程内扇出。这样多 worker 部署时每个 worker 都能推自己
持有的连接，等价于 PRD 9 的 Redis Pub/Sub 广播，且天然可补发。

消费者任务在首个 WebSocket 握手时惰性启动：lifespan 阶段还没有 Redis 依赖注入
覆盖（测试环境），握手时启动可以让生产与测试走同一条路径。
"""

import asyncio
import os
import socket
import uuid

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.services import event_stream
from app.ws.connection_manager import manager

settings = get_settings()

_task: asyncio.Task | None = None
_lock = asyncio.Lock()


def consumer_name() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


async def ensure_running(redis: aioredis.Redis) -> None:
    """
    幂等启动扇出消费者；进程内只会存在一个任务。

    消费者组以 `$` 为起始游标，因此建组必须在本函数返回前同步完成：
    否则「握手成功 → 后台任务被调度 → 建组」之间写入的事件会被游标跳过，
    客户端连上却收不到任何推送。
    """
    global _task
    await event_stream.ensure_group(redis, settings.WS_STREAM_GROUP)
    async with _lock:
        if _task is not None and not _task.done():
            return
        _task = asyncio.create_task(run_broadcaster(redis), name="ws-broadcaster")


async def run_broadcaster(redis: aioredis.Redis) -> None:
    """持续消费事件流并扇出。异常退出的连接由 ConnectionManager 自行摘除。"""
    try:
        async for frame in event_stream.consume(
            redis, settings.WS_STREAM_GROUP, consumer_name()
        ):
            await manager.broadcast(frame)
    except asyncio.CancelledError:
        return
    except Exception as exc:  # noqa: BLE001 - 消费者崩溃不能带走应用
        print(f"[WARN] ws broadcaster stopped: {type(exc).__name__}: {exc}")


async def shutdown() -> None:
    global _task
    task, _task = _task, None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
