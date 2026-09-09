"""
实时监控服务层（3.3 B-14 / B-15）

本文件承载监控侧的读查询：可见区域解析、大屏统计、TopN 报警、地图点位。

数据权限与报警侧统一走 `resolve_visible_org_ids`（OQ-1 口径：按设备归属区域过滤），
不复用 `apply_data_scope`——它对 `self` 走 created_by 过滤，自动上报的报警会被全部屏蔽；
且大屏的聚合查询（`select(func.count())`）不满足该函数对 `select(Model)` 形态的要求（计划 六.7）。
"""

from math import floor

from sqlalchemy import case, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.models.alarm import OPEN_ALARM_STATUSES, Alarm
from app.models.device import Device
from app.models.organization import Organization
from app.models.user import User
from app.schemas.alarm import DashboardOut, MapDevicesOut, MapDeviceOut, MapMetaOut

# 视口点位上限，超限改为网格聚合返回（FR-015 性能优化）
MAP_RENDER_LIMIT = 500
# 网格聚合的分桶数（视口 10x10）
GRID_BUCKETS = 10


async def resolve_descendant_org_ids(db: AsyncSession, org_id: int) -> list[int]:
    """递归取 org_id 及其全部后代区域 id（含自身）"""
    cte = select(Organization.id).where(Organization.id == org_id).cte(recursive=True)
    cte = cte.union_all(
        select(Organization.id).where(Organization.parent_id == cte.c.id)
    )
    result = await db.execute(select(cte.c.id))
    return [row[0] for row in result.all()]


async def resolve_visible_org_ids(db: AsyncSession, user: User) -> set[int] | None:
    """
    返回用户可见的区域 id 集合；None 表示不受限（data_scope='all'）。

    OQ-1 默认口径：报警/监控一律按**设备归属区域**过滤，
    因此 `self` 在实时场景降级为 `dept`（自动上报的报警没有 created_by）。
    """
    if user.data_scope == "all":
        return None
    if user.org_id is None:
        return set()
    return set(await resolve_descendant_org_ids(db, user.org_id))


def is_org_allowed(org_id: int | None, visible: set[int] | None) -> bool:
    """区域级越权拦截：受限用户只能定位到自己可见范围内的楼层"""
    if visible is None:
        return True
    return org_id is not None and org_id in visible


def scope_org_ids(
    visible: set[int] | None,
    target: int | None,
    target_descendants: list[int] | None = None,
) -> list[int] | None:
    """
    计算一次查询实际生效的区域集合。
    None = 不加区域限制；空列表 = 该用户看不到任何数据。
    """
    if visible is None:
        if target is None:
            return None
        return target_descendants if target_descendants is not None else [target]
    if target is None:
        return sorted(visible)
    allowed = set(target_descendants if target_descendants is not None else [target])
    return sorted(allowed & visible)


def apply_org_filter(stmt: Select, org_ids: list[int] | None) -> Select:
    """按区域集合过滤 Alarm/Device.org_id；org_id 为 NULL 的档案对受限用户不可见"""
    if org_ids is None:
        return stmt
    if not org_ids:
        return stmt.where(false())
    return stmt.where(Alarm.org_id.in_(org_ids))


async def _targets_for(
    db: AsyncSession, visible: set[int] | None, org_id: int | None
) -> list[int] | None:
    descendants = await resolve_descendant_org_ids(db, org_id) if org_id is not None else None
    return scope_org_ids(visible, org_id, descendants)


# ==================== 大屏统计 ====================


async def get_dashboard(
    db: AsyncSession, user: User, org_id: int | None = None
) -> DashboardOut:
    """
    FR-014 统计卡片。

    `online` = 总数 - offline - retired：3.2 的 devices.status 没有 online 取值，
    报警/故障/屏蔽设备仍在上报、仍属在线（A-13 引入 last_report_at 后的口径）。
    """
    visible = await resolve_visible_org_ids(db, user)
    target_ids = await _targets_for(db, visible, org_id)

    stmt = select(Device.status, func.count(Device.id).label("cnt")).where(
        Device.is_deleted.is_(False)
    )
    if target_ids is not None:
        if not target_ids:
            stmt = stmt.where(false())
        else:
            stmt = stmt.where(Device.org_id.in_(target_ids))

    rows = (await db.execute(stmt.group_by(Device.status))).all()
    status_counts = {status: int(cnt) for status, cnt in rows}
    total = sum(status_counts.values())
    offline = status_counts.get("offline", 0)
    retired = status_counts.get("retired", 0)

    alarm_stmt = (
        select(func.count())
        .select_from(Alarm)
        .where(Alarm.is_drill.is_(False), Alarm.status == "pending")
    )
    if target_ids is not None:
        alarm_stmt = (
            alarm_stmt.where(false())
            if not target_ids
            else alarm_stmt.where(Alarm.org_id.in_(target_ids))
        )
    pending_alarm = int((await db.execute(alarm_stmt)).scalar() or 0)
    pending_fire = int(
        (await db.execute(alarm_stmt.where(Alarm.alarm_type == "fire"))).scalar() or 0
    )

    return DashboardOut(
        total=total,
        online=total - offline - retired,
        offline=offline,
        alarm=status_counts.get("alarm", 0),
        fault=status_counts.get("fault", 0),
        shield=status_counts.get("shield", 0),
        retired=retired,
        normal=status_counts.get("normal", 0),
        pending_alarm=pending_alarm,
        pending_fire=pending_fire,
        status_counts=status_counts,
    )


# ==================== TopN 报警 ====================


async def get_recent_alarms(
    db: AsyncSession,
    user: User,
    *,
    limit: int = 20,
    org_id: int | None = None,
    include_drill: bool = False,
) -> list[Alarm]:
    """
    FR-014 大屏报警 TopN。
    置顶规则：`status='pending' AND alarm_type='fire'` 排最前，其次按时间倒序。
    """
    visible = await resolve_visible_org_ids(db, user)
    if org_id is not None and not is_org_allowed(org_id, visible):
        return []
    target_ids = await _targets_for(db, visible, org_id)

    pending_fire_first = case(
        ((Alarm.status == "pending") & (Alarm.alarm_type == "fire"), 0), else_=1
    )

    stmt = apply_org_filter(select(Alarm), target_ids)
    if not include_drill:
        stmt = stmt.where(Alarm.is_drill.is_(False))
    stmt = (
        stmt.options(selectinload(Alarm.device), selectinload(Alarm.org))
        .order_by(pending_fire_first, Alarm.created_at.desc(), Alarm.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


# ==================== 平面图 ====================


async def get_org(db: AsyncSession, org_id: int) -> Organization | None:
    return (
        await db.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()


async def resolve_map_owner(db: AsyncSession, org: Organization) -> Organization | None:
    """
    平面图继承规则（计划 5.4）：设备挂在 zone 叶子、平面图挂在 floor，
    因此从给定节点向上找**最近**持有平面图的祖先（含自身）。找不到返回 None。
    """
    current: Organization | None = org
    seen: set[int] = set()
    while current is not None and current.id not in seen:
        if current.map_image_url:
            return current
        if current.parent_id is None:
            return None
        seen.add(current.id)
        current = await get_org(db, current.parent_id)
    return None


async def get_map_meta(db: AsyncSession, user: User, org_id: int) -> MapMetaOut | None:
    """FR-015 平面图元数据（含继承解析结果）；区域不可见或不存在返回 None"""
    visible = await resolve_visible_org_ids(db, user)
    if not is_org_allowed(org_id, visible):
        return None

    org = await get_org(db, org_id)
    if org is None:
        return None

    owner = await resolve_map_owner(db, org)
    if owner is None:
        return MapMetaOut(org_id=org.id, org_name=org.org_name)

    return MapMetaOut(
        org_id=org.id,
        org_name=org.org_name,
        resolved_org_id=owner.id,
        resolved_org_name=owner.org_name,
        map_image_url=owner.map_image_url,
        map_image_width=owner.map_image_width,
        map_image_height=owner.map_image_height,
        map_origin=owner.map_origin or "top_left",
    )


# ==================== 地图点位 ====================


async def get_map_devices(
    db: AsyncSession,
    user: User,
    *,
    org_id: int | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = MAP_RENDER_LIMIT,
) -> MapDevicesOut:
    """
    FR-015 视口内设备点位。
    `org_id` 语义为「定位到该楼层」：先按继承规则解析持图楼层，再展开其全部后代区域。
    点位数超过 limit 时改为网格聚合，返回桶代表点（aggregated=True）。
    """
    visible = await resolve_visible_org_ids(db, user)
    if org_id is not None:
        if not is_org_allowed(org_id, visible):
            return MapDevicesOut(items=[], total=0, limit=limit)
        org = await get_org(db, org_id)
        if org is None:
            return MapDevicesOut(items=[], total=0, limit=limit)
        owner = await resolve_map_owner(db, org)
        org_id = owner.id if owner else org_id

    target_ids = await _targets_for(db, visible, org_id)

    stmt = (
        select(Device)
        .options(selectinload(Device.device_type))
        .where(
            Device.is_deleted.is_(False),
            Device.status != "retired",
            Device.map_x.is_not(None),
            Device.map_y.is_not(None),
        )
    )
    if target_ids is not None:
        stmt = stmt.where(false()) if not target_ids else stmt.where(
            Device.org_id.in_(target_ids)
        )
    if bbox is not None:
        xmin, ymin, xmax, ymax = bbox
        stmt = stmt.where(Device.map_x >= xmin, Device.map_x <= xmax).where(
            Device.map_y >= ymin, Device.map_y <= ymax
        )

    total = int((await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0)
    rows = list((await db.execute(stmt.order_by(Device.id))).scalars().all())

    active = await _active_alarm_map(db, [d.id for d in rows])
    items = [_map_point(d, active.get(d.id)) for d in rows]

    if total > limit:
        return MapDevicesOut(
            items=_aggregate_grid(items, bbox, limit),
            total=total,
            aggregated=True,
            bbox=list(bbox) if bbox else None,
            limit=limit,
        )

    return MapDevicesOut(
        items=items,
        total=total,
        aggregated=False,
        bbox=list(bbox) if bbox else None,
        limit=limit,
    )


async def _active_alarm_map(db: AsyncSession, device_ids: list[int]) -> dict[int, str]:
    """一次性取各设备的活动报警类型，避免逐设备 N+1"""
    if not device_ids:
        return {}
    rows = await db.execute(
        select(Alarm.device_id, Alarm.alarm_type)
        .where(Alarm.device_id.in_(device_ids), Alarm.status.in_(OPEN_ALARM_STATUSES))
        .order_by(Alarm.device_id, Alarm.id.desc())
    )
    active: dict[int, str] = {}
    for device_id, alarm_type in rows.all():
        active.setdefault(device_id, alarm_type)
    return active


def _map_point(device: Device, alarm_type: str | None) -> MapDeviceOut:
    device_type = device.device_type
    return MapDeviceOut(
        id=device.id,
        device_code=device.device_code,
        device_name=device.device_name,
        status=device.status,
        org_id=device.org_id,
        type_name=device_type.type_name if device_type else None,
        category=device_type.category if device_type else None,
        map_x=float(device.map_x),
        map_y=float(device.map_y),
        has_active_alarm=alarm_type is not None,
        alarm_type=alarm_type,
    )


STATUS_SEVERITY = {"alarm": 0, "fault": 1, "shield": 2, "offline": 3, "normal": 4}
ALARM_SEVERITY = {"fire": 0, "pre_fire": 1, "fault": 2, "shield": 3}


def _aggregate_grid(
    points: list[MapDeviceOut], bbox: tuple[float, float, float, float] | None, limit: int
) -> list[MapDeviceOut]:
    """
    视口网格聚合：按 bbox（缺省时按点位实际分布）切 GRID_BUCKETS x GRID_BUCKETS，
    每桶返回一个中心代表点并带上 count，前端 markercluster 直接消费该结果。
    """
    xs = [p.map_x for p in points if p.map_x is not None]
    ys = [p.map_y for p in points if p.map_y is not None]
    if not xs or not ys:
        return points[:limit]

    xmin, xmax = (bbox[0], bbox[2]) if bbox else (min(xs), max(xs))
    ymin, ymax = (bbox[1], bbox[3]) if bbox else (min(ys), max(ys))
    step_x = (xmax - xmin) / GRID_BUCKETS or 1.0
    step_y = (ymax - ymin) / GRID_BUCKETS or 1.0

    buckets: dict[tuple[int, int], list[MapDeviceOut]] = {}
    for point in points:
        cell = (
            min(max(floor((point.map_x - xmin) / step_x), 0), GRID_BUCKETS - 1),
            min(max(floor((point.map_y - ymin) / step_y), 0), GRID_BUCKETS - 1),
        )
        buckets.setdefault(cell, []).append(point)

    aggregated: list[MapDeviceOut] = []
    for (cx, cy), members in sorted(buckets.items()):
        head = members[0]
        alarm_types = [m.alarm_type for m in members if m.alarm_type]
        aggregated.append(
            MapDeviceOut(
                id=head.id,
                device_code=f"cluster-{cx}-{cy}",
                device_name=f"{len(members)} 台设备",
                status=min(
                    (m.status for m in members), key=lambda s: STATUS_SEVERITY.get(s, 9)
                ),
                org_id=head.org_id,
                category=head.category,
                map_x=sum(m.map_x for m in members) / len(members),
                map_y=sum(m.map_y for m in members) / len(members),
                has_active_alarm=bool(alarm_types),
                alarm_type=min(alarm_types, key=lambda t: ALARM_SEVERITY.get(t, 9))
                if alarm_types
                else None,
                count=len(members),
            )
        )
    return aggregated


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    """解析 `bbox=xmin,ymin,xmax,ymax`（原图像素坐标，见计划 4.2 坐标约定）"""
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if len(parts) != 4:
        return None
    try:
        xmin, ymin, xmax, ymax = (float(p) for p in parts)
    except ValueError:
        return None
    if xmin > xmax:
        xmin, xmax = xmax, xmin
    if ymin > ymax:
        ymin, ymax = ymax, ymin
    return xmin, ymin, xmax, ymax
