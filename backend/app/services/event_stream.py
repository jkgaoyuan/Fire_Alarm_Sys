"""
实时事件流（3.3 B-14）

Redis Stream 作为唯一写入缓冲：业务侧只 XADD，不直接触碰 WebSocket 连接。
- 断线重连补发依赖 XRANGE（PRD 2.2 的 last_msg_id 语义）
- 多实例广播依赖每个进程各自持有一个消费者组的 consumer（等价于 PRD 9 的 Pub/Sub 方案，且可补发）
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()

PAYLOAD_FIELD = "payload"
TYPE_FIELD = "type"
TS_FIELD = "ts"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_event(event_type: str, data: dict[str, Any], entry_id: str = "") -> dict[str, Any]:
    """帧协议见计划 3.2：{id, type, ts, data}，id 由 Stream 分配后回填"""
    return {
        "id": entry_id,
        "type": event_type,
        "ts": now_iso(),
        "data": data or {},
    }


async def publish(
    redis: aioredis.Redis,
    event_type: str,
    data: dict[str, Any],
) -> str:
    """写入事件流，返回 Stream entry id（即前端 last_msg_id）。"""
    entry_id = await redis.xadd(
        settings.WS_STREAM_KEY,
        {
            TYPE_FIELD: event_type,
            TS_FIELD: now_iso(),
            PAYLOAD_FIELD: json.dumps(data or {}, default=str),
        },
        maxlen=settings.WS_STREAM_MAXLEN,
        approximate=True,
    )
    return entry_id if isinstance(entry_id, str) else entry_id.decode()


async def read_after(
    redis: aioredis.Redis,
    last_msg_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    """
    读取 last_msg_id 之后至多 limit 条消息，返回完整帧列表（按时间正序）。
    优先使用 Redis 6.2+ 的 '(' 开区间语法（服务端即完成截断）；
    部分实现（老版本 fakeredis）不接受该语法，退回全量扫描 + 本地比较。
    """
    if not last_msg_id or last_msg_id in ("0", "0-0"):
        return []

    try:
        raw = await redis.xrange(
            settings.WS_STREAM_KEY, min=f"({last_msg_id}", max="+", count=limit
        )
        return [_decode(entry) for entry in raw]
    except Exception:  # noqa: BLE001 - 语法不受支持时走兜底，不影响正确性
        pass

    raw = await redis.xrange(settings.WS_STREAM_KEY, min="-", max="+", count=None)
    frames = [_decode(entry) for entry in raw]
    return [f for f in frames if _cmp_id(f["id"], last_msg_id) > 0][:limit]


async def plan_replay(
    redis: aioredis.Redis,
    last_msg_id: str,
    limit: int | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    """
    补发决策：返回 (是否可增量补发, 帧列表)。

    两种情况必须让前端走 REST 全量刷新（resync_required）：
    1. 待补发条数超过 limit（PRD 2.2 的补发上限）；
    2. 客户端断点已被 MAXLEN 裁剪掉，服务端无法证明中间没有空洞。
    """
    cap = limit or settings.WS_REPLAY_LIMIT
    if not last_msg_id or last_msg_id in ("0", "0-0"):
        return True, []

    frames = await read_after(redis, last_msg_id, cap + 1)
    if len(frames) > cap:
        return False, []

    earliest = await _earliest_id(redis)
    if earliest and _cmp_id(earliest, last_msg_id) > 0:
        return False, []
    return True, frames


async def _earliest_id(redis: aioredis.Redis) -> str | None:
    raw = await redis.xrange(settings.WS_STREAM_KEY, min="-", max="+", count=1)
    if not raw:
        return None
    entry_id = raw[0][0]
    return entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)


def _decode(entry: Any) -> dict[str, Any]:
    entry_id, fields = entry[0], entry[1]
    if isinstance(entry_id, bytes):
        entry_id = entry_id.decode()
    frame = {"id": entry_id, "type": "", "ts": now_iso(), "data": {}}
    for key, value in fields.items():
        name = key.decode() if isinstance(key, bytes) else key
        text = value.decode() if isinstance(value, bytes) else value
        if name == TYPE_FIELD:
            frame["type"] = text
        elif name == TS_FIELD:
            frame["ts"] = text
        elif name == PAYLOAD_FIELD:
            try:
                frame["data"] = json.loads(text)
            except (TypeError, ValueError):
                frame["data"] = {}
    return frame


def _cmp_id(left: str, right: str) -> int:
    """Stream id（ms-seq）比较，右边界为空时视为最小"""

    def parse(value: str) -> tuple[int, int]:
        if not value:
            return (0, -1)
        head, _, tail = str(value).partition("-")
        try:
            return (int(head), int(tail or 0))
        except ValueError:
            return (0, 0)

    a, b = parse(left), parse(right)
    return -1 if a < b else (1 if a > b else 0)


async def ensure_group(redis: aioredis.Redis, group: str) -> None:
    """创建消费者组；已存在时静默忽略（容器每次重启都会执行）"""
    try:
        await redis.xgroup_create(
            settings.WS_STREAM_KEY, groupname=group, id="$", mkstream=True
        )
    except Exception as exc:  # noqa: BLE001 - BUSYGROUP 是真 Redis 与 fakeredis 的共同表现
        if "BUSYGROUP" not in str(exc):
            raise


async def consume(
    redis: aioredis.Redis,
    group: str,
    consumer: str,
    batch_size: int = 50,
    block_ms: int = 2000,
) -> AsyncIterator[dict[str, Any]]:
    """
    以消费者身份持续拉取事件。每个进程一个消费者，读到的是全量消息。
    XREADGROUP 只能读到未投递的消息，因此进程启动前的历史消息由 XRANGE 补发兜底。
    """
    await ensure_group(redis, group)
    while True:
        response = await redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={settings.WS_STREAM_KEY: ">"},
            count=batch_size,
            block=block_ms,
        )
        if not response:
            # 真 Redis 这里已经阻塞满 block_ms，多睡 20ms 无感；
            # 但 fakeredis 的 BLOCK 立即返回，不让出事件循环会把测试跑成空转。
            await asyncio.sleep(0.02)
            continue
        for _stream, messages in response:
            for entry in messages:
                frame = _decode(entry)
                yield frame
                await redis.xack(settings.WS_STREAM_KEY, group, frame["id"])
