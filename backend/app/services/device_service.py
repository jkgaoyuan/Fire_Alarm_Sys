"""
设备档案服务层（3.2 B-9）

组合筛选 + 分页 + 数据权限 + 扩展属性校验 + 退役/删除区分 + 状态变更留痕。
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.core.exceptions import AuthError
from app.crud.device import device_crud
from app.models.device import DEVICE_STATUSES, Device, DeviceStatusLog
from app.models.device_type import DeviceType
from app.models.organization import Organization
from app.models.user import User
from app.schemas.device import DeviceCreate, DeviceUpdate
from app.services.user_service import apply_data_scope

# retired 为终态：不可再通过 PUT 修改，也不可再次退役
TERMINAL_STATUS = "retired"


# ==================== 扩展属性校验 ====================


def validate_attributes(
    schema: dict[str, Any], attributes: dict[str, Any]
) -> list[str]:
    """
    按设备类型的 attribute_schema 校验扩展属性。
    返回错误描述列表（空列表表示通过）。

    仅支持 string / number / select 三种字段类型（计划第八节降险策略）。
    扩展属性均为选填：值为 None 或空字符串时跳过类型校验。
    """
    errors: list[str] = []
    if not isinstance(attributes, dict):
        return ["attributes 必须是对象"]

    for key, value in attributes.items():
        spec = schema.get(key)
        if spec is None:
            errors.append(f"未知扩展属性: {key}")
            continue
        if value is None or value == "":
            continue

        label = spec.get("label", key)
        field_type = spec.get("type", "string")

        if field_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                # 允许纯数字字符串（Excel 导入的单元格常为文本）
                try:
                    float(str(value))
                except (TypeError, ValueError):
                    errors.append(f"{label} 必须为数字")
        elif field_type == "select":
            options = spec.get("options") or []
            if options and value not in options:
                errors.append(f"{label} 取值必须是 {options} 之一")
        elif field_type == "string":
            if not isinstance(value, str):
                errors.append(f"{label} 必须为文本")
        else:
            errors.append(f"属性 {key} 声明了不支持的字段类型 {field_type}")

    return errors


async def _get_type_schema(db: AsyncSession, type_id: int | None) -> dict[str, Any]:
    """取设备类型的 attribute_schema；type_id 为空视为无约束"""
    if type_id is None:
        return {}
    result = await db.execute(select(DeviceType).where(DeviceType.id == type_id))
    device_type = result.scalar_one_or_none()
    if device_type is None:
        raise AuthError(400, f"设备类型不存在: id={type_id}")
    return device_type.attribute_schema or {}


async def _ensure_org_exists(db: AsyncSession, org_id: int | None) -> None:
    if org_id is None:
        return
    result = await db.execute(
        select(Organization.id).where(Organization.id == org_id)
    )
    if result.scalar_one_or_none() is None:
        raise AuthError(400, f"区域不存在: id={org_id}")


# ==================== 查询 ====================


async def _apply_filters(
    stmt: Select,
    *,
    keyword: str | None = None,
    type_id: int | None = None,
    org_id: int | None = None,
    statuses: list[str] | None = None,
    brand: str | None = None,
    include_retired: bool = False,
) -> Select:
    """组合筛选（FR-012）。逻辑删除的设备任何情况下都不返回。"""
    stmt = stmt.where(Device.is_deleted.is_(False))

    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            Device.device_code.ilike(like) | Device.device_name.ilike(like)
        )
    if type_id is not None:
        stmt = stmt.where(Device.type_id == type_id)
    if org_id is not None:
        stmt = stmt.where(Device.org_id == org_id)
    if brand:
        stmt = stmt.where(Device.brand.ilike(f"%{brand}%"))

    if statuses:
        stmt = stmt.where(Device.status.in_(statuses))
    elif not include_retired:
        # 默认隐藏已退役（FR-008 退役流程 3）
        stmt = stmt.where(Device.status != TERMINAL_STATUS)

    return stmt


def parse_status_filter(status: str | None) -> list[str]:
    """解析逗号分隔的状态筛选参数，忽略非法值"""
    if not status:
        return []
    return [s.strip() for s in status.split(",") if s.strip() in DEVICE_STATUSES]


async def list_devices(
    db: AsyncSession,
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    type_id: int | None = None,
    org_id: int | None = None,
    status: str | None = None,
    brand: str | None = None,
    include_retired: bool = False,
) -> tuple[list[Device], int]:
    """分页查询设备列表，叠加数据权限过滤。返回 (设备列表, 总数)"""
    statuses = parse_status_filter(status)
    base = await _apply_filters(
        select(Device)
        .options(
            selectinload(Device.device_type),
            selectinload(Device.org),
            selectinload(Device.creator),
        ),
        keyword=keyword,
        type_id=type_id,
        org_id=org_id,
        statuses=statuses,
        brand=brand,
        include_retired=include_retired,
    )

    scoped = await apply_data_scope(base, user, db)
    # count 复用同一份筛选条件，避免 items 与 total 口径不一致
    count_result = await db.execute(
        select(func.count()).select_from(scoped.subquery())
    )
    total = count_result.scalar() or 0

    skip = (page - 1) * page_size
    items_stmt = scoped.order_by(Device.id.desc()).offset(skip).limit(page_size)
    result = await db.execute(items_stmt)
    return list(result.scalars().all()), total


async def get_device(db: AsyncSession, device_id: int) -> Device | None:
    """按 ID 查询设备（含类型/区域/创建人），逻辑删除的不可见"""
    device = await device_crud.get_with_relations(db, device_id)
    if device is None or device.is_deleted:
        return None
    return device


async def is_code_taken(
    db: AsyncSession, device_code: str, exclude_id: int | None = None
) -> bool:
    """设备编码唯一性校验（排除自身）"""
    stmt = select(Device.id).where(Device.device_code == device_code)
    if exclude_id is not None:
        stmt = stmt.where(Device.id != exclude_id)
    result = await db.execute(stmt.limit(1))
    return result.scalar_one_or_none() is not None


# ==================== 状态变更留痕 ====================


async def write_status_log(
    db: AsyncSession,
    *,
    device_id: int,
    old_status: str | None,
    new_status: str,
    changed_by: int | None,
    reason: str | None = None,
) -> None:
    db.add(
        DeviceStatusLog(
            device_id=device_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            reason=reason,
        )
    )


# ==================== 写操作 ====================


async def create_device(
    db: AsyncSession, payload: DeviceCreate, user: User
) -> Device:
    """创建设备。编码唯一、类型/区域存在性、扩展属性均需通过校验。"""
    if await is_code_taken(db, payload.device_code):
        raise AuthError(400, f"设备编码已存在: {payload.device_code}")

    schema = await _get_type_schema(db, payload.type_id)
    await _ensure_org_exists(db, payload.org_id)

    errors = validate_attributes(schema, payload.attributes)
    if errors:
        raise AuthError(400, "扩展属性校验失败: " + "；".join(errors))

    device = Device(
        **payload.model_dump(exclude={"attributes"}),
        attributes=payload.attributes or {},
        created_by=user.id,
    )
    db.add(device)
    await db.flush()
    await write_status_log(
        db,
        device_id=device.id,
        old_status=None,
        new_status=device.status,
        changed_by=user.id,
        reason="设备建档",
    )
    await db.commit()
    return await device_crud.reload(db, device.id)


async def update_device(
    db: AsyncSession, device_id: int, payload: DeviceUpdate, user: User
) -> Device | None:
    """
    更新设备。已退役设备禁止编辑（计划 7.3 验收项）。
    status 不接受 retired —— 退役必须走 /retire 以留下变更原因。
    """
    device = await device_crud.get_with_relations(db, device_id)
    if device is None or device.is_deleted:
        return None
    if device.status == TERMINAL_STATUS:
        raise AuthError(400, "设备已退役，禁止编辑")

    data = payload.model_dump(exclude_unset=True)
    new_status = data.get("status")
    if new_status == TERMINAL_STATUS:
        raise AuthError(400, "退役请调用 /devices/{id}/retire 接口")

    # 编码变更需重新校验唯一性
    new_code = data.get("device_code")
    if new_code and new_code != device.device_code:
        if await is_code_taken(db, new_code, exclude_id=device_id):
            raise AuthError(400, f"设备编码已存在: {new_code}")

    # 类型或属性任一变化都要重新校验扩展属性
    if "type_id" in data or "attributes" in data:
        target_type_id = data.get("type_id", device.type_id)
        schema = await _get_type_schema(db, target_type_id)
        target_attrs = data.get("attributes", device.attributes or {})
        errors = validate_attributes(schema, target_attrs)
        if errors:
            raise AuthError(400, "扩展属性校验失败: " + "；".join(errors))

    if "org_id" in data:
        await _ensure_org_exists(db, data["org_id"])

    status_changed = bool(new_status) and new_status != device.status
    old_status = device.status

    for field, value in data.items():
        if hasattr(device, field):
            setattr(device, field, value)

    db.add(device)
    if status_changed:
        await write_status_log(
            db,
            device_id=device.id,
            old_status=old_status,
            new_status=new_status,
            changed_by=user.id,
            reason="状态变更",
        )
    await db.commit()
    return await device_crud.reload(db, device_id)


async def retire_device(
    db: AsyncSession, device_id: int, user: User, reason: str | None = None
) -> Device | None:
    """
    设备退役：status -> retired，is_deleted 保持 FALSE，关联历史全部保留。
    已是 retired 的设备不可重复退役。
    """
    device = await device_crud.get_with_relations(db, device_id)
    if device is None or device.is_deleted:
        return None
    if device.status == TERMINAL_STATUS:
        raise AuthError(400, "设备已处于退役状态，无需重复退役")

    old_status = device.status
    device.status = TERMINAL_STATUS
    db.add(device)
    await write_status_log(
        db,
        device_id=device.id,
        old_status=old_status,
        new_status=TERMINAL_STATUS,
        changed_by=user.id,
        reason=reason or "设备退役",
    )
    await db.commit()
    return await device_crud.reload(db, device_id)


async def delete_device(db: AsyncSession, device_id: int, user: User) -> Device | None:
    """逻辑删除（is_deleted=TRUE）。物理删除会破坏关联历史，故不提供。"""
    device = await device_crud.get_with_relations(db, device_id)
    if device is None or device.is_deleted:
        return None

    old_status = device.status
    device.is_deleted = True
    db.add(device)
    await write_status_log(
        db,
        device_id=device.id,
        old_status=old_status,
        new_status=old_status,
        changed_by=user.id,
        reason="档案逻辑删除",
    )
    await db.commit()
    return device
