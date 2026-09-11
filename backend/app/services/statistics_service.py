"""
统计聚合服务（3.9 FR-048 ~ FR-051）
========================================
提供 4 个看板的聚合查询：
- 设备完好率（FR-048）
- 报警趋势（FR-049）
- 故障 TOP10（FR-050）
- 巡检完成率（FR-051）
- 综合概览（overview）
"""

from datetime import datetime, timedelta, date
from typing import Optional

from sqlalchemy import case, cast, func, select, and_, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alarm import Alarm
from app.models.device import Device
from app.models.inspection import InspectionTask
from app.models.organization import Organization
from app.models.repair import RepairOrder


async def get_device_status_distribution(
    db: AsyncSession,
    org_id: Optional[int] = None,
    include_drill: bool = False,
) -> dict:
    """设备完好率看板（FR-048）

    按 devices.status 分组计数，排除已删除和已退役设备。
    支持按区域下钻（org_id 过滤）。

    返回：
    {
        "items": [{"status": "normal", "count": 100, "label": "正常"}, ...],
        "total": 150
    }
    """
    stmt = (
        select(Device.status, func.count(Device.id).label("cnt"))
        .where(Device.is_deleted == False)
        .where(Device.status != "retired")
        .group_by(Device.status)
    )

    if org_id:
        # 递归查子组织
        org_ids = await _get_subtree_org_ids(db, org_id)
        stmt = stmt.where(Device.org_id.in_(org_ids))

    result = await db.execute(stmt)
    rows = result.all()

    status_labels = {
        "normal": "正常",
        "alarm": "报警",
        "fault": "故障",
        "shield": "屏蔽",
        "offline": "离线",
    }

    items = [
        {"status": row.status, "count": row.cnt, "label": status_labels.get(row.status, row.status)}
        for row in rows
    ]
    total = sum(item["count"] for item in items)

    return {"items": items, "total": total}


async def get_alarm_trend(
    db: AsyncSession,
    days: int = 7,
    org_id: Optional[int] = None,
    include_drill: bool = False,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    """报警趋势图（FR-049）

    按日期 + alarm_type 分组统计报警数量。
    默认近 7 天（OQ-1），可切换 30/90 天。

    返回：
    {
        "dates": ["2026-09-01", "2026-09-02", ...],
        "series": [
            {"type": "fire", "data": [5, 3, ...]},
            {"type": "fault", "data": [10, 8, ...]},
        ]
    }
    """
    if start and end:
        date_from = datetime.combine(start, datetime.min.time())
        date_to = datetime.combine(end, datetime.max.time())
    else:
        date_to = datetime.utcnow()
        date_from = date_to - timedelta(days=days)

    stmt = (
        select(
            func.date(Alarm.created_at).label("alarm_date"),
            Alarm.alarm_type,
            func.count(Alarm.id).label("cnt"),
        )
        .where(Alarm.created_at >= date_from)
        .where(Alarm.created_at <= date_to)
        .group_by(func.date(Alarm.created_at), Alarm.alarm_type)
        .order_by(func.date(Alarm.created_at))
    )

    if not include_drill:
        stmt = stmt.where(Alarm.is_drill == False)

    if org_id:
        org_ids = await _get_subtree_org_ids(db, org_id)
        stmt = stmt.where(Alarm.org_id.in_(org_ids))

    result = await db.execute(stmt)
    rows = result.all()

    # 构建日期序列
    if start and end:
        d = start
        dates = []
        while d <= end:
            dates.append(d.isoformat())
            d += timedelta(days=1)
    else:
        dates = []
        d = date_from.date()
        while d <= date_to.date():
            dates.append(d.isoformat())
            d += timedelta(days=1)

    # 按类型分组
    type_data: dict[str, dict[str, int]] = {}
    for row in rows:
        alarm_date = str(row.alarm_date)
        alarm_type = row.alarm_type
        if alarm_type not in type_data:
            type_data[alarm_type] = {}
        type_data[alarm_type][alarm_date] = row.cnt

    series = []
    for alarm_type, date_counts in type_data.items():
        data = [date_counts.get(d, 0) for d in dates]
        series.append({"type": alarm_type, "data": data})

    return {"dates": dates, "series": series}


async def get_fault_top10(
    db: AsyncSession,
    org_id: Optional[int] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    """故障 TOP10（FR-050）

    按 repair_orders.device_id 计数，取前 10。
    过滤条件：status='completed'、source != 'drill'（is_drill 不适用 repair，无需过滤）。

    返回：
    {
        "items": [
            {"device_id": 1, "device_code": "DEV-001", "device_name": "...", "fault_count": 15},
            ...
        ]
    }
    """
    stmt = (
        select(
            RepairOrder.device_id,
            Device.device_code,
            Device.device_name,
            func.count(RepairOrder.id).label("fault_count"),
        )
        .join(Device, RepairOrder.device_id == Device.id)
        .where(RepairOrder.status == "completed")
        .group_by(RepairOrder.device_id, Device.device_code, Device.device_name)
        .order_by(func.count(RepairOrder.id).desc())
        .limit(10)
    )

    if start:
        stmt = stmt.where(RepairOrder.completed_at >= datetime.combine(start, datetime.min.time()))
    if end:
        stmt = stmt.where(RepairOrder.completed_at <= datetime.combine(end, datetime.max.time()))

    if org_id:
        org_ids = await _get_subtree_org_ids(db, org_id)
        stmt = stmt.where(Device.org_id.in_(org_ids))

    result = await db.execute(stmt)
    rows = result.all()

    items = [
        {
            "device_id": row.device_id,
            "device_code": row.device_code,
            "device_name": row.device_name,
            "fault_count": row.fault_count,
        }
        for row in rows
    ]

    return {"items": items}


async def get_inspection_completion(
    db: AsyncSession,
    org_id: Optional[int] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    """巡检完成率（FR-051）

    按责任人统计：completed / (completed + missed) = 完成率。

    返回：
    {
        "items": [
            {
                "responsible_user_id": 1,
                "responsible_name": "张三",
                "total": 100,
                "completed": 85,
                "missed": 10,
                "pending": 5,
                "completion_rate": 0.895
            },
            ...
        ],
        "overall": {
            "total": 500,
            "completed": 400,
            "missed": 50,
            "pending": 50,
            "completion_rate": 0.889
        }
    }
    """
    from app.models.user import User

    stmt = (
        select(
            InspectionTask.responsible_user_id,
            User.real_name,
            func.count(InspectionTask.id).label("total"),
            func.count(case((InspectionTask.status == "completed", 1))).label("completed"),
            func.count(case((InspectionTask.status == "missed", 1))).label("missed"),
            func.count(case((InspectionTask.status == "pending", 1))).label("pending"),
        )
        .outerjoin(User, InspectionTask.responsible_user_id == User.id)
        .group_by(InspectionTask.responsible_user_id, User.real_name)
    )

    if start:
        stmt = stmt.where(InspectionTask.task_date >= start)
    if end:
        stmt = stmt.where(InspectionTask.task_date <= end)

    if org_id:
        # 通过巡检计划的 org_id 过滤
        from app.models.inspection import InspectionPlan
        stmt = stmt.join(InspectionPlan, InspectionTask.plan_id == InspectionPlan.id)
        org_ids = await _get_subtree_org_ids(db, org_id)
        stmt = stmt.where(InspectionPlan.org_id.in_(org_ids))

    result = await db.execute(stmt)
    rows = result.all()

    items = []
    overall_total = 0
    overall_completed = 0
    overall_missed = 0
    overall_pending = 0

    for row in rows:
        finished = row.completed + row.missed
        rate = round(row.completed / finished, 3) if finished > 0 else 0.0
        items.append({
            "responsible_user_id": row.responsible_user_id,
            "responsible_name": row.real_name or "未分配",
            "total": row.total,
            "completed": row.completed,
            "missed": row.missed,
            "pending": row.pending,
            "completion_rate": rate,
        })
        overall_total += row.total
        overall_completed += row.completed
        overall_missed += row.missed
        overall_pending += row.pending

    overall_finished = overall_completed + overall_missed
    overall_rate = round(overall_completed / overall_finished, 3) if overall_finished > 0 else 0.0

    return {
        "items": items,
        "overall": {
            "total": overall_total,
            "completed": overall_completed,
            "missed": overall_missed,
            "pending": overall_pending,
            "completion_rate": overall_rate,
        },
    }


async def get_overview(
    db: AsyncSession,
    org_id: Optional[int] = None,
) -> dict:
    """综合概览卡片

    返回：
    {
        "device_total": 500,
        "device_normal_rate": 0.92,
        "alarm_today": 5,
        "alarm_pending": 3,
        "inspection_today_total": 20,
        "inspection_today_completed": 15,
        "repair_pending": 8
    }
    """
    # 设备总数与完好率
    device_stmt = select(func.count(Device.id)).where(
        Device.is_deleted == False,
        Device.status != "retired",
    )
    normal_stmt = select(func.count(Device.id)).where(
        Device.is_deleted == False,
        Device.status != "retired",
        Device.status == "normal",
    )

    if org_id:
        org_ids = await _get_subtree_org_ids(db, org_id)
        device_stmt = device_stmt.where(Device.org_id.in_(org_ids))
        normal_stmt = normal_stmt.where(Device.org_id.in_(org_ids))

    device_total = (await db.execute(device_stmt)).scalar() or 0
    normal_count = (await db.execute(normal_stmt)).scalar() or 0
    normal_rate = round(normal_count / device_total, 3) if device_total > 0 else 0.0

    # 今日报警
    today_start = datetime.combine(date.today(), datetime.min.time())
    alarm_today_stmt = select(func.count(Alarm.id)).where(
        Alarm.created_at >= today_start,
        Alarm.is_drill == False,
    )
    alarm_pending_stmt = select(func.count(Alarm.id)).where(
        Alarm.status == "pending",
        Alarm.is_drill == False,
    )
    if org_id:
        alarm_today_stmt = alarm_today_stmt.where(Alarm.org_id.in_(org_ids))
        alarm_pending_stmt = alarm_pending_stmt.where(Alarm.org_id.in_(org_ids))

    alarm_today = (await db.execute(alarm_today_stmt)).scalar() or 0
    alarm_pending = (await db.execute(alarm_pending_stmt)).scalar() or 0

    # 今日巡检
    insp_total_stmt = select(func.count(InspectionTask.id)).where(
        InspectionTask.task_date == date.today()
    )
    insp_done_stmt = select(func.count(InspectionTask.id)).where(
        InspectionTask.task_date == date.today(),
        InspectionTask.status == "completed",
    )
    insp_today_total = (await db.execute(insp_total_stmt)).scalar() or 0
    insp_today_completed = (await db.execute(insp_done_stmt)).scalar() or 0

    # 待处理维修
    repair_stmt = select(func.count(RepairOrder.id)).where(
        RepairOrder.status.in_(["pending", "assigned", "repairing"])
    )
    repair_pending = (await db.execute(repair_stmt)).scalar() or 0

    return {
        "device_total": device_total,
        "device_normal_rate": normal_rate,
        "alarm_today": alarm_today,
        "alarm_pending": alarm_pending,
        "inspection_today_total": insp_today_total,
        "inspection_today_completed": insp_today_completed,
        "repair_pending": repair_pending,
    }


async def _get_subtree_org_ids(db: AsyncSession, org_id: int) -> list[int]:
    """递归获取组织及其所有子节点的 ID 列表"""
    cte = (
        select(Organization.id)
        .where(Organization.id == org_id)
        .cte(recursive=True)
    )
    cte = cte.union_all(
        select(Organization.id).where(Organization.parent_id == cte.c.id)
    )
    result = await db.execute(select(cte.c.id))
    return [row[0] for row in result.all()]
