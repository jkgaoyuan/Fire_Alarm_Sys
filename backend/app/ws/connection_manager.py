"""
WebSocket 连接管理（3.3 B-14）

职责：连接注册表、按用户数据权限过滤推送、心跳、故障连接摘除。
业务代码不直接调用本模块发消息——一律写 Redis Stream，由 ws_broadcaster 扇出，
以保证多进程（PRD 7 水平扩展）下每个 worker 都能把事件送达自己进程内的连接。
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from app.core.config import get_settings
from app.models.user import User
from app.services import event_stream

settings = get_settings()

# 连续写失败次数达到该值即摘除连接（计划 3.2 心跳节）
MAX_SEND_FAILURES = 2


@dataclass
class WSConnection:
    """单个客户端连接及其权限快照（握手时解析，之后不再查库）"""

    id: str
    websocket: WebSocket
    user_id: int
    username: str
    data_scope: str
    org_ids: set[int] | None
    failures: int = 0
    subscription: dict[str, Any] = field(default_factory=dict)

    @property
    def unrestricted(self) -> bool:
        return self.org_ids is None

    def can_see(self, frame: dict[str, Any]) -> bool:
        """
        数据权限过滤（计划 3.4）。
        事件 data 未带 org_id 时视为全局事件（心跳、统计聚合），不做过滤。
        """
        if self.org_ids is None:
            return True
        data = frame.get("data") or {}
        org_id = data.get("org_id")
        if org_id is None:
            return True
        try:
            return int(org_id) in self.org_ids
        except (TypeError, ValueError):
            return True

    async def send(self, frame: dict[str, Any]) -> bool:
        """发送一帧；成功清零失败计数，失败累加并返回是否应摘除"""
        try:
            await self.websocket.send_json(frame)
            self.failures = 0
            return True
        except Exception:  # noqa: BLE001 - 客户端断开形态多样，统一按失败处理
            self.failures += 1
            return False


class ConnectionManager:
    """进程内连接注册表"""

    def __init__(self) -> None:
        self._connections: dict[str, WSConnection] = {}
        self._heartbeat_task: asyncio.Task | None = None

    @property
    def count(self) -> int:
        return len(self._connections)

    def snapshot(self) -> list[WSConnection]:
        return list(self._connections.values())

    async def connect(
        self,
        websocket: WebSocket,
        user: User,
        org_ids: set[int] | None,
    ) -> WSConnection:
        await websocket.accept()
        conn = WSConnection(
            id=uuid.uuid4().hex,
            websocket=websocket,
            user_id=user.id,
            username=user.username,
            data_scope=user.data_scope,
            org_ids=org_ids,
        )
        self._connections[conn.id] = conn
        return conn

    async def disconnect(self, conn_id: str) -> None:
        self._connections.pop(conn_id, None)

    def evict(self, conn_id: str) -> None:
        """摘除已判定为失活的连接（不同步等待，供广播循环调用）"""
        self._connections.pop(conn_id, None)

    async def broadcast(self, frame: dict[str, Any]) -> int:
        """向所有可见连接扇出一帧，返回实际送达数。"""
        targets = [c for c in self.snapshot() if c.can_see(frame)]
        if not targets:
            return 0
        results = await asyncio.gather(
            *(c.send(frame) for c in targets), return_exceptions=True
        )
        delivered = 0
        for conn, ok in zip(targets, results):
            if ok is True:
                delivered += 1
            elif ok is False or ok is None:
                if conn.failures >= MAX_SEND_FAILURES:
                    self.evict(conn.id)
            else:  # gather(return_exceptions=True) 捕获的异常
                self.evict(conn.id)
        return delivered

    async def send_ping_frames(self) -> int:
        """
        一次心跳：向全部连接发 `pong`（计划 3.2：服务端每 30s 主动发送）。
        单独成方法便于测试直接调用而不必等 30 秒。
        """
        frame = event_stream.build_event("pong", {})
        return await self.broadcast(frame)

    async def heartbeat_loop(self) -> None:
        """后台心跳任务，随应用 lifespan 启停"""
        interval = settings.WS_HEARTBEAT_SECONDS
        try:
            while True:
                await asyncio.sleep(interval)
                if self._connections:
                    await self.send_ping_frames()
        except asyncio.CancelledError:
            return

    def start_heartbeat(self) -> None:
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self.heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        task = self._heartbeat_task
        self._heartbeat_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def close_all(self) -> None:
        for conn in self.snapshot():
            self.evict(conn.id)
            try:
                await conn.websocket.close()
            except Exception:  # noqa: BLE001 - 关停阶段忽略客户端异常
                pass


manager = ConnectionManager()
