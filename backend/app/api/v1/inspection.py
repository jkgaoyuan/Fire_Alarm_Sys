"""
巡检管理 API（3.6-B4）
====================
PRD 章节：3.6 设备巡检
端点清单：
1. GET /inspection-plans - 计划列表（分页 + 筛选）
2. POST /inspection-plans - 创建计划（inspection:create）
3. GET /inspection-plans/{id} - 计划详情（inspection:view）
4. PUT /inspection-plans/{id} - 更新计划（inspection:update）
5. DELETE /inspection-plans/{id} - 删除计划（inspection:delete）
6. POST /inspection-plans/{id}/toggle - 启用/停用（inspection:update）
7. POST /inspection-plans/{id}/generate - 手动生成任务（inspection:create）
8. GET /inspection-tasks - 任务列表（分页 + 筛选）
9. POST /inspection-tasks/{id}/records - 提交记录（inspection:execute）
10. GET /inspection-records - 记录查询（分页 + 筛选）
11. GET /inspection-missed-stats - 漏检统计（inspection:stat）

权限码：
- inspection:view - 查看巡检
- inspection:create - 新增计划
- inspection:update - 编辑计划
- inspection:delete - 删除计划
- inspection:execute - 执行巡检
- inspection:stat - 巡检统计
"""

from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db, require_permission
from app.models.inspection import InspectionPlan, InspectionTask, InspectionRecord
from app.schemas.inspection import (
    InspectionPlanCreate,
    InspectionPlanUpdate,
    InspectionPlanResponse,
    InspectionPlanWithStats,
    InspectionPlanPagination,
    InspectionTaskResponse,
    InspectionTaskWithDetails,
    InspectionTaskPagination,
    InspectionRecordCreate,
    InspectionRecordResponse,
    InspectionRecordPagination,
    InspectionMissedStat,
)
from app.crud.inspection import inspection_plan_crud, inspection_task_crud, inspection_record_crud
from app.services.inspection_service import (
    generate_tasks_for_plan,
    submit_inspection_record,
    InspectionService,
    scan_missed_tasks,
)


router = APIRouter(tags=["Inspection"])


# ==================== 巡检计划管理 ====================

@router.get(
    "/inspection-plans",
    response_model=InspectionPlanPagination,
    summary="获取巡检计划列表",
    dependencies=[Depends(require_permission("inspection:view"))]
)
async def get_inspection_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    org_id: Optional[int] = None,
    is_enabled: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """分页查询巡检计划列表"""
    skip = (page - 1) * page_size
    
    stmt = select(InspectionPlan)
    if org_id is not None:
        stmt = stmt.where(InspectionPlan.org_id == org_id)
    if is_enabled is not None:
        stmt = stmt.where(InspectionPlan.is_enabled == is_enabled)
    
    # 总数统计（SQLAlchemy 2.0 规范）
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one_or_none()
    
    results = (await db.execute(
        stmt.order_by(InspectionPlan.created_at.desc())
        .offset(skip)
        .limit(page_size)
    )).scalars().all()
    
    # 为每个计划添加统计信息
    items = []
    for plan in results:
        stats = await inspection_plan_crud.get_stats_by_plan(db, plan_id=plan.id)
        plan_with_stats = InspectionPlanWithStats(
            id=plan.id,
            plan_name=plan.plan_name,
            org_id=plan.org_id,
            device_type_id=plan.device_type_id,
            cycle_type=plan.cycle_type,
            cycle_days=plan.cycle_days,
            responsible_user_id=plan.responsible_user_id,
            start_date=plan.start_date,
            end_date=plan.end_date,
            is_enabled=plan.is_enabled,
            created_at=plan.created_at,
            **stats
        )
        items.append(plan_with_stats)
    
    return InspectionPlanPagination(
        items=items,
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/inspection-plans",
    response_model=InspectionPlanResponse,
    summary="创建巡检计划",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("inspection:create"))]
)
async def create_inspection_plan(
    data: InspectionPlanCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建新巡检计划"""
    # 验证责任人存在
    user_stmt = select(InspectionPlan.responsible_user_id).where(User.id == data.responsible_user_id)
    user_exists = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"责任人不存在：user_id={data.responsible_user_id}"
        )
    
    plan = InspectionPlan(**data.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return InspectionPlanResponse.model_validate(plan)


@router.get(
    "/inspection-plans/{plan_id}",
    response_model=InspectionPlanWithStats,
    summary="获取计划详情与统计",
    dependencies=[Depends(require_permission("inspection:view"))]
)
async def get_inspection_plan_detail(
    plan_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取单个计划详情及统计信息"""
    plan = await inspection_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="巡检计划不存在"
        )
    
    stats = await inspection_plan_crud.get_stats_by_plan(db, plan_id=plan.id)
    
    result = InspectionPlanWithStats(
        id=plan.id,
        plan_name=plan.plan_name,
        org_id=plan.org_id,
        device_type_id=plan.device_type_id,
        cycle_type=plan.cycle_type,
        cycle_days=plan.cycle_days,
        responsible_user_id=plan.responsible_user_id,
        start_date=plan.start_date,
        end_date=plan.end_date,
        is_enabled=plan.is_enabled,
        created_at=plan.created_at,
        **stats
    )
    return result


@router.put(
    "/inspection-plans/{plan_id}",
    response_model=InspectionPlanResponse,
    summary="更新巡检计划",
    dependencies=[Depends(require_permission("inspection:update"))]
)
async def update_inspection_plan(
    plan_id: int,
    data: InspectionPlanUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新巡检计划"""
    plan = await inspection_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="巡检计划不存在"
        )
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plan, key, value)
    
    await db.commit()
    await db.refresh(plan)
    return InspectionPlanResponse.model_validate(plan)


@router.delete(
    "/inspection-plans/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除巡检计划",
    dependencies=[Depends(require_permission("inspection:delete"))]
)
async def delete_inspection_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除巡检计划（仅未启用的）"""
    plan = await inspection_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="巡检计划不存在"
        )
    
    if plan.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已启用的计划无法直接删除，请先停用"
        )
    
    await inspection_plan_crud.remove(db, plan_id)
    return None


@router.post(
    "/inspection-plans/{plan_id}/toggle",
    response_model=InspectionPlanResponse,
    summary="启用/停用巡检计划",
    dependencies=[Depends(require_permission("inspection:update"))]
)
async def toggle_inspection_plan_status(
    plan_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db)
):
    """切换计划启用状态"""
    plan = await inspection_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="巡检计划不存在"
        )
    
    plan.is_enabled = data.get("is_enabled", not plan.is_enabled)
    await db.commit()
    await db.refresh(plan)
    return InspectionPlanResponse.model_validate(plan)


@router.post(
    "/inspection-plans/{plan_id}/generate",
    response_model=list[InspectionTaskResponse],
    summary="手动生成巡检任务",
    dependencies=[Depends(require_permission("inspection:create"))]
)
async def manual_generate_tasks(
    plan_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db)
):
    """为某计划在指定日期生成任务"""
    plan = await inspection_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="巡检计划不存在"
        )
    
    if not plan.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该巡检计划已禁用"
        )
    
    target_date_str = data.get("target_date")
    days_count = data.get("days", 7)
    
    if target_date_str:
        target_date = date.fromisoformat(target_date_str)
        tasks = await generate_tasks_for_plan(db, plan_id, target_date)
    else:
        # 生成未来 N 天的任务
        from app.services.inspection_service import get_next_dates_by_cycle
        generated = []
        start_date = date.today()
        future_dates = get_next_dates_by_cycle(start_date, plan.cycle_type, days_count)
        
        for td in future_dates:
            task_list = await generate_tasks_for_plan(db, plan_id, td)
            generated.extend(task_list)
        tasks = generated
    
    return [InspectionTaskResponse.model_validate(t) for t in tasks]


# ==================== 巡检任务管理 ====================

@router.get(
    "/inspection-tasks",
    response_model=InspectionTaskPagination,
    summary="获取巡检任务列表",
    dependencies=[Depends(require_permission("inspection:view"))]
)
async def get_inspection_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    responsible_user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """分页查询巡检任务列表"""
    skip = (page - 1) * page_size
    today = date.today()
    
    # 默认范围：今天及过去 30 天
    effective_start = start_date or (today.replace(day=1))
    effective_end = end_date or today
    
    stmt = select(InspectionTask).where(
        InspectionTask.task_date >= effective_start,
        InspectionTask.task_date <= effective_end,
    )
    
    if status:
        stmt = stmt.where(InspectionTask.status == status)
    if responsible_user_id:
        stmt = stmt.where(InspectionTask.responsible_user_id == responsible_user_id)
    
    # 总数统计
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one_or_none()
    
    results = (await db.execute(
        stmt.order_by(InspectionTask.task_date.desc())
        .offset(skip)
        .limit(page_size)
    )).scalars().all()
    
    # 加载关联数据
    items = []
    for task in results:
        task_stmt = (
            select(InspectionTask)
            .options(selectinload(InspectionTask.plan))
            .options(selectinload(InspectionTask.responsible_user))
            .where(InspectionTask.id == task.id)
        )
        full_task = (await db.execute(task_stmt)).scalar_one_or_none()
        
        item = InspectionTaskResponse(
            id=full_task.id,
            plan_id=full_task.plan_id,
            task_date=full_task.task_date,
            status=full_task.status,
            completed_at=full_task.completed_at,
            created_at=full_task.created_at,
            plan_name=full_task.plan.plan_name if full_task.plan else None,
            plan_cycle_type=full_task.plan.cycle_type if full_task.plan else None,
            responsible_user_id=full_task.responsible_user_id,
            responsible_user_name=full_task.responsible_user.real_name if full_task.responsible_user else None,
        )
        items.append(item)
    
    return InspectionTaskPagination(
        items=items,
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/inspection-tasks/{task_id}/records",
    response_model=InspectionRecordResponse,
    summary="提交巡检记录",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("inspection:execute"))]
)
async def submit_record(
    task_id: int,
    data: InspectionRecordCreate,
    db: AsyncSession = Depends(get_db)
):
    """维保人员提交巡检记录"""
    record = await submit_inspection_record(
        db=db,
        task_id=data.task_id,
        device_id=data.device_id,
        result=data.result.value,
        abnormal_desc=data.abnormal_desc,
        photos=data.photos,
    )
    
    await db.refresh(record)
    return InspectionRecordResponse.model_validate(record)


# ==================== 巡检记录查询 ====================

@router.get(
    "/inspection-records",
    response_model=InspectionRecordPagination,
    summary="获取巡检记录列表",
    dependencies=[Depends(require_permission("inspection:view"))]
)
async def get_inspection_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    task_id: Optional[int] = None,
    device_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    result: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """分页查询巡检记录"""
    skip = (page - 1) * page_size
    today = date.today()
    
    # 默认范围：本月
    effective_start = start_date or (today.replace(day=1))
    effective_end = end_date or today
    
    stmt = select(InspectionRecord).where(
        InspectionRecord.inspected_at >= datetime.combine(effective_start, datetime.min.time()),
        InspectionRecord.inspected_at <= datetime.combine(effective_end, datetime.max.time()),
    )
    
    if task_id:
        stmt = stmt.where(InspectionRecord.task_id == task_id)
    if device_id:
        stmt = stmt.where(InspectionRecord.device_id == device_id)
    if result:
        stmt = stmt.where(InspectionRecord.result == result)
    
    # 总数统计
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one_or_none()
    
    results = (await db.execute(
        stmt.order_by(InspectionRecord.inspected_at.desc())
        .offset(skip)
        .limit(page_size)
    )).scalars().all()
    
    items = [InspectionRecordResponse.model_validate(r) for r in results]
    
    return InspectionRecordPagination(
        items=items,
        total=total or 0,
        page=page,
        page_size=page_size,
    )


# ==================== 漏检统计 ====================

@router.get(
    "/inspection-missed-stats",
    response_model=InspectionMissedStat,
    summary="获取漏检统计数据",
    dependencies=[Depends(require_permission("inspection:stat"))]
)
async def get_missed_statistics(
    before_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    """扫描并获取漏检统计信息"""
    result = await scan_missed_tasks(db, before_date)
    
    stat = InspectionMissedStat(
        task_date=date.today(),
        missed_count=result["marked_missed"],
        overdue_hours=0.0,
        affected_plans=[
            {"plan_id": p["plan_id"], "plan_name": p["plan"].plan_name, "missed_count": p["missed_count"]}
            for p in result["alert_plans"]
        ],
        notification_sent=False,
    )
    return stat


# 需要导入 User 模型
from app.models.user import User
