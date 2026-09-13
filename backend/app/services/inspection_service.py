"""
巡检业务服务层（3.6 B-10）
==========================
核心功能：
1. 巡检计划管理（CRUD + 统计）
2. 任务自动生成（按周期规则）
3. 手动触发任务生成
4. 漏检扫描与预警通知

技术选型：
- 3.6 阶段暂不引入 Celery，使用 FastAPI lifespan + asyncio.create_task()
- 所有定时任务均通过 asyncio 实现（DEC-043）
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import false, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthError
from app.crud.inspection import inspection_plan_crud, inspection_task_crud, inspection_record_crud
from app.models.inspection import (
    InspectionPlan,
    InspectionTask,
    InspectionRecord,
    InspectionCycleType,
    InspectionTaskStatus,
)
from app.models.device import Device
from app.models.user import User


# ==================== 辅助函数 ====================

def _is_duplicate_task_error(exc: IntegrityError) -> bool:
    """
    区分「(plan_id, task_date) 撞唯一约束」与其它完整性错误。

    这个区分是必须的：FK 违例（如计划的责任人已被删除）同样是 IntegrityError，
    若一并当成「已存在」吞掉，任务会**静默不生成**——比报错更难发现。

    - PostgreSQL/asyncpg：唯一违例 sqlstate 为 23505（FK 违例是 23503）
    - SQLite/aiosqlite：无 sqlstate，回退到错误文案匹配
    """
    orig = getattr(exc, "orig", None)
    if getattr(orig, "sqlstate", None) == "23505":
        return True
    text = str(orig or exc).lower()
    return "unique" in text or "uq_inspection_tasks_plan_date" in text


async def apply_task_data_scope(query, user: User, db: AsyncSession):
    """
    按用户 data_scope 过滤巡检任务（3.6 计划第 278 行）。

    **刻意不复用 `user_service.apply_data_scope`**：那个函数对 `self` 锚
    `created_by`、对 `dept` 锚 `org_id`，而 `InspectionTask` 两个字段都没有
    （见 `app/models/inspection.py`），`hasattr` 守卫会让它静默返回原查询——
    表现是「过滤像是调了，实际谁都能看全部」，比不调更危险。

    任务的口径：
    - `all`  -> 不过滤
    - `self` -> 只看责任人是自己的任务（任务的「归属」是 responsible_user_id，
               不是 created_by——后者是生成任务的操作人，通常是管理员）
    - `dept` -> 只看本部门及子部门（经 plan.org_id）下的任务
    """
    if user.data_scope == "all":
        return query

    if user.data_scope == "dept":
        if user.org_id is None:
            return query.where(false())

        from app.models.organization import Organization

        cte = (
            select(Organization.id)
            .where(Organization.id == user.org_id)
            .cte(recursive=True)
        )
        cte = cte.union_all(
            select(Organization.id).where(Organization.parent_id == cte.c.id)
        )
        org_ids = [row[0] for row in (await db.execute(select(cte.c.id))).all()]

        if not org_ids:
            return query.where(false())

        plan_ids = select(InspectionPlan.id).where(InspectionPlan.org_id.in_(org_ids))
        return query.where(InspectionTask.plan_id.in_(plan_ids))

    # self（含未识别的取值，取最小可见权限）
    return query.where(InspectionTask.responsible_user_id == user.id)


def is_cycle_due(cycle_type: str, target_date: date) -> bool:
    """
    判断某计划在 target_date 这天是否该生成任务（3.6 计划 §3.2「周期类型与任务生成规则」）。

    | cycle_type | 生成规则                        |
    |------------|---------------------------------|
    | daily      | 每天 1 条                       |
    | weekly     | 每周一                          |
    | monthly    | 每月 1 日                       |
    | quarterly  | 每季度首月 1 日（1/4/7/10 月 1 日）|
    | yearly     | 每年 1 月 1 日                  |

    与 `get_next_dates_by_cycle()` 的口径差异是**刻意**的：那个服务手工生成，
    从 start_date 起按周期步进 N 个日期——用户自己选跨度，可以生成任意日期；
    这里是定时任务，按自然日历判断「今天该不该生成」，必须守 §3.2。
    没有这层判断，一个 weekly 计划会被每天建一条任务（7 倍）。

    未知取值一律返回 False 并告警：宁可少生成（可人工补），也不要按日创建垃圾任务。
    """
    if cycle_type == InspectionCycleType.daily.value:
        return True
    if cycle_type == InspectionCycleType.weekly.value:
        return target_date.weekday() == 0  # 周一
    if cycle_type == InspectionCycleType.monthly.value:
        return target_date.day == 1
    if cycle_type == InspectionCycleType.quarterly.value:
        return target_date.month in (1, 4, 7, 10) and target_date.day == 1
    if cycle_type == InspectionCycleType.yearly.value:
        return target_date.month == 1 and target_date.day == 1

    print(f"[WARN] 未知的巡检周期 cycle_type={cycle_type!r}，跳过该计划的自动生成")
    return False


def get_next_dates_by_cycle(start_date: date, cycle_type: InspectionCycleType, count: int) -> List[date]:
    """
    根据周期类型获取未来的日期列表
    
    Args:
        start_date: 开始日期
        cycle_type: 周期类型
        count: 需要生成的日期数量
        
    Returns:
        日期列表
    """
    dates = []
    current_date = start_date
    
    while len(dates) < count:
        dates.append(current_date)
        
        if cycle_type == InspectionCycleType.daily:
            current_date += timedelta(days=1)
        elif cycle_type == InspectionCycleType.weekly:
            current_date += timedelta(weeks=1)
        elif cycle_type == InspectionCycleType.monthly:
            # 下个月同一天，如果不存在则取月底
            try:
                current_date = current_date.replace(month=current_date.month + 1, day=current_date.day)
            except ValueError:
                # 2 月 30 日不存在，取 2 月最后一天
                next_month = current_date.month + 1
                next_year = current_date.year
                if next_month > 12:
                    next_month = 1
                    next_year += 1
                
                # 查找月末天数
                for day in range(28, 32):
                    try:
                        current_date = current_date.replace(year=next_year, month=next_month, day=day)
                    except ValueError:
                        continue
                    break
        elif cycle_type == InspectionCycleType.quarterly:
            # 每季度第一天
            current_month = ((current_date.month - 1) // 3 + 1) * 3 + 1
            if current_month > 12:
                current_month = 1
                current_date = current_date.replace(year=current_date.year + 1, month=1, day=1)
            else:
                current_date = current_date.replace(month=current_month, day=1)
        elif cycle_type == InspectionCycleType.yearly:
            current_date = current_date.replace(year=current_date.year + 1, day=current_date.day)
    
    return dates


async def generate_tasks_for_plan(
    db: AsyncSession,
    plan_id: int,
    target_date: Optional[date] = None,
) -> List[InspectionTask]:
    """
    为某巡检计划在指定日期生成任务
    
    Args:
        db: 数据库会话
        plan_id: 计划 ID
        target_date: 目标日期（默认今天），否则生成未来 N 天的任务
        
    Returns:
        新创建的任务列表

    Raises:
        AuthError: 计划不存在或已禁用

    Note:
        **本函数只 `flush`，不 `commit`。** `get_db` 依赖在 finally 里只 close 不 commit，
        未提交的事务会被回滚，所以调用方必须显式 `await db.commit()`
        ——循环调用时在循环外提交一次即可。漏掉就会「接口返回了任务、库里一行没有」。
        （`CRUDBase.create` 自带 commit，手写 `db.add` 的路径没有这层保护。）
    """
    # 1. 获取计划详情
    stmt = (
        select(InspectionPlan)
        .where(InspectionPlan.id == plan_id)
        .options(selectinload(InspectionPlan.organization))
        .options(selectinload(InspectionPlan.device_type))
        .options(selectinload(InspectionPlan.responsible_user))
    )
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    
    if not plan:
        raise AuthError(404, "巡检计划不存在")
    
    if not plan.is_enabled:
        raise AuthError(400, "该巡检计划已禁用")
    
    # 2. 确定任务日期范围
    if target_date is None:
        target_date = date.today()
    
    # 检查是否已存在（同计划同日期只生成一次）
    existing_stmt = select(InspectionTask).where(
        InspectionTask.plan_id == plan_id,
        InspectionTask.task_date == target_date,
    ).limit(1)
    existing_task = (await db.execute(existing_stmt)).scalars().first()
    
    if existing_task:
        # 已存在则跳过
        return []
    
    # 3. 创建任务
    task = InspectionTask(
        plan_id=plan_id,
        task_date=target_date,
        responsible_user_id=plan.responsible_user_id,
        status="pending",
        created_at=datetime.now(),
    )
    # 用 SAVEPOINT 包住插入：并发下两个请求可能都通过了上面的 check-then-act，
    # 由 uq_inspection_tasks_plan_date 兜底。**不能直接 `db.rollback()`**——
    # 那会回滚整个外层事务，把同批已生成的前几个计划一起丢掉。
    try:
        async with db.begin_nested():
            db.add(task)
            await db.flush()
    except IntegrityError as exc:
        if _is_duplicate_task_error(exc):
            return []
        raise  # 其它完整性错误（如责任人已被删导致的 FK 违例）交给调用方记录

    return [task]


async def generate_daily_tasks(db: AsyncSession, target_date: date) -> Dict[str, Any]:
    """
    为所有「启用中且有效期覆盖 target_date」的计划生成当日任务（3.6 FR-033）。

    这是每日 00:05 调度的主体逻辑，也是手动补跑/测试的直接入口（不碰循环、不 sleep）。

    与 `/inspection-plans/{id}/generate` 手接口的差别：
    - 手接口由用户自选日期，**不看计划有效期**；自动生成必须尊重计划窗口，
      否则会给一个早已结束的计划天天建任务。
    - 逐计划隔离失败：某个计划出错（如责任人已被删除导致 FK 违例）不影响其它计划。

    Args:
        db: 数据库会话（调用方持有，便于测试注入）
        target_date: 要生成的任务日期，**由调用方按业务时区算好传入**
            （见 app/core/timezone.py）。本函数不自己问「今天几号」。

    Returns:
        {"date", "plans", "created", "skipped", "failed", "errors"}
    """
    stmt = (
        select(InspectionPlan.id, InspectionPlan.cycle_type)
        .where(
            InspectionPlan.is_enabled.is_(True),
            or_(
                InspectionPlan.start_date.is_(None),
                InspectionPlan.start_date <= target_date,
            ),
            or_(
                InspectionPlan.end_date.is_(None),
                InspectionPlan.end_date >= target_date,
            ),
        )
        .order_by(InspectionPlan.id)
    )
    rows = (await db.execute(stmt)).all()

    # 按周期规则筛出「今天该生成」的计划（weekly 只在周一、monthly 只在 1 号…）
    plan_ids: List[int] = [
        plan_id
        for plan_id, cycle_type in rows
        if is_cycle_due(cycle_type, target_date)
    ]

    created = skipped = failed = 0
    errors: List[Dict[str, Any]] = []

    for plan_id in plan_ids:
        try:
            # 每个计划一个 SAVEPOINT：单个失败只回滚它自己，不影响同批其它计划，
            # 也不会污染外层会话（后续查询照常可用）。
            async with db.begin_nested():
                tasks = await generate_tasks_for_plan(db, plan_id, target_date)
        except Exception as exc:  # noqa: BLE001 - 一个计划失败不能拖垮整批
            failed += 1
            errors.append({"plan_id": plan_id, "error": f"{type(exc).__name__}: {exc}"})
            continue

        if tasks:
            created += len(tasks)
        else:
            skipped += 1

    # 统一收口提交。generate_tasks_for_plan 只 flush 不 commit，而 get_db 在
    # finally 里只 close 不 commit —— 漏掉这一步，整批任务会被静默回滚，
    # 表现是「接口说生成了 N 条、库里 0 行」（testing-guidelines 第 23 条）。
    await db.commit()

    return {
        "date": target_date.isoformat(),
        "plans": len(plan_ids),
        "created": created,
        "skipped": skipped,
        "failed": failed,
        # 截断：几百个坏计划不该把返回体和调度器日志刷爆，总数另给
        "errors": errors[:20],
        "errors_total": len(errors),
    }


async def scan_missed_tasks(
    db: AsyncSession,
    before_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    扫描漏检任务
    
    逻辑：
    1. 找出所有已过期的 pending/doing 状态任务
    2. 标记为 missed
    3. 统计漏检次数超过 3 次的计划，准备发送预警通知
    
    Args:
        db: 数据库会话
        before_date: 截止日期（默认昨天）
        
    Returns:
        扫描结果统计
    """
    if before_date is None:
        before_date = date.today() - timedelta(days=1)
    
    # 1. 查询待扫描的任务
    stmt = (
        select(InspectionTask)
        .where(
            InspectionTask.task_date < before_date,
            InspectionTask.status.in_(["pending", "doing"]),
        )
        .options(selectinload(InspectionTask.plan))
    )
    result = await db.execute(stmt)
    tasks_to_mark = result.scalars().all()
    
    marked_count = 0
    missed_plans = {}  # plan_id -> {'count': int, 'plan': InspectionPlan}
    
    for task in tasks_to_mark:
        task.status = "missed"
        db.add(task)
        marked_count += 1
        
        # 统计该计划的累计漏检数
        plan_id = task.plan.id
        if plan_id not in missed_plans:
            plan_count_stmt = (
                select(InspectionTask)
                .where(
                    InspectionTask.plan_id == plan_id,
                    InspectionTask.status == "missed",
                )
            )
            plan_missed_list = (await db.execute(plan_count_stmt)).scalars().all()
            missed_plans[plan_id] = {
                "count": len(plan_missed_list),
                "plan": task.plan
            }
    
    await db.commit()
    
    # 2. 准备预警通知（漏检≥3 次）
    alert_plans = [
        {"plan_id": pid, "plan": data["plan"], "missed_count": data["count"]}
        for pid, data in missed_plans.items()
        if data["count"] >= 3
    ]
    
    return {
        "total_scanned": len(tasks_to_mark),
        "marked_missed": marked_count,
        "alert_count": len(alert_plans),
        "alert_plans": alert_plans
    }


async def submit_inspection_record(
    db: AsyncSession,
    *,
    task_id: int,
    device_id: int,
    result: str,
    abnormal_desc: Optional[str] = None,
    photos: Optional[List[str]] = None,
    inspected_by: Optional[int] = None,
    created_by: Optional[int] = None,
) -> InspectionRecord:
    """
    提交巡检记录
    
    Args:
        db: 数据库会话
        task_id: 任务 ID
        device_id: 设备 ID
        result: 巡检结果（normal/abnormal）
        abnormal_desc: 异常情况描述
        photos: 照片 URL 数组
        inspected_by: 检查人 ID
        created_by: 创建人 ID（默认与 inspected_by 相同）
        
    Returns:
        创建的巡检记录
        
    Raises:
        AuthError: 任务不存在或状态异常
    """
    # 1. 验证任务存在且可执行
    stmt = (
        select(InspectionTask)
        .where(InspectionTask.id == task_id)
        .options(selectinload(InspectionTask.plan))
        .options(selectinload(InspectionTask.responsible_user))
    )
    task = (await db.execute(stmt)).scalar_one_or_none()
    
    if not task:
        raise AuthError(404, "巡检任务不存在")
    
    if task.status not in ["pending", "doing"]:
        raise AuthError(400, f"任务状态为{task.status}，不可提交记录")
    
    # 2. 验证设备属于该任务的巡检范围（如果计划有 device_type_id 限制）
    if task.plan.device_type_id:
        device_stmt = select(Device).where(Device.id == device_id)
        device = (await db.execute(device_stmt)).scalar_one_or_none()
        if not device or device.type_id != task.plan.device_type_id:
            raise AuthError(400, "该设备不在本次巡检范围内")
    
    # 3. 设置检查人与创建人
    if inspected_by is None:
        inspected_by = task.responsible_user_id
    
    if created_by is None:
        created_by = inspected_by
    
    # 4. 创建记录
    record = InspectionRecord(
        task_id=task_id,
        device_id=device_id,
        result=result,
        abnormal_desc=abnormal_desc,
        photos=photos or [],
        inspected_by=inspected_by,
        created_by=created_by,
        inspected_at=datetime.now(),
    )
    db.add(record)
    
    # 5. 更新任务状态
    if task.status == "pending":
        task.status = "doing"
    await db.flush()
    
    # 6. 巡检异常自动创建维修工单（3.7 FR-038）
    if result == "abnormal":
        from app.crud.repair import RepairOrderCRUD
        from app.schemas.repair import RepairOrderCreate
        
        # 幂等性检查：避免重复创建
        repair_crud = RepairOrderCRUD(db)
        existing_order = await repair_crud.get_by_inspection_record(record.id)
        
        if not existing_order:
            # 自动创建维修工单
            order_create = RepairOrderCreate(
                device_id=device_id,
                inspection_record_id=record.id,
                fault_desc=abnormal_desc or "巡检发现异常",
            )
            await repair_crud.create(order_create, created_by=created_by)
    
    return record


class InspectionService:
    """巡检管理服务"""
    
    @staticmethod
    async def create_plan(
        db: AsyncSession,
        *,
        data: Dict[str, Any],
        user_id: int,
    ) -> InspectionPlan:
        """创建巡检计划"""
        plan = InspectionPlan(**data)
        db.add(plan)
        await db.commit()
        await db.refresh(plan)
        return plan
    
    @staticmethod
    async def update_plan(
        db: AsyncSession,
        *,
        plan_id: int,
        data: Dict[str, Any],
    ) -> Optional[InspectionPlan]:
        """更新巡检计划"""
        plan = await inspection_plan_crud.get(db, id=plan_id)
        if not plan:
            return None
        
        update_data = {k: v for k, v in data.items() if k in plan.__dict__ and k not in ["id", "created_at"]}
        plan.update(**update_data)
        await db.commit()
        await db.refresh(plan)
        return plan
    
    @staticmethod
    async def delete_plan(db: AsyncSession, *, plan_id: int) -> bool:
        """删除巡检计划（仅未启用的）"""
        plan = await inspection_plan_crud.get(db, id=plan_id)
        if not plan:
            return False
        
        if plan.is_enabled:
            raise AuthError(400, "已启用的计划无法直接删除，请先停用")
        
        await inspection_plan_crud.delete(db, id=plan_id)
        return True
    
    @staticmethod
    async def toggle_plan_status(
        db: AsyncSession,
        *,
        plan_id: int,
        is_enabled: bool,
    ) -> Optional[InspectionPlan]:
        """启用/停用巡检计划"""
        plan = await inspection_plan_crud.get(db, id=plan_id)
        if not plan:
            return None
        
        plan.is_enabled = is_enabled
        await db.commit()
        await db.refresh(plan)
        return plan
    
    @staticmethod
    async def manual_generate_tasks(
        db: AsyncSession,
        *,
        plan_id: int,
        days: int = 7,
    ) -> List[InspectionTask]:
        """
        手动为某计划生成未来 N 天的任务
        
        Args:
            db: 数据库会话
            plan_id: 计划 ID
            days: 生成天数
            
        Returns:
            新创建的任务列表
        """
        plan = await inspection_plan_crud.get(db, id=plan_id)
        if not plan:
            raise AuthError(404, "计划不存在")
        
        if not plan.is_enabled:
            raise AuthError(400, "计划已禁用")
        
        generated = []
        start_date = date.today()
        future_dates = get_next_dates_by_cycle(start_date, plan.cycle_type, days)
        
        for target_date in future_dates:
            tasks = await generate_tasks_for_plan(db, plan_id, target_date)
            generated.extend(tasks)

        # 与 API 端点同样的收口：generate_tasks_for_plan 只 flush，调用方必须提交
        await db.commit()

        return generated
    
    @staticmethod
    async def get_task_statistics(
        db: AsyncSession,
        user_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        获取用户巡检统计数据
        
        Returns:
            统计信息：{
                "total_tasks": int,
                "completed_tasks": int,
                "missed_tasks": int,
                "completion_rate": float
            }
        """
        today = date.today()
        start = start_date or date(today.year, today.month, 1)
        end = end_date or today
        
        stmt = (
            select(InspectionTask)
            .where(
                InspectionTask.responsible_user_id == user_id,
                InspectionTask.task_date >= start,
                InspectionTask.task_date <= end,
            )
        )
        tasks = (await db.execute(stmt)).scalars().all()
        
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == "completed")
        missed = sum(1 for t in tasks if t.status == "missed")
        
        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "missed_tasks": missed,
            "completion_rate": round(completed / total, 4) if total > 0 else 0.0,
        }
