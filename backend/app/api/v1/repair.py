"""
维修工单 API 路由（3.7 FR-038 ~ FR-042）
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.crud.repair import RepairOrderCRUD
from app.models.user import User
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
)

router = APIRouter()


# ==================== CRUD 接口 ====================

@router.get("/repair-orders", response_model=RepairOrderListResponse, summary="获取维修工单列表")
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
    """获取维修工单列表（分页 + 筛选）"""
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
    )
    
    # 转换为响应格式
    items_response = []
    for item in items:
        resp = RepairOrderResponse(
            id=item.id,
            order_no=item.order_no,
            device_id=item.device_id,
            alarm_id=item.alarm_id,
            inspection_record_id=item.inspection_record_id,
            fault_desc=item.fault_desc,
            status=item.status,
            reporter_id=item.reporter_id,
            repairer_id=item.repairer_id,
            acceptor_id=item.acceptor_id,
            assigned_at=item.assigned_at,
            completed_at=item.completed_at,
            accepted_at=item.accepted_at,
            repair_result=item.repair_result,
            return_reason=item.return_reason,
            created_by=item.created_by,
            device_name=item.device.device_name if item.device else None,
            device_code=item.device.device_code if item.device else None,
            reporter_name=item.reporter.real_name if item.reporter else None,
            repairer_name=item.repairer.real_name if item.repairer else None,
            acceptor_name=item.acceptor.real_name if item.acceptor else None,
        )
        items_response.append(resp)
    
    total_pages = (total + page_size - 1) // page_size
    
    return RepairOrderListResponse(
        items=items_response,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/repair-orders", response_model=RepairOrderResponse, status_code=status.HTTP_201_CREATED, summary="创建维修工单")
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
    
    return RepairOrderResponse(
        id=db_obj.id,
        order_no=db_obj.order_no,
        device_id=db_obj.device_id,
        alarm_id=db_obj.alarm_id,
        inspection_record_id=db_obj.inspection_record_id,
        fault_desc=db_obj.fault_desc,
        status=db_obj.status,
        reporter_id=db_obj.reporter_id,
        repairer_id=db_obj.repairer_id,
        acceptor_id=db_obj.acceptor_id,
        assigned_at=db_obj.assigned_at,
        completed_at=db_obj.completed_at,
        accepted_at=db_obj.accepted_at,
        repair_result=db_obj.repair_result,
        return_reason=db_obj.return_reason,
        created_by=db_obj.created_by,
        device_name=db_obj.device.device_name if db_obj.device else None,
        device_code=db_obj.device.device_code if db_obj.device else None,
        reporter_name=db_obj.reporter.real_name if db_obj.reporter else None,
        repairer_name=db_obj.repairer.real_name if db_obj.repairer else None,
        acceptor_name=db_obj.acceptor.real_name if db_obj.acceptor else None,
    )


@router.get("/repair-orders/{id}", response_model=RepairOrderResponse, summary="获取维修工单详情")
async def get_repair_order(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取维修工单详情"""
    crud = RepairOrderCRUD(db)
    db_obj = await crud.get(id)
    
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="维修工单不存在"
        )
    
    return RepairOrderResponse(
        id=db_obj.id,
        order_no=db_obj.order_no,
        device_id=db_obj.device_id,
        alarm_id=db_obj.alarm_id,
        inspection_record_id=db_obj.inspection_record_id,
        fault_desc=db_obj.fault_desc,
        status=db_obj.status,
        reporter_id=db_obj.reporter_id,
        repairer_id=db_obj.repairer_id,
        acceptor_id=db_obj.acceptor_id,
        assigned_at=db_obj.assigned_at,
        completed_at=db_obj.completed_at,
        accepted_at=db_obj.accepted_at,
        repair_result=db_obj.repair_result,
        return_reason=db_obj.return_reason,
        created_by=db_obj.created_by,
        device_name=db_obj.device.device_name if db_obj.device else None,
        device_code=db_obj.device.device_code if db_obj.device else None,
        reporter_name=db_obj.reporter.real_name if db_obj.reporter else None,
        repairer_name=db_obj.repairer.real_name if db_obj.repairer else None,
        acceptor_name=db_obj.acceptor.real_name if db_obj.acceptor else None,
    )


# ==================== 状态流转接口 ====================

@router.put("/repair-orders/{id}/assign", response_model=RepairOrderResponse, summary="派单")
async def assign_repair_order(
    id: int,
    obj_in: RepairOrderAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """派单（仅消防主管可操作）"""
    # 权限检查：仅消防主管可派单
    if not any(r.role_code == "chief" for r in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅消防主管可执行派单操作"
        )
    
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
    
    return RepairOrderResponse(
        id=db_obj.id,
        order_no=db_obj.order_no,
        device_id=db_obj.device_id,
        alarm_id=db_obj.alarm_id,
        inspection_record_id=db_obj.inspection_record_id,
        fault_desc=db_obj.fault_desc,
        status=db_obj.status,
        reporter_id=db_obj.reporter_id,
        repairer_id=db_obj.repairer_id,
        acceptor_id=db_obj.acceptor_id,
        assigned_at=db_obj.assigned_at,
        completed_at=db_obj.completed_at,
        accepted_at=db_obj.accepted_at,
        repair_result=db_obj.repair_result,
        return_reason=db_obj.return_reason,
        created_by=db_obj.created_by,
        device_name=db_obj.device.device_name if db_obj.device else None,
        device_code=db_obj.device.device_code if db_obj.device else None,
        reporter_name=db_obj.reporter.real_name if db_obj.reporter else None,
        repairer_name=db_obj.repairer.real_name if db_obj.repairer else None,
        acceptor_name=db_obj.acceptor.real_name if db_obj.acceptor else None,
    )


@router.put("/repair-orders/{id}/complete", response_model=RepairOrderResponse, summary="完成维修")
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
    
    return RepairOrderResponse(
        id=db_obj.id,
        order_no=db_obj.order_no,
        device_id=db_obj.device_id,
        alarm_id=db_obj.alarm_id,
        inspection_record_id=db_obj.inspection_record_id,
        fault_desc=db_obj.fault_desc,
        status=db_obj.status,
        reporter_id=db_obj.reporter_id,
        repairer_id=db_obj.repairer_id,
        acceptor_id=db_obj.acceptor_id,
        assigned_at=db_obj.assigned_at,
        completed_at=db_obj.completed_at,
        accepted_at=db_obj.accepted_at,
        repair_result=db_obj.repair_result,
        return_reason=db_obj.return_reason,
        created_by=db_obj.created_by,
        device_name=db_obj.device.device_name if db_obj.device else None,
        device_code=db_obj.device.device_code if db_obj.device else None,
        reporter_name=db_obj.reporter.real_name if db_obj.reporter else None,
        repairer_name=db_obj.repairer.real_name if db_obj.repairer else None,
        acceptor_name=db_obj.acceptor.real_name if db_obj.acceptor else None,
    )


@router.put("/repair-orders/{id}/accept", response_model=RepairOrderResponse, summary="验收通过")
async def accept_repair_order(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """验收通过（仅消防主管可操作）"""
    # 权限检查：仅消防主管可验收
    if not any(r.role_code == "chief" for r in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅消防主管可执行验收操作"
        )
    
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
    
    return RepairOrderResponse(
        id=db_obj.id,
        order_no=db_obj.order_no,
        device_id=db_obj.device_id,
        alarm_id=db_obj.alarm_id,
        inspection_record_id=db_obj.inspection_record_id,
        fault_desc=db_obj.fault_desc,
        status=db_obj.status,
        reporter_id=db_obj.reporter_id,
        repairer_id=db_obj.repairer_id,
        acceptor_id=db_obj.acceptor_id,
        assigned_at=db_obj.assigned_at,
        completed_at=db_obj.completed_at,
        accepted_at=db_obj.accepted_at,
        repair_result=db_obj.repair_result,
        return_reason=db_obj.return_reason,
        created_by=db_obj.created_by,
        device_name=db_obj.device.device_name if db_obj.device else None,
        device_code=db_obj.device.device_code if db_obj.device else None,
        reporter_name=db_obj.reporter.real_name if db_obj.reporter else None,
        repairer_name=db_obj.repairer.real_name if db_obj.repairer else None,
        acceptor_name=db_obj.acceptor.real_name if db_obj.acceptor else None,
    )


@router.put("/repair-orders/{id}/return", response_model=RepairOrderResponse, summary="验收退回")
async def return_repair_order(
    id: int,
    obj_in: RepairOrderReturn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """验收退回（仅消防主管可操作）"""
    # 权限检查：仅消防主管可验收
    if not any(r.role_code == "chief" for r in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅消防主管可执行验收操作"
        )
    
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
    
    return RepairOrderResponse(
        id=db_obj.id,
        order_no=db_obj.order_no,
        device_id=db_obj.device_id,
        alarm_id=db_obj.alarm_id,
        inspection_record_id=db_obj.inspection_record_id,
        fault_desc=db_obj.fault_desc,
        status=db_obj.status,
        reporter_id=db_obj.reporter_id,
        repairer_id=db_obj.repairer_id,
        acceptor_id=db_obj.acceptor_id,
        assigned_at=db_obj.assigned_at,
        completed_at=db_obj.completed_at,
        accepted_at=db_obj.accepted_at,
        repair_result=db_obj.repair_result,
        return_reason=db_obj.return_reason,
        created_by=db_obj.created_by,
        device_name=db_obj.device.device_name if db_obj.device else None,
        device_code=db_obj.device.device_code if db_obj.device else None,
        reporter_name=db_obj.reporter.real_name if db_obj.reporter else None,
        repairer_name=db_obj.repairer.real_name if db_obj.repairer else None,
        acceptor_name=db_obj.acceptor.real_name if db_obj.acceptor else None,
    )
