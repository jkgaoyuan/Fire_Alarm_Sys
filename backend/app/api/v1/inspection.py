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
from typing import Optional, List
from fastapi import APIRouter, Body, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db, get_current_active_user, require_permission
from app.models.inspection import InspectionPlan, InspectionTask, InspectionRecord
from app.models.user import User
from app.schemas.auth import ResponseModel as Response
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
    InspectionTaskDeviceItem,
    InspectionTaskDevicePagination,
    InspectionMissedStat,
)
from app.crud.inspection import inspection_plan_crud, inspection_task_crud, inspection_record_crud
from app.services.device_service import list_devices_by_scope
from app.services.organization_service import resolve_descendant_org_ids
from app.services.inspection_service import (
    apply_task_data_scope,
    generate_tasks_for_plan,
    submit_inspection_record,
    InspectionService,
    scan_missed_tasks,
)


router = APIRouter(tags=["Inspection"])


# ==================== 巡检计划管理 ====================

@router.get(
    "/inspection-plans",
    response_model=Response[InspectionPlanPagination],
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
    
    return Response(
        code=200,
        message="success",
        data=InspectionPlanPagination(
            items=items,
            total=total or 0,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "/inspection-plans",
    response_model=Response[InspectionPlanResponse],
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
    user_stmt = select(User.id).where(User.id == data.responsible_user_id)
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
    return Response(code=200, message="创建成功", data=InspectionPlanResponse.model_validate(plan))


@router.get(
    "/inspection-plans/{plan_id}",
    response_model=Response[InspectionPlanWithStats],
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
    return Response(code=200, message="success", data=result)


@router.put(
    "/inspection-plans/{plan_id}",
    response_model=Response[InspectionPlanResponse],
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
    return Response(code=200, message="更新成功", data=InspectionPlanResponse.model_validate(plan))


@router.delete(
    "/inspection-plans/{plan_id}",
    response_model=Response[None],
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
    
    await inspection_plan_crud.delete(db, id=plan_id)
    return Response(code=200, message="deleted", data=None)


@router.post(
    "/inspection-plans/{plan_id}/toggle",
    response_model=Response[InspectionPlanResponse],
    summary="启用/停用巡检计划",
    dependencies=[Depends(require_permission("inspection:update"))]
)
async def toggle_inspection_plan_status(
    plan_id: int,
    data: dict | None = Body(default=None),
    db: AsyncSession = Depends(get_db)
):
    """切换计划启用状态（body 可省略，省略即取反）"""
    plan = await inspection_plan_crud.get(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="巡检计划不存在"
        )

    data = data or {}
    plan.is_enabled = data.get("is_enabled", not plan.is_enabled)
    await db.commit()
    await db.refresh(plan)
    return Response(code=200, message="状态更新成功", data=InspectionPlanResponse.model_validate(plan))


@router.post(
    "/inspection-plans/{plan_id}/generate",
    response_model=Response[List[InspectionTaskResponse]],
    summary="手动生成巡检任务",
    dependencies=[Depends(require_permission("inspection:create"))]
)
async def manual_generate_tasks(
    plan_id: int,
    data: dict | None = Body(default=None),
    db: AsyncSession = Depends(get_db)
):
    """为某计划在指定日期生成任务（body 可省略，days 默认 7）"""
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

    data = data or {}
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

    # 必须显式提交：generate_tasks_for_plan 只做 flush，而 get_db 在 finally 里
    # 只 close 不 commit——未提交的事务会被回滚。曾经因此出现「接口返回 7 条任务、
    # 库里 0 行」：前端弹生成成功，任务页却是空的。
    # 在循环外提交一次，保证批量生成要么全成、要么全不成。
    await db.commit()

    tasks = [InspectionTaskResponse.model_validate(t) for t in tasks]
    return Response(code=200, message="Generated", data=tasks)


# ==================== 巡检任务管理 ====================

@router.get(
    "/inspection-tasks",
    response_model=Response[InspectionTaskPagination],
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
    plan_id: Optional[int] = None,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """分页查询巡检任务列表（受 data_scope 约束）"""
    skip = (page - 1) * page_size
    today = date.today()

    # 默认下限为本月 1 日；**不设隐式上限**——/generate 产出的就是未来任务，
    # 上限截到今天会让刚生成的任务全部不可见（实测：库里 7 条、列表 1 条）。
    # 只有调用方显式传 end_date 时才收窄。
    effective_start = start_date or (today.replace(day=1))

    stmt = select(InspectionTask).where(InspectionTask.task_date >= effective_start)
    if end_date:
        stmt = stmt.where(InspectionTask.task_date <= end_date)

    if status:
        stmt = stmt.where(InspectionTask.status == status)
    if responsible_user_id:
        stmt = stmt.where(InspectionTask.responsible_user_id == responsible_user_id)
    if plan_id:
        # 计划详情弹窗的「任务列表」要的就是该计划的任务。此前没有这个参数，
        # 前端只能不传 → 计划 A 的详情里列出**全量任务**。
        stmt = stmt.where(InspectionTask.plan_id == plan_id)

    # 数据范围（3.6 计划第 278 行）：任务表没有 created_by / org_id，
    # 不能复用 user_service.apply_data_scope，见该函数注释
    stmt = await apply_task_data_scope(stmt, user, db)

    # 总数统计
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one_or_none()
    
    results = (await db.execute(
        stmt.order_by(InspectionTask.task_date.desc())
        .offset(skip)
        .limit(page_size)
    )).scalars().all()

    # 「已记录数」：一条 group by 把本页所有任务的记录数一次查出来。
    # 不要放进下面的循环里逐个查——那是 N+1。
    task_ids = [t.id for t in results]
    counts: dict[int, int] = {}
    if task_ids:
        cnt_stmt = (
            select(InspectionRecord.task_id, func.count(InspectionRecord.id))
            .where(InspectionRecord.task_id.in_(task_ids))
            .group_by(InspectionRecord.task_id)
        )
        counts = {tid: n for tid, n in (await db.execute(cnt_stmt)).all()}

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
            records_count=counts.get(full_task.id, 0),
        )
        items.append(item)
    
    return Response(
        code=200,
        message="success",
        data=InspectionTaskPagination(
            items=items,
            total=total or 0,
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/inspection-tasks/{task_id}/devices",
    response_model=Response[InspectionTaskDevicePagination],
    summary="获取巡检任务的应检设备",
    dependencies=[Depends(require_permission("inspection:execute"))],
)
async def get_task_devices(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
    keyword: Optional[str] = None,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    「执行巡检」设备选择器的数据源：**该任务所属计划范围内**的设备。

    取代原先直接调 `GET /devices` 的做法。那个做法有两个问题：

    1. **维保员看不到任何设备。** `/devices` 会套通用的
       `apply_data_scope`，`data_scope='self'` 锚的是 `devices.created_by`
       ——设备的录入人，与「该由谁巡检」无关。设备通常由管理员录入，
       于是维保员的设备列表恒为空，且返回 `code 200 / message success`、
       **不报错**，界面上只是一张空表格（2026-09-14 实测）。
       这与 `apply_task_data_scope` 开头那段注释要解决的是同一类问题。
    2. **范围本身是错的。** 全量设备表意味着可以挑一台根本不在该计划范围内的
       设备来填报——任务只覆盖某区域某类设备，记录却可以落在任意设备上。

    范围口径 = 计划的 `org_id`（**含全部子区域**）+ `device_type_id`（为空即不限类型），
    只取在役设备（未逻辑删除、未退役）。

    **授权**：先按 `apply_task_data_scope` 确认该任务对当前用户可见，
    看不到任务就看不到它的设备——避免这个端点变成绕过设备数据权限的枚举入口。
    """
    task_stmt = (
        select(InspectionTask)
        .options(selectinload(InspectionTask.plan))
        .where(InspectionTask.id == task_id)
    )
    task_stmt = await apply_task_data_scope(task_stmt, user, db)
    task = (await db.execute(task_stmt)).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="巡检任务不存在或无权访问")

    plan = task.plan

    # 计划没挂区域时无法界定范围，宁可返回空也不要放开成全量设备
    org_ids = (
        await resolve_descendant_org_ids(db, plan.org_id)
        if plan is not None and plan.org_id is not None
        else []
    )
    if not org_ids:
        return Response(
            code=200,
            message="success",
            data=InspectionTaskDevicePagination(
                items=[], total=0, page=page, page_size=page_size
            ),
        )

    devices, total = await list_devices_by_scope(
        db,
        org_ids=org_ids,
        type_id=plan.device_type_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )

    items = [
        InspectionTaskDeviceItem(
            id=d.id,
            device_code=d.device_code,
            device_name=d.device_name,
            type_id=d.type_id,
            # device_type / org 已由 list_devices_by_scope 用 selectinload 预加载，
            # 这里读关系不会触发懒加载
            type_name=d.device_type.type_name if d.device_type else None,
            org_id=d.org_id,
            org_name=d.org.org_name if d.org else None,
            status=d.status,
        )
        for d in devices
    ]

    return Response(
        code=200,
        message="success",
        data=InspectionTaskDevicePagination(
            items=items, total=total, page=page, page_size=page_size
        ),
    )


def _record_out(record: InspectionRecord) -> InspectionRecordResponse:
    """
    把 ORM 记录转成响应对象。

    ⚠️ **不能**写成 `InspectionRecordResponse.model_validate(record)`：
    `device_code` / `device_name` 在 `InspectionRecord` 上**不是列**（列只有
    id/task_id/device_id/inspected_by/created_by/result/abnormal_desc/photos/
    inspected_at/...），设备信息要通过 `device` 关系取。`model_validate` 读不到
    这两个**必填**字段就抛 ValidationError → 未捕获 → 500。
    2026-09-14 admin 提交巡检记录报的正是这个。

    同一根因还有一个**静默**的：`inspected_by_name` 是 Optional，
    `model_validate` 取不到时不报错、直接给 `None`（页面空白且无提示），
    所以这里也一并显式取。

    调用方**必须**用 `_record_query()`（或等价地 selectinload 同两个关系）
    取记录：异步会话下访问未加载的关系会抛 MissingGreenlet。
    """
    return InspectionRecordResponse(
        id=record.id,
        task_id=record.task_id,
        device_id=record.device_id,
        # device_id 是非空外键，device 必然存在，不存在「取不到」的分支
        device_code=record.device.device_code,
        device_name=record.device.device_name,
        result=record.result,
        abnormal_desc=record.abnormal_desc,
        photos=record.photos or [],
        inspected_by=record.inspected_by,
        # inspected_by 可空，故这里要判空
        inspected_by_name=record.inspector.real_name if record.inspector else None,
        created_by=record.created_by,
        inspected_at=record.inspected_at,
    )


def _record_query():
    """带 device / inspector 的记录查询（`_record_out` 依赖这两个关系已加载）"""
    return select(InspectionRecord).options(
        selectinload(InspectionRecord.device),
        selectinload(InspectionRecord.inspector),
    )


@router.post(
    "/inspection-tasks/{task_id}/records",
    response_model=Response[InspectionRecordResponse],
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

    # 同 generate：service 只 flush，提交必须由这里收口，否则记录与任务状态一并回滚。
    # 注意「正常」结果只走这条路径，不提交就整条丢；「异常」结果因内部调用
    # repair_crud.create（CRUDBase.create 自带 commit）而被顺带提交——
    # 这层不一致会让缺陷看起来时有时无。
    await db.commit()

    # commit 会把对象置为过期（expire_on_commit），直接读 record.id 会触发
    # 同步刷新 → MissingGreenlet。先 await refresh 取回主键，再按主键重新查询
    # 带出 device / inspector —— 记录是刚 add() 的，这两个关系从未被加载。
    await db.refresh(record)
    full = (
        await db.execute(_record_query().where(InspectionRecord.id == record.id))
    ).scalar_one()

    return Response(code=200, message="success", data=_record_out(full))


# ==================== 巡检记录查询 ====================

@router.get(
    "/inspection-records",
    response_model=Response[InspectionRecordPagination],
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
    
    # 用 _record_query() 而不是裸 select：响应要 device_code/device_name 与
    # inspected_by_name，这三个都取自 device / inspector 关系（见 _record_out）。
    stmt = _record_query()

    # ⚠️ 日期窗口按「有没有点名 task_id」分两种口径。
    # 指定了 task_id 就**不套隐式「本月」窗口**：既然要的就是某个任务的记录，
    # 再按 inspected_at 收窄到本月毫无道理，只会静默返回空表——前端「查看记录」
    # 不传日期，于是查上个月的任务永远显示 0 行，而同一行的「已记录数」写着 3。
    # （2026-09-14 实测缺陷。）显式传进来的 start_date / end_date 仍然照常生效。
    if task_id:
        stmt = stmt.where(InspectionRecord.task_id == task_id)
        if start_date:
            stmt = stmt.where(
                InspectionRecord.inspected_at
                >= datetime.combine(start_date, datetime.min.time())
            )
        if end_date:
            stmt = stmt.where(
                InspectionRecord.inspected_at
                <= datetime.combine(end_date, datetime.max.time())
            )
    else:
        # 不指定任务时保留「本月」默认，避免列表接口全表扫描
        effective_start = start_date or (today.replace(day=1))
        effective_end = end_date or today
        stmt = stmt.where(
            InspectionRecord.inspected_at >= datetime.combine(effective_start, datetime.min.time()),
            InspectionRecord.inspected_at <= datetime.combine(effective_end, datetime.max.time()),
        )

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
    
    items = [_record_out(r) for r in results]
    
    return Response(
        code=200,
        message="success",
        data=InspectionRecordPagination(
            items=items,
            total=total or 0,
            page=page,
            page_size=page_size,
        )
    )


# ==================== 漏检统计 ====================

@router.get(
    "/inspection-missed-stats",
    response_model=Response[InspectionMissedStat],
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
    return Response(
        code=200,
        message="success",
        data=stat
    )


# 需要导入 User 模型
from app.models.user import User
