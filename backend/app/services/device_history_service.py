"""
设备历史记录与历史轨迹（3.2 B-11 / FR-011、3.3 B-18 / FR-018）

聚合 `device_status_logs` / `alarms` / `repair_orders` / `inspection_records` 四张表。

3.4 巡检与 3.7 维修均已交付，四类数据源**全部可聚合**。此前那份
`PENDING_SOURCES` 声明与响应里的 `unavailable_sources` 字段是这两张表尚未建库时的
临时保护（避免前端把「无记录」误读成「无历史」），已于 2026-09-16 随接入一并移除。

`get_device_trajectory()` 是同一张 `device_status_logs` 的**单类别时序视图**：
带时间区间、分页与导出，供 FR-018 折线/甘特展示；与上方跨类别聚合共用数据源，不重复实现。
"""

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alarm import Alarm
from app.models.device import Device, DeviceStatusLog
from app.models.inspection import InspectionRecord
from app.models.repair import RepairOrder
from app.models.user import User
from app.services.device_service import apply_device_data_scope

TRAJECTORY_DEFAULT_DAYS = 7
TRAJECTORY_MAX_DAYS = 90
TRAJECTORY_MAX_EXPORT_ROWS = 10000

TRAJECTORY_HEADERS = ["时间", "原状态", "新状态", "变更原因", "操作人"]

STATUS_LABELS: dict[str, str] = {
    "normal": "正常",
    "alarm": "报警",
    "fault": "故障",
    "shield": "屏蔽",
    "offline": "离线",
    "retired": "已退役",
}


def _label(status: str | None) -> str:
    if not status:
        return "未知"
    return STATUS_LABELS.get(status, status)


ALARM_TYPE_LABELS: dict[str, str] = {
    "fire": "火警",
    "pre_fire": "预警",
    "fault": "故障",
    "shield": "屏蔽",
}

ALARM_STATUS_LABELS: dict[str, str] = {
    "pending": "待确认",
    "confirmed": "已确认",
    "false_alarm": "误报",
    "processing": "处理中",
    "resolved": "已解决",
}

INSPECTION_RESULT_LABELS: dict[str, str] = {
    "normal": "正常",
    "abnormal": "异常",
}

# 取值与 `app.models.repair.RepairOrderStatus` 一一对应
REPAIR_STATUS_LABELS: dict[str, str] = {
    "pending": "待处理",
    "assigned": "已派单",
    "repairing": "维修中",
    "pending_accept": "待验收",
    "completed": "已完成",
    "returned": "已退回",
}


async def _status_items(db: AsyncSession, device_id: int, limit: int) -> list[dict]:
    logs = (
        (
            await db.execute(
                select(DeviceStatusLog)
                .options(selectinload(DeviceStatusLog.changer))
                .where(DeviceStatusLog.device_id == device_id)
                .order_by(DeviceStatusLog.created_at.desc(), DeviceStatusLog.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    items: list[dict[str, Any]] = []
    for log in logs:
        new = _label(log.new_status)
        title = f"建档：{new}" if log.old_status is None else f"状态变更：{_label(log.old_status)} → {new}"
        items.append(
            {
                "category": "status_change",
                "title": title,
                "detail": log.reason,
                "operator": log.changer.real_name if log.changer else None,
                "created_at": log.created_at,
            }
        )
    return items


async def _alarm_items(db: AsyncSession, device_id: int, limit: int) -> list[dict]:
    alarms = (
        (
            await db.execute(
                select(Alarm)
                .options(selectinload(Alarm.confirmer))
                .where(Alarm.device_id == device_id)
                .order_by(Alarm.created_at.desc(), Alarm.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    items: list[dict[str, Any]] = []
    for alarm in alarms:
        kind = ALARM_TYPE_LABELS.get(alarm.alarm_type, alarm.alarm_type)
        state = ALARM_STATUS_LABELS.get(alarm.status, alarm.status)
        items.append(
            {
                "category": "alarm",
                "title": f"报警：{kind}",
                "detail": alarm.location_description or state,
                "operator": alarm.confirmer.real_name if alarm.confirmer else None,
                "created_at": alarm.created_at,
            }
        )
    return items


async def _inspection_items(db: AsyncSession, device_id: int, limit: int) -> list[dict]:
    """巡检记录（FR-034 / FR-036）。一条记录一条时间轴条目，与 `_alarm_items` 同粒度。"""
    records = (
        (
            await db.execute(
                select(InspectionRecord)
                .options(selectinload(InspectionRecord.inspector))
                .where(InspectionRecord.device_id == device_id)
                .order_by(
                    InspectionRecord.inspected_at.desc(), InspectionRecord.id.desc()
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    items: list[dict[str, Any]] = []
    for record in records:
        outcome = INSPECTION_RESULT_LABELS.get(record.result, record.result)
        items.append(
            {
                "category": "inspection",
                "title": f"巡检：{outcome}",
                "detail": record.abnormal_desc,
                "operator": record.inspector.real_name if record.inspector else None,
                "created_at": record.inspected_at,
            }
        )
    return items


async def _repair_items(db: AsyncSession, device_id: int, limit: int) -> list[dict]:
    """维修工单（FR-038 ~ FR-042）。

    每个工单只出一条条目，时间取**建单时间** —— 与报警「一条报警一条」的粒度一致。
    `assigned_at` / `completed_at` / `accepted_at` 不在时间轴上展开，
    它们在工单详情里看；展开会让条目数成倍增长且与其它类别粒度不齐。
    """
    orders = (
        (
            await db.execute(
                select(RepairOrder)
                .options(selectinload(RepairOrder.reporter))
                .where(RepairOrder.device_id == device_id)
                .order_by(RepairOrder.created_at.desc(), RepairOrder.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    items: list[dict[str, Any]] = []
    for order in orders:
        state = REPAIR_STATUS_LABELS.get(order.status, order.status)
        items.append(
            {
                "category": "repair",
                "title": f"维修：{order.order_no}（{state}）",
                "detail": order.fault_desc,
                "operator": order.reporter.real_name if order.reporter else None,
                "created_at": order.created_at,
            }
        )
    return items


async def get_device_history(
    db: AsyncSession, device_id: int, *, user: User, limit: int = 100
) -> dict[str, Any] | None:
    """按时间倒序返回设备历史。设备不存在、已逻辑删除或超出数据范围时返回 None。"""
    base = select(Device).where(Device.id == device_id, Device.is_deleted.is_(False))
    scoped = await apply_device_data_scope(base, user, db)
    device = (await db.execute(scoped)).scalar_one_or_none()
    if device is None:
        return None

    # 四类数据源各自取 limit 条后再合并截断，避免某一类记录过多把另一类完全挤出时间轴。
    #
    # 时间戳**一律原样透传，不做时区折算**：四个列在库里的类型完全一致
    # （均为 `timestamp with time zone`，实测 2026-09-16），响应里统一是带 `Z` 的
    # aware UTC。若只给新接入的两类做 naive 折算，会出现同一时间轴里两种时区的错乱。
    merged = await _status_items(db, device_id, limit)
    merged += await _alarm_items(db, device_id, limit)
    merged += await _inspection_items(db, device_id, limit)
    merged += await _repair_items(db, device_id, limit)
    merged.sort(key=lambda item: item["created_at"], reverse=True)
    items = merged[:limit]

    return {
        "device_id": device.id,
        "device_code": device.device_code,
        "total": len(items),
        "items": items,
    }


# ==================== 历史轨迹（B-18 / FR-018）====================


def normalize_utc(value: datetime | None) -> datetime | None:
    """带时区的入参折算为 naive UTC，与 `created_at` 的存储口径一致"""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def resolve_window(
    start: datetime | None, end: datetime | None
) -> tuple[datetime, datetime]:
    """
    轨迹查询区间：缺省近 7 天，跨度上限 90 天（计划 5.6）。

    非法区间抛 ValueError，由接口层转成 code=400，避免 service 依赖 HTTP 语义。
    """
    finish = normalize_utc(end) or datetime.utcnow()
    begin = normalize_utc(start) or finish - timedelta(days=TRAJECTORY_DEFAULT_DAYS)
    if begin >= finish:
        raise ValueError("开始时间必须早于结束时间")
    if finish - begin > timedelta(days=TRAJECTORY_MAX_DAYS):
        raise ValueError(f"查询区间不得超过 {TRAJECTORY_MAX_DAYS} 天")
    return begin, finish


def _point(log: DeviceStatusLog) -> dict[str, Any]:
    return {
        "time": log.created_at,
        "old_status": log.old_status,
        "new_status": log.new_status,
        "status_label": _label(log.new_status),
        "reason": log.reason,
        "operator": log.changer.real_name if log.changer else None,
    }


async def get_device_trajectory(
    db: AsyncSession,
    device_id: int,
    *,
    user: User,
    start: datetime,
    end: datetime,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any] | None:
    """
    单设备状态变化轨迹，按时间**升序**返回（供折线/甘特直接绘制）。

    设备不存在、已逻辑删除或超出数据范围返回 None。
    """
    base = select(Device).where(Device.id == device_id, Device.is_deleted.is_(False))
    scoped = await apply_device_data_scope(base, user, db)
    device = (await db.execute(scoped)).scalar_one_or_none()
    if device is None:
        return None

    conditions = [
        DeviceStatusLog.device_id == device_id,
        DeviceStatusLog.created_at >= start,
        DeviceStatusLog.created_at <= end,
    ]
    total = (
        await db.execute(
            select(func.count()).select_from(DeviceStatusLog).where(*conditions)
        )
    ).scalar_one()
    logs = (
        (
            await db.execute(
                select(DeviceStatusLog)
                .options(selectinload(DeviceStatusLog.changer))
                .where(*conditions)
                .order_by(DeviceStatusLog.created_at.asc(), DeviceStatusLog.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return {
        "device_id": device.id,
        "device_code": device.device_code,
        "device_name": device.device_name,
        "start": start,
        "end": end,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_point(log) for log in logs],
    }


def _row(point: dict[str, Any]) -> list[str]:
    return [
        point["time"].strftime("%Y-%m-%d %H:%M:%S") if point["time"] else "",
        _label(point["old_status"]),
        _label(point["new_status"]),
        point["reason"] or "",
        point["operator"] or "系统",
    ]


def build_trajectory_xlsx(payload: dict[str, Any]) -> bytes:
    """openpyxl 写内存工作簿（万行内同步导出足够）"""
    wb = Workbook()
    ws = wb.active
    ws.title = "历史轨迹"
    ws.append(TRAJECTORY_HEADERS)
    for point in payload["items"]:
        ws.append(_row(point))
    for index, width in enumerate((20, 10, 10, 30, 14), start=1):
        ws.column_dimensions[get_column_letter(index)].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_trajectory_csv(payload: dict[str, Any]) -> bytes:
    """utf-8-sig 便于 Excel 直接双击打开不乱码"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(TRAJECTORY_HEADERS)
    for point in payload["items"]:
        writer.writerow(_row(point))
    return buf.getvalue().encode("utf-8-sig")
