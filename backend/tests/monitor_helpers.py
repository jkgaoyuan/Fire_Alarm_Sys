"""
3.3 实时监控与电子地图测试共用工具

构造设备档案 + 上报载荷，并提供 FakeWebSocket，
使 WS 端点可以直接作为协程被测（避免 TestClient 的跨事件循环共享 aiosqlite 会话）。
"""

import asyncio
from typing import Any

from fastapi import WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alarm import Alarm
from app.models.device import Device
from app.models.device_type import DeviceType
from app.models.organization import Organization
from app.schemas.alarm import DeviceReportRequest

MONITOR_PERMS = [
    "monitor:view",
    "monitor:config",
    "alarm:view",
    "alarm:confirm",
    "alarm:silence",
    "alarm:reset",
    "device:view",
]

ALARM_ONLY_PERMS = ["alarm:view", "alarm:confirm", "alarm:silence", "alarm:reset"]


async def create_device(
    db: AsyncSession,
    org: Organization,
    device_type: DeviceType,
    code: str = "DEV-MON-001",
    **kwargs: Any,
) -> Device:
    """直接落库的设备（不经 3.2 接口，避免为实时测试引入档案权限依赖）"""
    device = Device(
        device_code=code,
        device_name=kwargs.pop("device_name", f"{code} 探测器"),
        type_id=device_type.id,
        org_id=org.id,
        status=kwargs.pop("status", "normal"),
        attributes=kwargs.pop("attributes", {}),
        **kwargs,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


def report(device: Device, **kwargs: Any) -> DeviceReportRequest:
    """构造上报请求（默认只带状态，报警类型/演练按需覆盖）"""
    kwargs.setdefault("device_id", device.id)
    return DeviceReportRequest(**kwargs)


async def create_alarm(
    db: AsyncSession,
    device: Device,
    alarm_type: str = "fire",
    **kwargs: Any,
) -> Alarm:
    """落一条报警（跳过上报链路，用于单测处置动作）"""
    from app.models.alarm import ALARM_TYPE_PROFILE

    alarm = Alarm(
        device_id=device.id,
        org_id=device.org_id,
        device_code=device.device_code,
        alarm_type=alarm_type,
        alarm_level=kwargs.pop("alarm_level", ALARM_TYPE_PROFILE[alarm_type]["alarm_level"]),
        status=kwargs.pop("status", "pending"),
        **kwargs,
    )
    db.add(alarm)
    await db.commit()
    await db.refresh(alarm)
    return alarm


class _End:
    """receive_json 收到该哨兵即按客户端断开处理"""


END = _End()


class FakeWebSocket:
    """
    最小 WebSocket 替身。

    队列驱动而非按预置列表返回：真实连接的收消息循环会一直挂起，
    测试才能在 handler 运行期间继续上报事件、再断言下行帧。
    """

    def __init__(self, incoming: list[Any] | None = None):
        self._queue: asyncio.Queue = asyncio.Queue()
        for message in incoming or []:
            self._queue.put_nowait(message)
        self.accepted = False
        self.closed_code: int | None = None
        self.sent: list[dict[str, Any]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int | None = None) -> None:
        self.closed_code = code

    async def receive_json(self) -> Any:
        item = await self._queue.get()
        if isinstance(item, _End):
            raise WebSocketDisconnect()
        return item

    async def send_json(self, data: Any) -> None:
        self.sent.append(data)

    def push(self, message: Any) -> None:
        self._queue.put_nowait(message)

    def end(self) -> None:
        self._queue.put_nowait(END)

    def frames_of(self, event_type: str) -> list[dict[str, Any]]:
        return [frame for frame in self.sent if frame.get("type") == event_type]

    def types(self) -> list[str]:
        return [frame.get("type") for frame in self.sent]


async def wait_until(predicate, *, timeout: float = 3.0, interval: float = 0.02) -> bool:
    """轮询等待条件成立（用于等待后台扇出任务把帧投递到连接）"""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()
