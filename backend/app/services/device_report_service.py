"""
设备上报与报警生成服务（3.3 B-13）

上报入口抽象成纯 service 函数：模拟器（B-19）进程内直调，HTTP 端点（受开关保护）
与后续 MQTT 适配层都只做协议转换，业务逻辑不重复。

事务边界遵循计划 六.1：devices 更新 + 状态日志 + alarms 插入同事务，
XADD 放在 commit 之后，推送失败不回滚业务。
"""

from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthError, NotFoundError
from app.crud.alarm import alarm_crud
from app.crud.device import device_crud
from app.models.alarm import ALARM_TYPE_PROFILE
from app.models.device import DEVICE_STATUSES, Device
from app.schemas.alarm import DeviceReportRequest
from app.services import alarm_service
from app.services.device_service import write_status_log

REPORT_LOG_REASON = "设备上报"


def _utc_now() -> datetime:
    """naive UTC，与 Base.created_at 的 datetime.utcnow 口径一致（SQLite 无时区偏移）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


async def _load_device(db: AsyncSession, payload: DeviceReportRequest) -> Device:
    stmt = (
        select(Device)
        .options(selectinload(Device.org))
        .where(Device.is_deleted.is_(False))
    )
    if payload.device_id is not None:
        stmt = stmt.where(Device.id == payload.device_id)
    else:
        stmt = stmt.where(Device.device_code == payload.device_code)
    device = (await db.execute(stmt)).scalar_one_or_none()
    if device is None:
        raise NotFoundError("设备不存在或未建档")
    return device


def _target_status(payload: DeviceReportRequest) -> str:
    """
    解析上报后的设备状态：
    报警类型优先（fire/pre_fire → alarm），它决定了大屏着色，不能被上报里
    滞后的 status 字段覆盖。
    """
    if payload.alarm_type:
        profile = ALARM_TYPE_PROFILE.get(payload.alarm_type)
        if profile is None:
            raise AuthError(400, f"未知报警类型: {payload.alarm_type}")
        return profile["device_status"]
    if payload.status not in DEVICE_STATUSES:
        raise AuthError(400, f"未知设备状态: {payload.status}")
    return payload.status


async def handle_device_report(
    db: AsyncSession,
    redis: aioredis.Redis | None,
    payload: DeviceReportRequest,
    *,
    reason: str = REPORT_LOG_REASON,
) -> dict:
    """
    处理一次设备上报。返回：
    {device_id, device_code, old_status, status, status_changed, alarm_id, alarm_created}
    """
    if payload.device_id is None and not payload.device_code:
        raise AuthError(400, "device_id 与 device_code 至少提供一个")

    device = await _load_device(db, payload)
    if device.status == "retired":
        raise AuthError(400, "设备已退役，不再接收上报")

    new_status = _target_status(payload)
    old_status = device.status
    reported_at = _to_utc(payload.reported_at) if payload.reported_at else _utc_now()

    device.status = new_status
    device.last_report_at = reported_at
    db.add(device)

    status_changed = new_status != old_status
    if status_changed:
        await write_status_log(
            db,
            device_id=device.id,
            old_status=old_status,
            new_status=new_status,
            changed_by=None,
            reason=reason,
        )

    alarm = None
    alarm_created = False
    if payload.alarm_type:
        alarm, alarm_created = await alarm_service.raise_alarm(
            db,
            device,
            payload.alarm_type,
            is_drill=payload.is_drill,
            location_description=payload.location_description,
        )

    await db.commit()

    result = {
        "device_id": device.id,
        "device_code": device.device_code,
        "old_status": old_status,
        "status": new_status,
        "status_changed": status_changed,
        "alarm_id": alarm.id if alarm else None,
        "alarm_created": alarm_created,
    }

    if status_changed:
        reloaded = await device_crud.get_with_relations(db, device.id)
        await alarm_service.publish(
            redis, "device_status", alarm_service.device_payload(reloaded, old_status, reason)
        )
    if alarm is not None and alarm_created:
        fresh = await alarm_crud.get_with_relations(db, alarm.id)
        await alarm_service.publish(redis, "alarm_new", alarm_service.alarm_payload(fresh))

    return result


# ==================== 离线检测 ====================


async def scan_offline_devices(
    db: AsyncSession,
    redis: aioredis.Redis | None,
    *,
    threshold_seconds: int,
) -> list[dict]:
    """
    把「有上报能力但超时无上报」的设备置为 offline 并生成 fault 报警。

    `last_report_at IS NULL` 的设备跳过：3.2 建档的历史设备没有上报通道，
    一律判离线会把整本档案刷成红色（无回读通道，OQ-2 同源问题）。
    """
    cutoff = _utc_now() - timedelta(seconds=threshold_seconds)
    stmt = (
        select(Device)
        .options(selectinload(Device.org))
        .where(
            Device.is_deleted.is_(False),
            Device.last_report_at.is_not(None),
            Device.last_report_at < cutoff,
            Device.status.notin_(["offline", "retired"]),
        )
    )
    devices = list((await db.execute(stmt)).scalars().all())

    results: list[dict] = []
    for device in devices:
        old_status = device.status
        device.status = "offline"
        db.add(device)
        await write_status_log(
            db,
            device_id=device.id,
            old_status=old_status,
            new_status="offline",
            changed_by=None,
            reason="心跳超时自动判定离线",
        )
        alarm, created = await alarm_service.raise_alarm(db, device, "fault")
        results.append(
            {
                "device_id": device.id,
                "device_code": device.device_code,
                "old_status": old_status,
                "alarm_id": alarm.id if created else None,
            }
        )

    if not results:
        return []

    await db.commit()

    for item in results:
        reloaded = await device_crud.get_with_relations(db, item["device_id"])
        await alarm_service.publish(
            redis,
            "device_status",
            alarm_service.device_payload(reloaded, item["old_status"], "心跳超时"),
        )
        if item["alarm_id"]:
            fresh = await alarm_crud.get_with_relations(db, item["alarm_id"])
            await alarm_service.publish(redis, "alarm_new", alarm_service.alarm_payload(fresh))
    return results
