"""
维修工单 API 路由（3.7 FR-038 ~ FR-042）
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, require_permission
from app.schemas.auth import ResponseModel as Response
from app.crud.repair import RepairOrderCRUD
from app.models.user import User
from app.services.repair_service import repair_scope_condition
from app.schemas.repair import (
    RepairOrderCreate,
    RepairOrderUpdate,
    RepairOrderAssign,
    RepairOrderComplete,
    RepairOrderReturn,
    RepairOrderResponse,
    RepairOrderListResponse,
    AvgRepairDurationResponse,
    FaultDistributionResponse,
    WorkloadResponse,
    Top10FaultDevicesResponse,
    RepairOverviewResponse,
)

router = APIRouter()


# ==================== 响应序列化 ====================

def _order_out(order) -> RepairOrderResponse:
    """
    把 ORM 工单对象转成响应体。

    此前这段 25 行的构造在 7 个端点 + 列表循环里各抄了一份，字段一多必然漂移；
    而漏字段是**静默的**——少写一个就是 None，没有报错，前端显示空白。

    ⚠️ 关系字段（device / reporter / repairer / acceptor）必须已被预加载。
    这里用 `if xxx else None` 只是兜底：异步会话下访问**未加载**的关系会抛
    MissingGreenlet，兜底救不了。所以调用方必须经 `crud.get()`（内含 4 个
    selectinload），不要自己拼裸 `select(RepairOrder)`
    （2026-09-13 详情接口实际踩过，线上 500）。
    """
    return RepairOrderResponse(
        id=order.id,
        order_no=order.order_no,
        device_id=order.device_id,
        alarm_id=order.alarm_id,
        inspection_record_id=order.inspection_record_id,
        fault_desc=order.fault_desc,
        status=order.status,
        reporter_id=order.reporter_id,
        repairer_id=order.repairer_id,
        acceptor_id=order.acceptor_id,
        assigned_at=order.assigned_at,
        completed_at=order.completed_at,
        accepted_at=order.accepted_at,
        repair_result=order.repair_result,
        return_reason=order.return_reason,
        created_by=order.created_by,
        device_name=order.device.device_name if order.device else None,
        device_code=order.device.device_code if order.device else None,
        reporter_name=order.reporter.real_name if order.reporter else None,
        repairer_name=order.repairer.real_name if order.repairer else None,
        acceptor_name=order.acceptor.real_name if order.acceptor else None,
    )


# ⚠️ 信封（`Response(code=...)`）必须在端点里保持**字面量**，不要顺手把它也抽成
# 一个 `return _envelope(db_obj)` 式的辅助函数（本文件曾经这么试过）：
# `tests/test_api_envelope_contract.py` 是 AST 静态扫描，只认字面量
# `Response(code=...)` 或含 `code` 键的 dict，调用辅助函数一律判 `bare`（裸返回）。
# 守卫刻意不做「已知返回信封的辅助函数」白名单——那等于给它开一个可以返回
# 任何东西的后门。所以这里只抽 `data` 部分，端点写成
# `return Response(code=200, message="success", data=_order_out(db_obj))`。


# ==================== CRUD 接口 ====================

@router.get(
    "/repair-orders",
    response_model=Response[RepairOrderListResponse],
    summary="获取维修工单列表",
    dependencies=[Depends(require_permission("repair:view"))],
)
async def list_repair_orders(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选"),
    device_id: Optional[int] = Query(None, description="设备 ID 筛选"),
    repairer_id: Optional[int] = Query(None, description="维修人员 ID 筛选"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取维修工单列表（分页 + 筛选，受数据权限范围约束）"""
    crud = RepairOrderCRUD(db)

    skip = (page - 1) * page_size
    items, total = await crud.get_multi(
        skip=skip,
        limit=page_size,
        status=status,
        device_id=device_id,
        repairer_id=repairer_id,
        start_date=start_date,
        end_date=end_date,
        scope_condition=await repair_scope_condition(current_user, db),
    )
    
    # 转换为响应格式
    items_response = [_order_out(item) for item in items]
    total_pages = (total + page_size - 1) // page_size
    
    return Response(
        code=200,
        message="success",
        data=RepairOrderListResponse(
            items=items_response,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
    )


@router.post(
    "/repair-orders",
    response_model=Response[RepairOrderResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建维修工单",
    dependencies=[Depends(require_permission("repair:create"))],
)
async def create_repair_order(
    obj_in: RepairOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建维修工单"""
    crud = RepairOrderCRUD(db)
    db_obj = await crud.create(obj_in, created_by=current_user.id)
    
    # 重新查询以获取关联信息
    db_obj = await crud.get(db_obj.id)
    
    return Response(code=200, message="success", data=_order_out(db_obj))


@router.get(
    "/repair-orders/{id}",
    response_model=Response[RepairOrderResponse],
    summary="获取维修工单详情",
    dependencies=[Depends(require_permission("repair:view"))],
)
async def get_repair_order(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取维修工单详情（越出数据权限范围按不存在处理，不泄露存在性）"""
    crud = RepairOrderCRUD(db)
    db_obj = await crud.get(
        id, scope_condition=await repair_scope_condition(current_user, db)
    )
    
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="维修工单不存在"
        )
    
    return Response(code=200, message="success", data=_order_out(db_obj))


# ==================== 状态流转接口 ====================

@router.put(
    "/repair-orders/{id}/assign",
    response_model=Response[RepairOrderResponse],
    summary="派单",
    dependencies=[Depends(require_permission("repair:assign"))],
)
async def assign_repair_order(
    id: int,
    obj_in: RepairOrderAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """派单（需 repair:assign 权限，由路由依赖校验）"""
    
    crud = RepairOrderCRUD(db)
    try:
        db_obj = await crud.assign(id, obj_in.repairer_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="维修工单不存在"
        )
    
    # 重新查询以获取关联信息
    db_obj = await crud.get(db_obj.id)
    
    return Response(code=200, message="success", data=_order_out(db_obj))


@router.put(
    "/repair-orders/{id}/start",
    response_model=Response[RepairOrderResponse],
    summary="开始维修",
    # repair:repair = 「维修填报」。与下面保留的**归属检查**（只有被指派的
    # 维修人本人能开始）叠加：权限码管「这类操作能不能做」，归属检查管
    # 「这一单归不归你」。两者语义不同，都需要——口径与 /complete 一致。
    dependencies=[Depends(require_permission("repair:repair"))],
)
async def start_repair_order(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """开始维修（`assigned` / `returned` → `repairing`）"""
    crud = RepairOrderCRUD(db)

    # 检查是否为维修人员
    db_obj_check = await crud.get(id)
    if not db_obj_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="维修工单不存在"
        )

    if db_obj_check.repairer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅维修人员可开始维修"
        )

    try:
        db_obj = await crud.start(id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="维修工单不存在"
        )

    # 重新查询以获取关联信息
    db_obj = await crud.get(db_obj.id)

    return Response(code=200, message="success", data=_order_out(db_obj))


@router.put(
    "/repair-orders/{id}/complete",
    response_model=Response[RepairOrderResponse],
    summary="完成维修",
    # repair:repair = 「维修填报」。与下面保留的**归属检查**（只有被指派的
    # 维修人本人能完成）叠加：权限码管「这类操作能不能做」，归属检查管
    # 「这一单归不归你」。两者语义不同，都需要。
    dependencies=[Depends(require_permission("repair:repair"))],
)
async def complete_repair_order(
    id: int,
    obj_in: RepairOrderComplete,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """完成维修（仅维修人员可操作）"""
    crud = RepairOrderCRUD(db)
    
    # 检查是否为维修人员
    db_obj_check = await crud.get(id)
    if not db_obj_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="维修工单不存在"
        )
    
    if db_obj_check.repairer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅维修人员可完成维修"
        )
    
    try:
        db_obj = await crud.complete(id, obj_in.repair_result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="维修工单不存在"
        )
    
    # 重新查询以获取关联信息
    db_obj = await crud.get(db_obj.id)
    
    return Response(code=200, message="success", data=_order_out(db_obj))


@router.put(
    "/repair-orders/{id}/accept",
    response_model=Response[RepairOrderResponse],
    summary="验收通过",
    dependencies=[Depends(require_permission("repair:accept"))],
)
async def accept_repair_order(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """验收通过（需 repair:accept 权限，由路由依赖校验）"""
    
    crud = RepairOrderCRUD(db)
    try:
        db_obj = await crud.accept(id, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="维修工单不存在"
        )
    
    # 重新查询以获取关联信息
    db_obj = await crud.get(db_obj.id)
    
    return Response(code=200, message="success", data=_order_out(db_obj))


@router.put(
    "/repair-orders/{id}/return",
    response_model=Response[RepairOrderResponse],
    summary="验收退回",
    dependencies=[Depends(require_permission("repair:accept"))],
)
async def return_repair_order(
    id: int,
    obj_in: RepairOrderReturn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """验收退回（需 repair:accept 权限，由路由依赖校验）"""
    
    crud = RepairOrderCRUD(db)
    try:
        db_obj = await crud.return_order(id, obj_in.return_reason, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="维修工单不存在"
        )
    
    # 重新查询以获取关联信息
    db_obj = await crud.get(db_obj.id)
    
    return Response(code=200, message="success", data=_order_out(db_obj))


# ==================== 统计接口 ====================

@router.get(
    "/repair-statistics/overview",
    response_model=Response[RepairOverviewResponse],
    summary="维修概览统计",
    dependencies=[Depends(require_permission("repair:view"))],
)
async def get_repair_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """平均维修时长 + 状态分布"""
    crud = RepairOrderCRUD(db)
    avg_hours = await crud.get_avg_repair_duration()
    status_dist = await crud.get_status_distribution()
    total = sum(item["count"] for item in status_dist)
    return Response(
        code=200,
        message="success",
        data=RepairOverviewResponse(
            avg_repair_hours=avg_hours,
            total_orders=total,
            status_distribution=status_dist,
        ),
    )


@router.get("/repair-statistics/by-repairer", response_model=Response[WorkloadResponse],
    dependencies=[Depends(require_permission("repair:view"))],
)
async def get_repairer_workload(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """维修人员工作量统计"""
    crud = RepairOrderCRUD(db)
    items = await crud.get_workload_by_repairer()
    return Response(
        code=200,
        message="success",
        data=WorkloadResponse(items=items),
    )


@router.get("/repair-statistics/fault-types", response_model=Response[FaultDistributionResponse],
    dependencies=[Depends(require_permission("repair:view"))],
)
async def get_fault_distribution(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """故障类型分布（按设备类型分组）"""
    crud = RepairOrderCRUD(db)
    items = await crud.get_fault_type_distribution()
    return Response(
        code=200,
        message="success",
        data=FaultDistributionResponse(items=items),
    )


@router.get("/repair-statistics/top10-devices", response_model=Response[Top10FaultDevicesResponse],
    dependencies=[Depends(require_permission("repair:view"))],
)
async def get_top10_fault_devices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """故障设备 TOP10 统计"""
    crud = RepairOrderCRUD(db)
    items = await crud.get_top10_fault_devices()
    return Response(
        code=200,
        message="success",
        data=Top10FaultDevicesResponse(items=items),
    )
