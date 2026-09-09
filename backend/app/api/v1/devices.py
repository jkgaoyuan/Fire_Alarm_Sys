"""
设备档案 API 路由（3.2 B-9 / B-10 / B-11）

type_router: /device-types      设备类型下拉与详情（登录即可）
router:      /devices           档案 CRUD、退役、批量导入、历史记录、状态轨迹（3.3 B-18）
"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_permission
from app.db.session import get_db
from app.models.device_type import DeviceType
from app.models.user import User
from app.schemas.device import (
    DeviceCreate,
    DeviceHistoryOut,
    DeviceListOut,
    DeviceOut,
    DeviceRetireRequest,
    DeviceTypeOut,
    DeviceUpdate,
    ImportResultOut,
    TrajectoryOut,
)
from app.services import device_import_service, device_history_service
from app.services.device_service import (
    create_device,
    delete_device,
    get_device,
    list_devices,
    retire_device,
    update_device,
)

type_router = APIRouter()
router = APIRouter()

MAX_IMPORT_ROWS = 5000
TEMPLATE_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


# ==================== 设备类型 ====================


@type_router.get("", response_model=dict)
async def list_device_types(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """设备类型列表（全部，不分页，供下拉框与动态表单使用）"""
    result = await db.execute(select(DeviceType).order_by(DeviceType.id))
    types = result.scalars().all()
    return {
        "code": 200,
        "message": "success",
        "data": [DeviceTypeOut.model_validate(t).model_dump() for t in types],
    }


@type_router.get("/{type_id}", response_model=dict)
async def get_device_type(
    type_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """设备类型详情（含 attribute_schema）"""
    result = await db.execute(select(DeviceType).where(DeviceType.id == type_id))
    device_type = result.scalar_one_or_none()
    if device_type is None:
        return {"code": 404, "message": "设备类型不存在", "data": None}
    return {
        "code": 200,
        "message": "success",
        "data": DeviceTypeOut.model_validate(device_type).model_dump(),
    }


# ==================== 设备档案 ====================


@router.get("", response_model=dict)
async def list_devices_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
    type_id: int | None = Query(None),
    org_id: int | None = Query(None),
    status: str | None = Query(None, description="状态筛选，多值以逗号分隔"),
    brand: str | None = Query(None),
    include_retired: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("device:view")),
):
    """分页查询设备列表（组合筛选 + 数据权限过滤）"""
    devices, total = await list_devices(
        db,
        user,
        page=page,
        page_size=page_size,
        keyword=keyword,
        type_id=type_id,
        org_id=org_id,
        status=status,
        brand=brand,
        include_retired=include_retired,
    )
    return {
        "code": 200,
        "message": "success",
        "data": DeviceListOut(
            items=[_device_out(d) for d in devices],
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
    }


@router.post("", response_model=dict)
async def create_device_api(
    payload: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("device:create")),
):
    """创建设备档案"""
    device = await create_device(db, payload, user)
    return {
        "code": 200,
        "message": "创建成功",
        "data": _device_out(device),
    }


@router.get("/import/template")
async def download_import_template(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("device:create")),
):
    """下载批量导入 Excel 模板"""
    result = await db.execute(select(DeviceType).order_by(DeviceType.id))
    types = list(result.scalars().all())
    content = device_import_service.build_template(types)
    return Response(
        content=content,
        media_type=TEMPLATE_MEDIA_TYPE,
        headers={
            "Content-Disposition": 'attachment; filename="device_import_template.xlsx"'
        },
    )


@router.post("/import", response_model=dict)
async def import_devices_api(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("device:create")),
):
    """Excel 批量导入设备，返回成功/失败明细"""
    payload = await file.read()
    if not payload:
        return {"code": 400, "message": "上传文件为空", "data": None}

    rows = device_import_service.read_rows(payload)
    if len(rows) > MAX_IMPORT_ROWS:
        return {
            "code": 400,
            "message": f"单次导入不得超过 {MAX_IMPORT_ROWS} 行",
            "data": None,
        }

    result = await device_import_service.import_devices(db, payload, user)
    return {
        "code": 200,
        "message": result["message"],
        "data": ImportResultOut(**result).model_dump(),
    }


@router.get("/{device_id}", response_model=dict)
async def get_device_api(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("device:view")),
):
    """设备详情（含类型名称、区域名称、创建人），已叠加数据范围"""
    device = await get_device(db, device_id, user)
    if device is None:
        return {"code": 404, "message": "设备不存在", "data": None}
    return {
        "code": 200,
        "message": "success",
        "data": _device_out(device),
    }


@router.put("/{device_id}", response_model=dict)
async def update_device_api(
    device_id: int,
    payload: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("device:update")),
):
    """更新设备档案（已退役设备禁止编辑）"""
    device = await update_device(db, device_id, payload, user)
    if device is None:
        return {"code": 404, "message": "设备不存在", "data": None}
    return {
        "code": 200,
        "message": "更新成功",
        "data": _device_out(device),
    }


@router.post("/{device_id}/retire", response_model=dict)
async def retire_device_api(
    device_id: int,
    payload: DeviceRetireRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("device:retire")),
):
    """设备退役：status 置为 retired，保留全部关联历史"""
    device = await retire_device(db, device_id, user, payload.reason)
    if device is None:
        return {"code": 404, "message": "设备不存在", "data": None}
    return {
        "code": 200,
        "message": "设备已退役",
        "data": _device_out(device),
    }


@router.get("/{device_id}/history", response_model=dict)
async def get_device_history_api(
    device_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("device:view")),
):
    """设备历史记录时间轴（按时间倒序），已叠加数据范围"""
    history = await device_history_service.get_device_history(
        db, device_id, user=user, limit=limit
    )
    if history is None:
        return {"code": 404, "message": "设备不存在", "data": None}
    return {
        "code": 200,
        "message": "success",
        "data": DeviceHistoryOut(**history).model_dump(),
    }


@router.get("/{device_id}/trajectory", response_model=dict)
async def get_device_trajectory_api(
    device_id: int,
    start: datetime | None = Query(None, description="缺省为 end 前 7 天"),
    end: datetime | None = Query(None, description="缺省为当前时间"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("device:view")),
):
    """设备历史轨迹（FR-018：单类别时序，按时间升序，最长 90 天），已叠加数据范围"""
    try:
        begin, finish = device_history_service.resolve_window(start, end)
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": None}

    payload = await device_history_service.get_device_trajectory(
        db,
        device_id,
        user=user,
        start=begin,
        end=finish,
        page=page,
        page_size=page_size,
    )
    if payload is None:
        return {"code": 404, "message": "设备不存在", "data": None}
    return {
        "code": 200,
        "message": "success",
        "data": TrajectoryOut(**payload).model_dump(),
    }


@router.get("/{device_id}/trajectory/export")
async def export_device_trajectory_api(
    device_id: int,
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("device:view")),
):
    """
    轨迹导出（≤1 万行同步导出），已叠加数据范围。

    超上限直接拒绝并提示缩小区间；异步导出任务属 3.9 数据报表范围。
    """
    try:
        begin, finish = device_history_service.resolve_window(start, end)
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": None}

    payload = await device_history_service.get_device_trajectory(
        db,
        device_id,
        user=user,
        start=begin,
        end=finish,
        page=1,
        page_size=device_history_service.TRAJECTORY_MAX_EXPORT_ROWS + 1,
    )
    if payload is None:
        return {"code": 404, "message": "设备不存在", "data": None}
    max_rows = device_history_service.TRAJECTORY_MAX_EXPORT_ROWS
    if payload["total"] > max_rows:
        return {
            "code": 400,
            "message": (
                f"导出行数 {payload['total']} 超过 {max_rows} 行上限，"
                "请缩小时间区间（异步导出见 3.9）"
            ),
            "data": None,
        }

    if format == "csv":
        content = device_history_service.build_trajectory_csv(payload)
        media_type = "text/csv; charset=utf-8"
    else:
        content = device_history_service.build_trajectory_xlsx(payload)
        media_type = TEMPLATE_MEDIA_TYPE
    filename = (
        f"{payload['device_code']}_trajectory_"
        f"{begin.strftime('%Y%m%d')}_{finish.strftime('%Y%m%d')}.{format}"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{device_id}", response_model=dict)
async def delete_device_api(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("device:delete")),
):
    """逻辑删除设备档案（退役请走 /retire）"""
    device = await delete_device(db, device_id, user)
    if device is None:
        return {"code": 404, "message": "设备不存在", "data": None}
    return {"code": 200, "message": "删除成功", "data": None}


def _device_out(device) -> dict:
    """ORM → 响应字典，补充类型/区域/创建人展示字段"""
    return DeviceOut(
        id=device.id,
        device_code=device.device_code,
        device_name=device.device_name,
        type_id=device.type_id,
        type_name=device.device_type.type_name if device.device_type else None,
        category=device.device_type.category if device.device_type else None,
        org_id=device.org_id,
        org_name=device.org.org_name if device.org else None,
        manufacturer=device.manufacturer,
        model=device.model,
        brand=device.brand,
        spec=device.spec,
        install_date=device.install_date,
        warranty_expire_date=device.warranty_expire_date,
        maintain_cycle=device.maintain_cycle,
        status=device.status,
        map_x=device.map_x,
        map_y=device.map_y,
        attributes=device.attributes or {},
        remark=device.remark,
        is_deleted=device.is_deleted,
        created_by=device.created_by,
        creator_name=device.creator.real_name if device.creator else None,
        created_at=device.created_at,
        updated_at=device.updated_at,
    ).model_dump()
