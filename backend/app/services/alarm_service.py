"""
报警服务层（3.3 B-12 / B-16）

写入路径只有两条：设备上报（device_report_service）与人工处置（confirm/silence/reset）。
两者都在事务提交后 XADD 事件，推送失败不回滚业务（计划 六.1）。
"""

from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import false, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.config import get_settings
from app.core.exceptions import AuthError, NotFoundError
from app.crud.alarm import alarm_crud
from app.models.alarm import (
    ALARM_STATUS_TRANSITIONS,
    ALARM_TYPE_PROFILE,
    Alarm,
    can_transition,
)
from app.models.device import Device
from app.models.user import User
from app.schemas.alarm import AlarmConfirmRequest, AlarmResetRequest
from app.services import event_stream
from app.services.device_service import write_status_log
from app.services.emergency_service import create_emergency_event
from app.services.monitor_service import resolve_visible_org_ids

settings = get_settings()

# 屏蔽需走解除屏蔽流程、已退役设备不参与复位（计划 5.5.5）
RESET_FORBIDDEN_DEVICE_STATUS = {"retired", "shield"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).astimezone().isoformat(timespec="seconds") if value else None


# ==================== 数据权限 ====================


async def visible_org_ids(db: AsyncSession, user: User) -> set[int] | None:
    """用户可见区域集合；None 表示不受限（data_scope='all'）"""
    return await resolve_visible_org_ids(db, user)


def scope_by_org(stmt: Select, org_ids: set[int] | None) -> Select:
    """按已解析的可见区域集合给 org_id 列加过滤（org_id 为 NULL 的记录受限用户不可见）"""
    if org_ids is None:
        return stmt
    if not org_ids:
        return stmt.where(false())
    return stmt.where(Alarm.org_id.in_(org_ids))


def is_org_visible(org_id: int | None, org_ids: set[int] | None) -> bool:
    """单条记录可见性判定（详情接口用，避免为一条记录再拼 SQL）"""
    if org_ids is None:
        return True
    return org_id is not None and org_id in org_ids


# ==================== 事件载荷 ====================


def alarm_payload(alarm: Alarm, device: Device | None = None) -> dict[str, Any]:
    """
    帧 data 载荷（计划 3.2 帧协议）。
    org_id 必须带上：WS 连接按它做数据权限过滤。
    device / org 关系需调用方预加载，async 下不能依赖懒加载。
    """
    device = device if device is not None else alarm.device
    org = alarm.org
    return {
        "alarm_id": alarm.id,
        "device_id": alarm.device_id,
        "device_code": alarm.device_code,
        "device_name": device.device_name if device else None,
        "org_id": alarm.org_id,
        "org_name": org.org_name if org else None,
        "alarm_type": alarm.alarm_type,
        "alarm_level": alarm.alarm_level,
        "status": alarm.status,
        "location_description": alarm.location_description,
        "map_x": float(device.map_x) if device is not None and device.map_x is not None else None,
        "map_y": float(device.map_y) if device is not None and device.map_y is not None else None,
        "created_at": _iso(alarm.created_at),
        "is_drill": bool(alarm.is_drill),
        "silenced": alarm.silenced_at is not None,
    }


def device_payload(device: Device, old_status: str | None, reason: str) -> dict[str, Any]:
    """`device_status` 帧载荷：统计卡片与地图点位着色只需要这几个字段"""
    return {
        "device_id": device.id,
        "device_code": device.device_code,
        "device_name": device.device_name,
        "org_id": device.org_id,
        "old_status": old_status,
        "status": device.status,
        "map_x": float(device.map_x) if device.map_x is not None else None,
        "map_y": float(device.map_y) if device.map_y is not None else None,
        "reason": reason,
        "reported_at": _iso(device.last_report_at),
    }


async def publish(redis: aioredis.Redis | None, event_type: str, data: dict) -> str | None:
    """写事件流；redis 为空（离线脚本）或 Redis 故障时静默降级，不影响业务事务"""
    if redis is None:
        return None
    try:
        return await event_stream.publish(redis, event_type, data)
    except Exception as exc:  # noqa: BLE001 - 推送失败绝不能回滚已提交的消防业务数据
        print(f"[WARN] 事件推送失败 {event_type}: {type(exc).__name__}: {exc}")
        return None


# ==================== 报警生成 ====================


async def raise_alarm(
    db: AsyncSession,
    device: Device,
    alarm_type: str,
    *,
    is_drill: bool = False,
    location_description: str | None = None,
    created_by: int | None = None,
) -> tuple[Alarm, bool]:
    """
    生成报警，返回 (报警, 是否新建)。

    同设备同类型存在未收敛报警时只返回既有记录（模拟器 1s 一报即触发去重）；
    已确认的报警不会被后续上报降级回 pending——人工处置结果优先。
    """
    profile = ALARM_TYPE_PROFILE.get(alarm_type)
    if profile is None:
        raise AuthError(400, f"未知报警类型: {alarm_type}")

    existing = await alarm_crud.find_open(db, device.id, alarm_type)
    if existing is not None:
        return existing, False

    alarm = Alarm(
        device_id=device.id,
        org_id=device.org_id,
        device_code=device.device_code,
        alarm_type=alarm_type,
        alarm_level=profile["alarm_level"],
        status="pending",
        location_description=location_description,
        is_drill=is_drill,
        pending_since=_utc_now(),
        created_by=created_by,
    )
    db.add(alarm)
    await db.flush()
    return alarm, True


# ==================== 人工处置 ====================


async def confirm_alarm(
    db: AsyncSession,
    redis: aioredis.Redis | None,
    alarm_id: int,
    user: User,
    payload: AlarmConfirmRequest,
) -> Alarm:
    """
    FR-025/FR-026 确认；真实火警在**同一事务内**开启应急处置闭环（3.5-B2 / FR-027）。

    确认与建事件不可分割：先 flush 事件再 commit，避免「报警已确认、事件没建」
    的中间态 —— 这个中间态正是本接线长期缺失时的表现。
    """
    alarm = await get_alarm_for_user(db, alarm_id, user)

    target = "false_alarm" if payload.confirm_result == "false_alarm" else "confirmed"
    if not can_transition(alarm.status, target):
        raise AuthError(400, f"报警当前状态 {alarm.status}，不可确认为 {target}")

    # 演练告警不是真实火警，不能走「现场属实」：3.8 口径下它本就不建应急事件，
    # 放行只会得到一条与处置台账对不上的确认记录。误报路径仍然开放，
    # 否则演练告警会永久卡在 pending。
    if target == "confirmed" and alarm.is_drill:
        raise AuthError(400, "演练告警不能确认为真实火警")

    alarm.status = target
    alarm.confirmed_by = user.id
    alarm.confirmed_at = _utc_now()
    alarm.confirm_result = payload.confirm_result
    if target == "false_alarm":
        alarm.false_reason = payload.false_reason
    db.add(alarm)

    event = None
    if target == "confirmed":
        event = await create_emergency_event(db, alarm.id, user.id)

    await db.commit()

    fresh = await alarm_crud.reload(db, alarm_id)
    await publish(redis, "alarm_confirmed", alarm_payload(fresh))
    # 事件推送放在 commit 之后：推送失败不能回滚已提交的确认与事件
    if event is not None:
        await publish(
            redis,
            "emergency_new",
            {
                "event_id": event.id,
                "event_no": event.event_no,
                "alarm_id": alarm_id,
                "org_id": fresh.org_id,
                "created_by": user.id,
            },
        )
    return fresh


async def silence_alarm(
    db: AsyncSession,
    redis: aioredis.Redis | None,
    alarm_id: int,
    user: User,
) -> Alarm:
    """
    FR-016.1 单条消音：只留痕、不改 status（报警仍需被看见）。
    重复消音幂等返回且不再广播，避免多端反复触发停止音频。
    """
    alarm = await get_alarm_for_user(db, alarm_id, user)
    if alarm.silenced_at is not None:
        return alarm

    alarm.silenced_by = user.id
    alarm.silenced_at = _utc_now()
    db.add(alarm)
    await db.commit()

    fresh = await alarm_crud.reload(db, alarm_id)
    await publish(
        redis,
        "alarm_silenced",
        {
            "alarm_id": fresh.id,
            "device_id": fresh.device_id,
            "org_id": fresh.org_id,
            "silenced_by": fresh.silenced_by,
            "silenced_at": _iso(fresh.silenced_at),
        },
    )
    return fresh


async def reset_alarm(
    db: AsyncSession,
    redis: aioredis.Redis | None,
    alarm_id: int,
    user: User,
    payload: AlarmResetRequest,
) -> Alarm:
    """
    FR-016.2 系统复位（计划 5.5 规则）。
    跨表事务：报警置 resolved + 设备回 normal + 状态日志，三者同提交。
    """
    if not payload.physical_restored:
        raise AuthError(400, "必须确认设备物理状态已恢复正常后方可复位")

    alarm = await get_alarm_for_user(db, alarm_id, user)
    device = alarm.device
    if device is None:
        raise AuthError(400, "报警关联设备不存在，无法复位")
    if device.status in RESET_FORBIDDEN_DEVICE_STATUS:
        label = "已退役" if device.status == "retired" else "屏蔽中"
        raise AuthError(400, f"设备{label}，禁止系统复位")

    if alarm.status == "resolved":
        return alarm  # 并发/重复复位幂等

    _ensure_physically_restored(device)

    if not can_transition(alarm.status, "resolved"):
        raise AuthError(400, f"报警当前状态 {alarm.status}，不可复位")

    now = _utc_now()
    alarm.status = "resolved"
    alarm.resolved_at = now
    alarm.pending_since = None
    alarm.reset_by = user.id
    alarm.reset_at = now
    alarm.reset_remark = payload.remark
    db.add(alarm)

    old_status = device.status
    if old_status != "normal":
        device.status = "normal"
        db.add(device)
        await write_status_log(
            db,
            device_id=device.id,
            old_status=old_status,
            new_status="normal",
            changed_by=user.id,
            reason="系统复位",
        )

    await db.commit()

    fresh = await alarm_crud.reload(db, alarm_id)
    await publish(redis, "alarm_reset", alarm_payload(fresh))
    if old_status != "normal":
        await publish(
            redis, "device_status", device_payload(fresh.device, old_status, "系统复位")
        )
    return fresh


def _ensure_physically_restored(device: Device) -> None:
    """
    5.5 判定：上报新鲜时以设备当前状态为准；
    无回读通道（last_report_at 为空或已过期）时靠显式勾选 + 审计留痕放行（OQ-2）。
    """
    if device.last_report_at is None:
        return
    fresh = (
        _utc_now() - _as_utc(device.last_report_at)
    ).total_seconds() <= settings.OFFLINE_THRESHOLD_SECONDS
    if fresh and device.status != "normal":
        raise AuthError(400, "设备物理状态未恢复，禁止复位")


# ==================== 查询 ====================


async def get_alarm_for_user(db: AsyncSession, alarm_id: int, user: User) -> Alarm:
    """按数据权限取单条报警；不可见一律 404，不泄露存在性"""
    org_ids = await visible_org_ids(db, user)
    alarm = await alarm_crud.get_with_relations(db, alarm_id)
    if alarm is None or not is_org_visible(alarm.org_id, org_ids):
        raise NotFoundError("报警记录不存在")
    return alarm


async def list_alarms(
    db: AsyncSession,
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    alarm_type: str | None = None,
    alarm_level: str | None = None,
    status: str | None = None,
    org_id: int | None = None,
    device_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    include_drill: bool = False,
) -> tuple[list[Alarm], int]:
    """报警中心分页筛选（计划 5.2）"""
    stmt = alarm_crud.with_relations()
    if alarm_type:
        stmt = stmt.where(Alarm.alarm_type == alarm_type)
    if alarm_level:
        stmt = stmt.where(Alarm.alarm_level == alarm_level)
    if status:
        stmt = stmt.where(Alarm.status.in_(_split(status, ALARM_STATUS_TRANSITIONS)))
    if org_id is not None:
        stmt = stmt.where(Alarm.org_id == org_id)
    if device_id is not None:
        stmt = stmt.where(Alarm.device_id == device_id)
    if start is not None:
        stmt = stmt.where(Alarm.created_at >= start)
    if end is not None:
        stmt = stmt.where(Alarm.created_at <= end)
    if not include_drill:
        stmt = stmt.where(Alarm.is_drill.is_(False))

    org_ids = await visible_org_ids(db, user)
    stmt = scope_by_org(stmt, org_ids)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(
        stmt.order_by(Alarm.created_at.desc(), Alarm.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(result.scalars().unique().all())
    return items, total


def _split(value: str, allowed: Any) -> list[str]:
    """逗号分隔多值筛选，忽略非法值"""
    allowed_set = set(allowed)
    return [v.strip() for v in value.split(",") if v.strip() in allowed_set]
