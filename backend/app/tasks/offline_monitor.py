"""
设备离线检测任务（3.3 B-13）

Celery 尚未引入（计划 12 节 A-11 / 13 节 OQ-5），先用 lifespan asyncio 循环顶替。
`scan_once()` 是幂等入口，将来换 Celery Beat 时只需把它包成 task。
"""

import asyncio

from app.core.config import get_settings
from app.db.redis import get_redis_pool
from app.db.session import AsyncSessionLocal
from app.services.device_report_service import scan_offline_devices

settings = get_settings()

_task: asyncio.Task | None = None


async def scan_once() -> int:
    """执行一轮离线扫描，返回被判离线的设备数"""
    async with AsyncSessionLocal() as db:
        redis = await get_redis_pool()
        results = await scan_offline_devices(
            db, redis, threshold_seconds=settings.OFFLINE_THRESHOLD_SECONDS
        )
    if results:
        print(f"[INFO] 离线扫描置 offline: {len(results)} 台")
    return len(results)


async def _loop() -> None:
    interval = settings.OFFLINE_SCAN_INTERVAL_SECONDS
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await scan_once()
            except Exception as exc:  # noqa: BLE001 - 单轮失败不能让任务静默消失
                print(f"[WARN] 离线扫描失败: {type(exc).__name__}: {exc}")
    except asyncio.CancelledError:
        return


def start() -> None:
    """幂等启动；OFFLINE_SCAN_ENABLED=false 时不注册（测试环境）"""
    global _task
    if not settings.OFFLINE_SCAN_ENABLED:
        return
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(), name="offline-monitor")


async def stop() -> None:
    global _task
    task, _task = _task, None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
