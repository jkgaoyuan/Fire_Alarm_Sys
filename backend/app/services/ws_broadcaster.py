"""
Stream → 本进程连接的扇出消费者（3.3 B-14，P2-008 多 worker 修正）

每个 worker 进程使用独立的消费者组（组名含 PID），这样 Redis 会把全量消息
投递给每一个 worker，各 worker 再按连接的数据权限在进程内扇出。
原先所有 worker 共用同一组名会导致每条消息只被一个 worker 消费，其余 worker
的连接收不到推送。

消费者任务在应用 lifespan 中 eager 启动（不再延迟到首次 WS 握手），
确保多 worker 部署时每个进程从启动就开始消费。
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


def group_name() -> str:
    """每进程独立的消费者组名，保证多 worker 下每个进程都收到全量消息。"""
    return f"{settings.WS_STREAM_GROUP}-{socket.gethostname()}-{os.getpid()}"


def consumer_name() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


async def ensure_running(redis: aioredis.Redis) -> None:
    """
    幂等启动扇出消费者；进程内只会存在一个任务。
    lifespan 阶段 eager 调用，WS 握手时也可能调用（兼容测试环境）。
    """
    global _task
    await event_stream.ensure_group(redis, group_name())
    async with _lock:
        if _task is not None and not _task.done():
            return
        _task = asyncio.create_task(run_broadcaster(redis), name="ws-broadcaster")


def is_running() -> bool:
    return _task is not None and not _task.done()


async def run_broadcaster(redis: aioredis.Redis) -> None:
    """持续消费事件流并扇出。异常退出的连接由 ConnectionManager 自行摘除。"""
    try:
        async for frame in event_stream.consume(
            redis, group_name(), consumer_name()
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
