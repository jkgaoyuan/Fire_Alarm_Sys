"""
设备档案服务层（3.2 B-9）

组合筛选 + 分页 + 数据权限 + 扩展属性校验 + 退役/删除区分 + 状态变更留痕。
"""

from typing import Any

from sqlalchemy import false, func, select
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
from app.services.organization_service import resolve_descendant_org_ids

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
    include_deleted: bool = False,
) -> Select:
    """
    组合筛选（FR-012）。

    默认不返回逻辑删除的设备；`include_deleted=True` 时改为「只返回已删除」，
    供归档页回收站视图调用 `/devices/{id}/restore` 恢复档案
    ——此前后端冲突提示让用户去调一个没有任何 UI 入口的接口。
    """
    stmt = stmt.where(
        Device.is_deleted.is_(True) if include_deleted else Device.is_deleted.is_(False)
    )

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
    include_deleted: bool = False,
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
        include_deleted=include_deleted,
    )

    scoped = await apply_device_data_scope(base, user, db)
    # count 复用同一份筛选条件，避免 items 与 total 口径不一致
    count_result = await db.execute(
        select(func.count()).select_from(scoped.subquery())
    )
    total = count_result.scalar() or 0

    skip = (page - 1) * page_size
    items_stmt = scoped.order_by(Device.id.desc()).offset(skip).limit(page_size)
    result = await db.execute(items_stmt)
    return list(result.scalars().all()), total


async def apply_device_data_scope(query: Select, user: User, db: AsyncSession) -> Select:
    """
    按用户 `data_scope` 追加**设备域**的过滤条件。

    **为什么不复用 `user_service.apply_data_scope`**：那个函数对 `self` 锚的是
    `devices.created_by` —— 设备的**录入人**。设备是**组织的资产**，不是录入人的私产；
    「谁录的这份档案」与「谁该看/该修/该管这台设备」没有关系。

    按 `created_by` 过滤的实测后果（2026-09-14）：维保员 `data_scope='self'`，
    设备由管理员录入 → 设备档案页显示 **0 台**、详情/历史/轨迹一律 404，
    而设备维保恰恰是这个角色的本职工作——模块对其主要使用者不可用。

    这与本仓库既有的两条口径同源：
    - **DEC-012**：alarms 域 `self` 降级为 `dept`（「自动上报的报警没有 created_by」）；
    - `inspection_service.apply_task_data_scope` / `repair_service.repair_scope_condition`：
      **每个域自己决定 `self` 锚在哪个字段上，锚不住就降级 dept**。

    设备上没有任何「归属到某个人」的字段可锚，因此走降级：

    - `all`  -> 不过滤
    - `dept` -> 本部门及全部子部门（经 `Device.org_id`）
    - `self` -> **降级为 `dept`**（含未识别的取值，取最小可见权限仍是 dept 级）
    """
    if user.data_scope == "all":
        return query

    # dept 与 self 同路：self 在设备域没有可锚的字段，降级为 dept
    if user.org_id is None:
        # 无部门则不可见任何设备（与 apply_data_scope 的 dept 分支一致）
        return query.where(false())

    org_ids = await resolve_descendant_org_ids(db, user.org_id)
    if not org_ids:
        return query.where(false())
    return query.where(Device.org_id.in_(org_ids))


async def list_devices_by_scope(
    db: AsyncSession,
    *,
    org_ids: list[int],
    type_id: int | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> tuple[list[Device], int]:
    """
    按「组织集合 + 设备类型」取在役设备并分页。

    ⚠️ **刻意不套 `apply_data_scope`**：数据权限的锚点应由**调用方**决定，
    而不是无条件锚 `created_by` —— 理由与 `inspection_service.apply_task_data_scope`
    开头那段注释完全一致，那是本仓库为解决同一类问题立下的口径。

    设备上的 `created_by` 是「谁录的档案」，而巡检场景里「这台设备该不该我检」
    取决于它属于哪个区域、属于哪类设备，与录入人无关。实测（2026-09-14）：
    维保员 `data_scope='self'`，而设备都是管理员录的 →
    `GET /devices` 返回 `total=0` 且 **`code 200 / message success`、不报错**，
    「执行巡检」的设备列表恒为空，点开只有一张空表格。

    **调用方必须自行完成授权判定**（例如先确认该巡检任务对当前用户可见）。
    筛选条件复用 `_apply_filters`，避免「在役设备」出现第二份定义。
    """
    base = await _apply_filters(
        select(Device),
        keyword=keyword,
        type_id=type_id,
        # org 条件单独加：这里要的是「组织集合」，而 _apply_filters 只接受单个 org_id
        org_id=None,
    )
    scoped = base.where(Device.org_id.in_(org_ids))

    # count 与 items 复用同一份条件，避免 total 与列表口径不一致
    count_result = await db.execute(select(func.count()).select_from(scoped.subquery()))
    total = count_result.scalar() or 0

    skip = (page - 1) * page_size
    # 预加载 device_type / org：调用方要展示类型名与区域名，
    # 不预加载的话读这两个关系会触发异步懒加载 → MissingGreenlet（500），
    # 或者更糟——被 getattr 兜成 None，页面显示空白而不报错。
    result = await db.execute(
        scoped.options(
            selectinload(Device.device_type),
            selectinload(Device.org),
        )
        .order_by(Device.id.desc())
        .offset(skip)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def _get_device_in_scope(
    db: AsyncSession, device_id: int, user: User
) -> Device | None:
    """按 ID 查询设备并叠加用户数据范围；逻辑删除与越权均视为不存在。"""
    base = select(Device).where(Device.id == device_id, Device.is_deleted.is_(False))
    scoped = await apply_device_data_scope(base, user, db)
    stmt = scoped.options(
        selectinload(Device.device_type),
        selectinload(Device.org),
        selectinload(Device.creator),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_device(db: AsyncSession, device_id: int, user: User) -> Device | None:
    """按 ID 查询设备（含类型/区域/创建人），已叠加数据范围。"""
    return await _get_device_in_scope(db, device_id, user)


async def _get_code_conflict(
    db: AsyncSession, device_code: str, exclude_id: int | None = None
) -> tuple[int, bool] | None:
    """
    查询设备编码冲突记录。
    返回 (id, is_deleted)：is_deleted=True 表示该编码被已逻辑删除档案占用。
    """
    stmt = select(Device.id, Device.is_deleted).where(Device.device_code == device_code)
    if exclude_id is not None:
        stmt = stmt.where(Device.id != exclude_id)
    row = (await db.execute(stmt.limit(1))).one_or_none()
    if row is None:
        return None
    return row[0], row[1]


def _code_conflict_message(
    device_code: str, conflict: tuple[int, bool]
) -> str:
    """根据冲突记录是否已删除，生成对应的可读错误文案。"""
    conflict_id, is_deleted = conflict
    if is_deleted:
        return (
            f"设备编码已被已删除档案占用: {device_code}。"
            f"如需恢复，请调用 POST /api/v1/devices/{conflict_id}/restore 恢复该档案，"
            "或更换编码。"
        )
    return f"设备编码已存在: {device_code}"


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
    conflict = await _get_code_conflict(db, payload.device_code)
    if conflict is not None:
        raise AuthError(400, _code_conflict_message(payload.device_code, conflict))

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
    device = await _get_device_in_scope(db, device_id, user)
    if device is None:
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
        conflict = await _get_code_conflict(db, new_code, exclude_id=device_id)
        if conflict is not None:
            raise AuthError(400, _code_conflict_message(new_code, conflict))

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
    device = await _get_device_in_scope(db, device_id, user)
    if device is None:
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
    device = await _get_device_in_scope(db, device_id, user)
    if device is None:
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


async def restore_device(
    db: AsyncSession, device_id: int, user: User
) -> Device | None:
    """恢复逻辑删除的设备档案，恢复前校验编码不与未删除档案冲突。"""
    base = select(Device).where(Device.id == device_id, Device.is_deleted.is_(True))
    scoped = await apply_device_data_scope(base, user, db)
    stmt = scoped.options(
        selectinload(Device.device_type),
        selectinload(Device.org),
        selectinload(Device.creator),
    )
    device = (await db.execute(stmt)).scalar_one_or_none()
    if device is None:
        return None

    conflict = await _get_code_conflict(db, device.device_code, exclude_id=device.id)
    if conflict is not None and not conflict[1]:
        raise AuthError(
            400,
            f"恢复失败：设备编码 {device.device_code} 已被其他未删除档案占用，"
            "请先处理冲突后再恢复该档案。",
        )

    device.is_deleted = False
    db.add(device)
    await write_status_log(
        db,
        device_id=device.id,
        old_status=device.status,
        new_status=device.status,
        changed_by=user.id,
        reason="档案恢复",
    )
    await db.commit()
    return await device_crud.reload(db, device.id)
