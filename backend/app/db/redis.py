"""
Redis 连接管理
"""

import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()

# 全局 Redis 连接池（应用启动时初始化）
_redis_pool: aioredis.Redis | None = None


async def get_redis_pool() -> aioredis.Redis:
    """获取或初始化 Redis 连接"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


async def close_redis_pool() -> None:
    """关闭 Redis 连接"""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
