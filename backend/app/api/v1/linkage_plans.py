"""
联动预案 API（3.4-B4 + 3.4-B5）
- 预案 CRUD、启用/停用、模拟触发
- 手动执行预案
- 联动日志查询列表和详情
- 日志导出
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_db, require_permission, get_current_active_user
from app.models.linkage import LinkagePlan, AlarmLinkageLog
from app.models.user import User
from app.schemas.auth import ResponseModel as Response
from app.schemas.linkage import (
    LinkagePlanCreate,
    LinkagePlanUpdate,
    LinkagePlanOut,
    LinkagePlanPagination,
    LinkageManualExecute,
    AlarmLinkageLogOut,
    AlarmLinkageLogPagination,
    LinkageExecuteResult,
)
from app.crud.linkage import linkage_plan_crud, alarm_linkage_log_crud
from app.services.linkage_engine_service import linkage_engine
from app.services.linkage_executor import execute_action

router = APIRouter(tags=["Linkage Plans"])


# ==================== 预案管理 ====================

@router.get(
    "",
    response_model=Response[LinkagePlanPagination],
    summary="获取预案列表",
    # 此前只有一行 `# TODO: 添加权限验证`，端点实际是敞开的：未带 token
    # 即返回 200 + 预案数据（含 actions 动作配置），而同文件的 `/{plan_id}`
    # 要求 linkage:view。补上与其兄弟端点一致的权限码。
    dependencies=[Depends(require_permission("linkage:view"))]
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
    
    return Response(
        code=200,
        message="success",
        data=LinkagePlanPagination(
            items=items,
            total=total or 0,
            page=page,
            page_size=page_size,
        ),
    )


@router.get(
    "/{plan_id}",
    response_model=Response[LinkagePlanOut],
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
    return Response(
        code=200,
        message="success",
        data=LinkagePlanOut.model_validate(plan),
    )


@router.post(
    "",
    response_model=Response[LinkagePlanOut],
    summary="创建预案",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("linkage:create"))]
)
async def create_linkage_plan(
    data: LinkagePlanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """创建新预案"""
    plan = LinkagePlan(**data.model_dump(), created_by=user.id)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return Response(
        code=200,
        message="success",
        data=LinkagePlanOut.model_validate(plan),
    )


@router.put(
    "/{plan_id}",
    response_model=Response[LinkagePlanOut],
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
    return Response(
        code=200,
        message="success",
        data=LinkagePlanOut.model_validate(plan),
    )


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
    
    await linkage_plan_crud.delete(db, id=plan.id)


@router.post(
    "/{plan_id}/toggle",
    response_model=Response[LinkagePlanOut],
    summary="切换预案启用状态",
    dependencies=[Depends(require_permission("linkage:update"))]
)
async def toggle_linkage_plan_status(
    plan_id: int,
    data: dict | None = Body(default=None),
    db: AsyncSession = Depends(get_db)
):
    """切换预案的启用/停用状态（body 可省略，省略即取反）"""
    plan = await linkage_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预案不存在"
        )

    # 显式传入 is_enabled 时按目标值设置，避免「双击即两次取反」导致 UI 与库不同步
    data = data or {}
    plan.is_enabled = data.get("is_enabled", not plan.is_enabled)
    await db.commit()
    await db.refresh(plan)
    
    return Response(
        code=200,
        message="success",
        data=LinkagePlanOut.model_validate(plan),
    )


@router.post(
    "/{plan_id}/simulate",
    response_model=Response[AlarmLinkageLogPagination],
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
    return Response(
        code=200,
        message="success",
        data=AlarmLinkageLogPagination(
            items=items,
            total=len(items),
            page=1,
            page_size=len(items),
        ),
    )


@router.post(
    "/execute",
    response_model=Response[LinkageExecuteResult],
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
    
    return Response(
        code=200,
        message="success",
        data=LinkageExecuteResult(
            message=f"成功执行 {len(logs)} 个动作",
            logs=[AlarmLinkageLogOut.model_validate(log) for log in logs],
        ),
    )
