"""
联动预案 API（3.4-B4 + 3.4-B5）
- 预案 CRUD、启用/停用、模拟触发
- 手动执行预案
- 联动日志查询列表和详情
- 日志导出
"""

from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db, require_permission, get_current_active_user
from app.db.redis import get_redis_pool
from app.models.device import Device
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
    LinkageExecuteResult,
    LinkageSimulateResult,
)
from app.crud.alarm import alarm_crud
from app.crud.linkage import linkage_plan_crud, alarm_linkage_log_crud
from app.services.alarm_service import alarm_payload, publish, raise_alarm
from app.services.linkage_engine_service import linkage_engine
from app.services.linkage_executor import execute_action

# 引擎入口 `on_alarm_created` 只对这两类报警启动（见 linkage_engine_service.py），
# 模拟必须挑其中一种，否则构造出来的告警根本不会被任何预案匹配。
SIMULATABLE_ALARM_TYPES = ("fire", "pre_fire")

router = APIRouter(tags=["Linkage Plans"])


def _plan_out(plan: LinkagePlan) -> LinkagePlanOut:
    """
    ORM → 响应，补上 `org_name`。

    `organization` 关系必须已被预加载（`_load_plan` 的 selectinload，或写操作后的
    `db.refresh(plan, ["organization"])`）。异步 session 里读未加载的关系会触发
    隐式 IO，所以这里显式取值，而不是交给 `model_validate` 去碰。
    区域查不到（悬空 org_id）时给 None，不让整条记录挂掉。
    """
    return LinkagePlanOut(
        id=plan.id,
        plan_name=plan.plan_name,
        org_id=plan.org_id,
        org_name=plan.organization.org_name if plan.organization else None,
        fire_type=plan.fire_type,
        trigger_device_type_id=plan.trigger_device_type_id,
        trigger_alarm_type=plan.trigger_alarm_type,
        actions=plan.actions,
        is_enabled=plan.is_enabled,
        is_simulation_allowed=plan.is_simulation_allowed,
        created_by=plan.created_by,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


async def _load_plan(db: AsyncSession, plan_id: int) -> LinkagePlan | None:
    """按 ID 取预案，并预加载 organization（_plan_out 依赖它已就绪）"""
    stmt = (
        select(LinkagePlan)
        .options(selectinload(LinkagePlan.organization))
        .where(LinkagePlan.id == plan_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _refresh_with_org(db: AsyncSession, plan: LinkagePlan) -> None:
    """
    提交后重新加载预案，连带 organization —— 否则 `_plan_out` 取不到区域名。

    两步是刻意的：commit 会让所有属性过期，只按名刷新 organization 的话，
    其余列仍是过期状态，`_plan_out` 读它们会触发隐式 IO（异步下不可靠）。
    先整体刷新列，再单独补关系。
    """
    await db.refresh(plan)
    await db.refresh(plan, ["organization"])


def _resolve_simulate_alarm_type(plan: LinkagePlan) -> str:
    """
    挑一个**能让这条预案命中**的报警类型来模拟。

    规则与 `LinkageEngineService._matches_alarm` 对齐：`fire_type` 与
    `trigger_alarm_type` 都会被拿去和 `alarm.alarm_type` 比，所以两者同时设置
    且不同时，**没有任何报警能满足**。这类自相矛盾的配置在这里直接报错，
    而不是构造一条必然匹配不上的告警、让它静默地什么都不发生。
    """
    if (
        plan.fire_type is not None
        and plan.trigger_alarm_type is not None
        and plan.fire_type != plan.trigger_alarm_type
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"预案的「火灾类型」({plan.fire_type}) 与「触发报警类型」"
                f"({plan.trigger_alarm_type}) 不一致，而引擎要求两者同时成立，"
                f"该预案不会被任何报警触发。请把其中一个改为「不限制」或改成相同取值。"
            ),
        )

    alarm_type = plan.trigger_alarm_type or plan.fire_type or "fire"

    if alarm_type not in SIMULATABLE_ALARM_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"预案的触发类型为「{alarm_type}」，但联动引擎只对 "
                f"A 类火警(fire) 与预火灾(pre_fire) 启动，该预案不会被任何报警触发。"
                f"请把触发类型改为这两者之一或「不限制」。"
            ),
        )

    return alarm_type


async def _pick_device_in_org(db: AsyncSession, org_id: int) -> Device:
    """
    在预案所属区域里挑一台设备承载演练告警。

    `raise_alarm` 的 `device` 是必填的，且 `org_id` 从它快照
    （alarm_service.py），而预案匹配比的正是 `alarm.org_id == plan.org_id` ——
    所以「本区域没有设备」是个必须明确报错的分支，不能静默跳过。
    """
    stmt = (
        select(Device)
        .where(
            Device.org_id == org_id,
            Device.is_deleted.is_(False),
            Device.status != "retired",
        )
        .order_by(Device.id)
        .limit(1)
    )
    device = (await db.execute(stmt)).scalar_one_or_none()
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"区域(id={org_id})下没有可用设备，无法模拟。"
                f"演练告警必须挂在一台真实设备上——请先在该区域建档设备。"
            ),
        )
    return device


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
    stmt = (
        stmt.options(selectinload(LinkagePlan.organization))
        .order_by(LinkagePlan.created_at.desc())
        .offset(skip)
        .limit(page_size)
    )
    results = (await db.execute(stmt)).scalars().all()

    items = [_plan_out(plan) for plan in results]
    
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
    plan = await _load_plan(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预案不存在"
        )
    return Response(
        code=200,
        message="success",
        data=_plan_out(plan),
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
    await _refresh_with_org(db, plan)
    return Response(
        code=200,
        message="success",
        data=_plan_out(plan),
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
    await _refresh_with_org(db, plan)
    return Response(
        code=200,
        message="success",
        data=_plan_out(plan),
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
    await _refresh_with_org(db, plan)

    return Response(
        code=200,
        message="success",
        data=_plan_out(plan),
    )


@router.post(
    "/{plan_id}/simulate",
    response_model=Response[LinkageSimulateResult],
    summary="模拟测试预案",
    dependencies=[Depends(require_permission("linkage:simulate"))]
)
async def simulate_linkage_trigger(
    plan_id: int,
    remark: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis_pool),
    user: User = Depends(get_current_active_user),
):
    """
    模拟测试：生成一条**演练告警**，让预案按真实规则跑完整联动链路。

    与旧实现的区别——旧实现直接拿预案的 actions 循环执行，绕开了
    `LinkageEngineService._matches_alarm()`，因此它回答不了「这条预案到底会不会
    被触发」：`org_id` / `fire_type` / `trigger_alarm_type` 配错也照样报成功，
    而且不产生告警、不广播，报警中心与监控大屏都看不到任何痕迹。

    现在是：在预案所属区域挑设备 → 建 `is_drill=True` 的真实告警 →
    交给引擎匹配并执行 → 回报命中了哪些预案。演练告警不进统计
    （statistics_service）、不触发应急升级（emergency_service），
    但要「含演练」筛选才在报警中心可见（与既有约定一致）。

    产生的告警会广播 `alarm_new`：这是报警中心的实时增量来源，否则
    「含演练」开关打开了也得手动刷新才看得见——那正是本次重写要修的毛病。
    """
    plan = await _load_plan(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="预案不存在"
        )

    if not plan.is_simulation_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该预案已禁用模拟测试",
        )

    alarm_type = _resolve_simulate_alarm_type(plan)
    device = await _pick_device_in_org(db, plan.org_id)

    location = f"模拟测试：预案「{plan.plan_name}」"
    if remark:
        location = f"{location}；{remark}"

    alarm, created = await raise_alarm(
        db,
        device,
        alarm_type,
        is_drill=True,
        location_description=location,
        created_by=user.id,
    )

    if not created:
        # raise_alarm 按 (device_id, alarm_type, 未收敛状态) 去重，**且不看 is_drill**。
        # 撞上真实告警时绝不能拿它当演练跑——那等于对着一次真火警做模拟。
        if not alarm.is_drill:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"设备「{device.device_name}」上已有未处理的 {alarm_type} 告警"
                    f"（id={alarm.id}），模拟测试不会复用真实告警。"
                    f"请先处置该告警，或改用该区域的其它设备。"
                ),
            )
        # 既有的是上次演练留下的 → 复用它，重复点击即幂等

    await db.commit()

    # 广播给已打开的大屏 / 报警中心。与上报路径同口径
    # （`device_report_service.handle_device_report`）：只在**新建**报警时推，
    # 幂等复用不重复推，否则报警中心会把同一条演练告警当成新的播两遍。
    #
    # 只推 `alarm_new`，**不推 `device_status`**：模拟不改变设备状态
    # （`raise_alarm` 不写 `devices.status`），推了等于凭空宣告一次状态变更。
    #
    # 演练帧不会误鸣笛——前端已按 `is_drill` 拦下（`stores/monitor.js:207`），
    # 报警中心的「含演练」开关也正需要这份增量做实时显隐（`Center.vue:363`）。
    if created:
        fresh = await alarm_crud.get_with_relations(db, alarm.id)
        await publish(redis, "alarm_new", alarm_payload(fresh))

    # 只回报本次新产生的日志：复用演练告警时，库里还有上一轮的记录
    before_id = (await db.execute(
        select(func.max(AlarmLinkageLog.id)).where(AlarmLinkageLog.alarm_id == alarm.id)
    )).scalar() or 0

    # 同步 await 而非 create_task：调用方需要立刻知道命中了什么
    await linkage_engine.on_alarm_created(db, alarm)

    rows = (await db.execute(
        select(AlarmLinkageLog)
        .where(
            AlarmLinkageLog.alarm_id == alarm.id,
            AlarmLinkageLog.id > before_id,
        )
        .order_by(AlarmLinkageLog.id)
    )).scalars().all()

    matched_ids = sorted({log.plan_id for log in rows if log.plan_id is not None})

    names: list[str] = []
    if matched_ids:
        name_rows = (await db.execute(
            select(LinkagePlan.id, LinkagePlan.plan_name)
            .where(LinkagePlan.id.in_(matched_ids))
        )).all()
        by_id = {r.id: r.plan_name for r in name_rows}
        names = [by_id[i] for i in matched_ids if i in by_id]

    return Response(
        code=200,
        message="success",
        data=LinkageSimulateResult(
            alarm_id=alarm.id,
            alarm_type=alarm.alarm_type,
            org_id=alarm.org_id,
            device_id=device.id,
            device_code=device.device_code,
            is_drill=True,
            matched_plan_ids=matched_ids,
            matched_plan_names=names,
            included_self=plan.id in matched_ids,
            logs=[AlarmLinkageLogOut.model_validate(log) for log in rows],
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
