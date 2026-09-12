"""
联动预案 API（3.4-B4 + 3.4-B5）
- 预案 CRUD、启用/停用、模拟触发
- 手动执行预案
- 联动日志查询列表和详情
- 日志导出
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_db, require_permission
from app.models.linkage import LinkagePlan, AlarmLinkageLog
from app.schemas.linkage import (
    LinkagePlanCreate,
    LinkagePlanUpdate,
    LinkagePlanOut,
    LinkagePlanPagination,
    LinkageManualExecute,
    AlarmLinkageLogOut,
    AlarmLinkageLogPagination,
)
from app.crud.linkage import linkage_plan_crud, alarm_linkage_log_crud
from app.services.linkage_engine_service import linkage_engine
from app.services.linkage_executor import execute_action

router = APIRouter(tags=["Linkage Plans"])


# ==================== 预案管理 ====================

@router.get(
    "",
    response_model=LinkagePlanPagination,
    summary="获取预案列表"
    # TODO: 添加权限验证
)
async def get_linkage_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    org_id: Optional[int] = None,
    fire_type: Optional[str] = None,
    trigger_device_type_id: Optional[int] = None,
    is_enabled: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """分页查询预案列表，支持多种筛选条件"""
    skip = (page - 1) * page_size
    
    # 构建筛选条件
    stmt = select(LinkagePlan)
    if org_id is not None:
        stmt = stmt.where(LinkagePlan.org_id == org_id)
    if fire_type is not None:
        stmt = stmt.where(LinkagePlan.fire_type == fire_type)
    if trigger_device_type_id is not None:
        stmt = stmt.where(LinkagePlan.trigger_device_type_id == trigger_device_type_id)
    if is_enabled is not None:
        stmt = stmt.where(LinkagePlan.is_enabled == is_enabled)
    
    # 总数统计
    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one_or_none()
    
    # 获取数据
    stmt = stmt.order_by(LinkagePlan.created_at.desc()).offset(skip).limit(page_size)
    results = (await db.execute(stmt)).scalars().all()
    
    items = [LinkagePlanOut.model_validate(plan) for plan in results]
    
    return LinkagePlanPagination(
        items=items,
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{plan_id}",
    response_model=LinkagePlanOut,
    summary="获取预案详情",
    dependencies=[Depends(require_permission("linkage:view"))]
)
async def get_linkage_plan_detail(plan_id: int, db: AsyncSession = Depends(get_db)):
    """获取单个预案详情"""
    plan = await linkage_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预案不存在"
        )
    return LinkagePlanOut.model_validate(plan)


@router.post(
    "",
    response_model=LinkagePlanOut,
    summary="创建预案",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("linkage:create"))]
)
async def create_linkage_plan(
    data: LinkagePlanCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建新预案"""
    plan = LinkagePlan(**data.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return LinkagePlanOut.model_validate(plan)


@router.put(
    "/{plan_id}",
    response_model=LinkagePlanOut,
    summary="更新预案",
    dependencies=[Depends(require_permission("linkage:update"))]
)
async def update_linkage_plan(
    plan_id: int,
    data: LinkagePlanUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新预案"""
    plan = await linkage_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预案不存在"
        )
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plan, key, value)
    
    await db.commit()
    await db.refresh(plan)
    return LinkagePlanOut.model_validate(plan)


@router.delete(
    "/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除预案",
    dependencies=[Depends(require_permission("linkage:delete"))]
)
async def delete_linkage_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除预案（有执行日志时禁止删除，改为停用）"""
    # 检查是否有执行日志
    log_count = await alarm_linkage_log_crud.count_plan_logs(db, plan_id)
    if log_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该预案已有执行日志，请改用停用功能"
        )
    
    plan = await linkage_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预案不存在"
        )
    
    await linkage_plan_crud.remove(db, plan)
    await db.commit()


@router.post(
    "/{plan_id}/toggle",
    response_model=LinkagePlanOut,
    summary="切换预案启用状态",
    dependencies=[Depends(require_permission("linkage:update"))]
)
async def toggle_linkage_plan_status(
    plan_id: int,
    db: AsyncSession = Depends(get_db)
):
    """切换预案的启用/停用状态"""
    plan = await linkage_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预案不存在"
        )
    
    plan.is_enabled = not plan.is_enabled
    await db.commit()
    await db.refresh(plan)
    
    return LinkagePlanOut.model_validate(plan)


@router.post(
    "/{plan_id}/simulate",
    response_model=AlarmLinkageLogPagination,
    summary="模拟触发预案",
    dependencies=[Depends(require_permission("linkage:simulate"))]
)
async def simulate_linkage_trigger(
    plan_id: int,
    remark: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    模拟触发预案（不生成真实告警，仅记录日志）
    用于测试预案逻辑是否正确
    """
    plan = await linkage_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预案不存在"
        )
    
    # 生成模拟日志（is_simulation=true）
    logs = []
    for action in plan.actions:
        log = AlarmLinkageLog(
            alarm_id=None,  # 模拟模式下为空
            plan_id=plan.id,
            action_type=action["action_type"],
            target_device_id=action.get("target_device_id"),
            status="pending",
            is_simulation=True,
            delay_seconds=action.get("delay_seconds", 0),
        )
        db.add(log)
        await db.flush()
        
        # 直接执行（简化流程）
        result_status, result_message = await execute_action(action, log)
        log.status = result_status
        log.result_message = result_message
        log.completed_at = datetime.now()
        
        logs.append(log)
    
    await db.commit()
    
    # 返回结果
    items = [AlarmLinkageLogOut.model_validate(log) for log in logs]
    return AlarmLinkageLogPagination(
        items=items,
        total=len(items),
        page=1,
        page_size=len(items),
    )


@router.post(
    "/execute",
    response_model=dict,
    summary="手动执行预案",
    dependencies=[Depends(require_permission("linkage:execute"))]
)
async def execute_linkage_plan(
    data: LinkageManualExecute,
    db: AsyncSession = Depends(get_db)
):
    """手动执行预案（针对指定报警或独立演练）"""
    plan = await linkage_plan_crud.get(db, data.plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预案不存在"
        )
    
    # 生成联动日志
    logs = []
    for action in plan.actions:
        log = AlarmLinkageLog(
            alarm_id=data.alarm_id,
            plan_id=plan.id,
            action_type=action["action_type"],
            target_device_id=action.get("target_device_id"),
            status="pending",
            is_simulation=data.is_simulation,
            delay_seconds=action.get("delay_seconds", 0),
        )
        db.add(log)
        await db.flush()
        
        # 执行动作
        result_status, result_message = await execute_action(action, log)
        log.status = result_status
        log.result_message = result_message
        log.completed_at = datetime.now()
        
        logs.append(log)
    
    await db.commit()
    
    return {
        "message": f"成功执行 {len(logs)} 个动作",
        "logs": [AlarmLinkageLogOut.model_validate(log) for log in logs],
    }


# ==================== 联动日志管理 ====================

@router.get(
    "/logs",
    response_model=AlarmLinkageLogPagination,
    summary="查询联动日志",
    dependencies=[Depends(require_permission("linkage:view"))]
)
async def get_linkage_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    alarm_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    status: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """分页查询联动日志，支持多条件筛选"""
    skip = (page - 1) * page_size
    
    stmt = select(AlarmLinkageLog)
    if alarm_id is not None:
        stmt = stmt.where(AlarmLinkageLog.alarm_id == alarm_id)
    if plan_id is not None:
        stmt = stmt.where(AlarmLinkageLog.plan_id == plan_id)
    if status is not None:
        stmt = stmt.where(AlarmLinkageLog.status == status)
    if start_time is not None:
        stmt = stmt.where(AlarmLinkageLog.created_at >= start_time)
    if end_time is not None:
        stmt = stmt.where(AlarmLinkageLog.created_at <= end_time)
    
    # 总数 (SQLAlchemy 2.0 正确语法)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one_or_none()
    
    # 数据
    stmt = stmt.order_by(AlarmLinkageLog.created_at.desc()).offset(skip).limit(page_size)
    results = (await db.execute(stmt)).scalars().all()
    
    items = [AlarmLinkageLogOut.model_validate(log) for log in results]
    
    return AlarmLinkageLogPagination(
        items=items,
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/logs/{log_id}",
    response_model=AlarmLinkageLogOut,
    summary="获取日志详情",
    dependencies=[Depends(require_permission("linkage:view"))]
)
async def get_linkage_log_detail(log_id: int, db: AsyncSession = Depends(get_db)):
    """获取单个日志详情"""
    log = await alarm_linkage_log_crud.get(db, log_id)
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="日志不存在"
        )
    return AlarmLinkageLogOut.model_validate(log)


@router.get(
    "/logs/export",
    summary="导出联动日志（CSV）",
    dependencies=[Depends(require_permission("linkage:view"))]
)
async def export_linkage_logs(
    alarm_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    导出联动日志为 CSV 格式
    限制最多 1 万行，超限需分批查询
    """
    from fastapi.responses import PlainTextResponse
    
    # 构建查询
    stmt = select(AlarmLinkageLog)
    if alarm_id is not None:
        stmt = stmt.where(AlarmLinkageLog.alarm_id == alarm_id)
    if plan_id is not None:
        stmt = stmt.where(AlarmLinkageLog.plan_id == plan_id)
    if start_time is not None:
        stmt = stmt.where(AlarmLinkageLog.created_at >= start_time)
    if end_time is not None:
        stmt = stmt.where(AlarmLinkageLog.created_at <= end_time)
    
    results = (await db.execute(stmt)).scalars().all()
    
    if len(results) > 10000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="导出行数超过 1 万，请缩小筛选范围"
        )
    
    # 生成 CSV
    lines = ["id,alarm_id,plan_id,action_type,target_device_id,status,result_message,is_simulation,created_at"]
    for log in results:
        lines.append(
            f"{log.id},{log.alarm_id},{log.plan_id},"
            f"{log.action_type},{log.target_device_id},{log.status},"
            f'"{log.result_message or ""}",{log.is_simulation},{log.created_at}'
        )
    
    csv_content = "\n".join(lines)
    return PlainTextResponse(csv_content, media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="linkage_logs.csv"'
    })
