"""
应急事件核心服务
3.5 模块 - B2/B3

- create_emergency_event: 建事件 + 两条初始时间轴；由
  `alarm_service.confirm_alarm()` 确认真实火警时调用（3.5-B2 的接线在那边，
  本模块只提供实现）。只 flush 不 commit，与调用方共用一个事务。
- escalation_scan: 5 分钟超时扫描升级
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.emergency import EmergencyEvent, EmergencyTimeline, Notification
from app.schemas.emergency import EmergencyTimelineCreate
from app.core.config import get_settings
from app.core.timezone import today_in_app_tz


settings = get_settings()


def _iso(value) -> Optional[str]:
    """datetime → ISO8601；None 原样返回（前端 formatTime 容忍空值）"""
    return value.isoformat() if value is not None else None


def event_payload(event: EmergencyEvent) -> dict:
    """
    应急事件的 JSON 载荷。

    路由声明的是 `response_model=dict`，Pydantic 不会代转 ORM 对象 ——
    直接把 ORM 塞进 dict 会抛 `PydanticSerializationError` → 500。
    空表时 items 为空列表、没有对象需要序列化，所以这个缺陷只在
    **事件真的存在之后**才暴露（即本模块接线修好的那一刻）。
    """
    return {
        "id": event.id,
        "alarm_id": event.alarm_id,
        "event_no": event.event_no,
        "status": event.status,
        "started_at": _iso(event.started_at),
        "resolved_at": _iso(event.resolved_at),
        "closed_at": _iso(event.closed_at),
        "closed_by": event.closed_by,
        "summary": event.summary,
        "created_by": event.created_by,
        "created_at": _iso(event.created_at),
        "updated_at": _iso(event.updated_at),
    }


def timeline_payload(node: EmergencyTimeline) -> dict:
    """时间轴节点的 JSON 载荷"""
    return {
        "id": node.id,
        "event_id": node.event_id,
        "node_type": node.node_type,
        "node_title": node.node_title,
        "description": node.description,
        "operator_id": node.operator_id,
        "operated_at": _iso(node.operated_at),
        "attachments": node.attachments or [],
        "created_at": _iso(node.created_at),
    }


def user_brief(user) -> Optional[dict]:
    """用户摘要（详情页的创建人/关闭人），不泄露手机号等敏感字段"""
    if user is None:
        return None
    return {"id": user.id, "username": user.username, "real_name": user.real_name}


async def create_emergency_event(
    session: AsyncSession,
    alarm_id: int,
    creator_id: int
) -> Optional[EmergencyEvent]:
    """
    创建应急事件（在真实火警确认时自动调用）

    只 flush 不 commit —— 必须与调用方（confirm_alarm）在同一事务内提交，
    否则会出现「报警已确认、事件没建」的中间态。

    Args:
        session: DB Session
        alarm_id: 关联报警 ID
        creator_id: 创建人 ID

    Returns:
        创建成功的 EmergencyEvent 实例；该报警已有事件时返回 None（幂等）
    """
    # 幂等：一条报警最多一个处置事件（emergency_events.alarm_id 有唯一约束，
    # 这里显式短路，避免把唯一约束冲突留给调用方去处理）
    existing = await session.execute(
        select(EmergencyEvent).where(EmergencyEvent.alarm_id == alarm_id)
    )
    if existing.scalars().first() is not None:
        return None

    # 生成事件编号 EV-YYYYMMDD-NNN
    # 日期段问的是「今天是几号」——容器跑 UTC，直接 datetime.now() 会在
    # 北京时间 00:00–08:00 之间产出前一天的编号，故走业务时区（app/core/timezone.py）。
    date_str = today_in_app_tz().strftime("%Y%m%d")

    # 查询今日已有事件数
    stmt = select(EmergencyEvent).where(
        EmergencyEvent.event_no.startswith(f"EV-{date_str}-")
    )
    result = await session.execute(stmt)
    existing_events = result.scalars().all()
    seq_num = len(existing_events) + 1
    event_no = f"EV-{date_str}-{seq_num:03d}"
    
    # 创建事件
    event = EmergencyEvent(
        alarm_id=alarm_id,
        event_no=event_no,
        status="processing",
        created_by=creator_id
    )
    session.add(event)
    await session.flush()  # 获取 ID
    
    # 插入 timeline 节点：alarm + confirm
    # 1. alarm 节点
    alarm_timeline = EmergencyTimeline(
        event_id=event.id,
        node_type="alarm",
        node_title="火警产生",
        description=f"报警 ID:{alarm_id}触发应急处置流程",
        operator_id=creator_id
    )
    session.add(alarm_timeline)
    
    # 2. confirm 节点
    confirm_timeline = EmergencyTimeline(
        event_id=event.id,
        node_type="confirm",
        node_title="确认真实火警",
        description="值班员现场确认为真实火警",
        operator_id=creator_id
    )
    session.add(confirm_timeline)
    
    await session.flush()
    return event


async def scan_pending_alarms_for_escalation(session: AsyncSession):
    """
    扫描待确认报警，超时 5 分钟未确认则升级通知主管
    
    调用时机：FastAPI lifespan 后台任务，每 60 秒执行一次
    """
    timeout_threshold = datetime.now() - timedelta(minutes=5)
    
    # 查找超时的 pending 报警（演练除外）
    from app.models.alarm import Alarm
    stmt = select(Alarm).where(
        Alarm.status == "pending",
        Alarm.is_drill == False,
        Alarm.pending_since <= timeout_threshold
    )
    result = await session.execute(stmt)
    overdue_alarms = result.scalars().all()
    
    if not overdue_alarms:
        return 0
    
    # 检查是否已发送过升级通知（通过 timeline 去重）
    escalated_event_ids = set()
    for alarm in overdue_alarms:
        if alarm.emergency_event:
            stmt = select(EmergencyTimeline).where(
                EmergencyTimeline.event_id == alarm.emergency_event.id,
                EmergencyTimeline.node_type == "escalation"
            )
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                continue
            escalated_event_ids.add(alarm.emergency_event.id)
    
    if not escalated_event_ids:
        return 0
    
    # 查询所有主管用户
    from app.models.user import User, Role
    stmt = select(Role).where(Role.role_code == "chief")
    role_result = await session.execute(stmt)
    chief_role = role_result.scalar_one_or_none()
    
    if not chief_role:
        return 0
    
    stmt = select(User).where(User.roles.contains(chief_role))
    user_result = await session.execute(stmt)
    chiefs = user_result.scalars().all()
    
    # 为每个主管创建通知
    notifications_created = 0
    for event_id in escalated_event_ids:
        for chief in chiefs:
            notification = Notification(
                user_id=chief.id,
                title="火警待确认升级通知",
                content="有火警待确认超过 5 分钟，请主管关注处置",
                module="emergency",
                ref_id=event_id,
                is_read=False
            )
            session.add(notification)
            notifications_created += 1
    
    return notifications_created


class EmergencyEscalationTask:
    """超时升级后台任务（lifespan 启动）"""
    
    def __init__(self, interval_seconds: int = 60):
        self.interval = interval_seconds
        self._task: Optional[asyncio.Task] = None
    
    async def start(self, engine):
        """启动后台任务"""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        
        AsyncSessionLocal = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
        
        async def scan_loop():
            while True:
                try:
                    async with AsyncSessionLocal() as session:
                        count = await scan_pending_alarms_for_escalation(session)
                        if count > 0:
                            print(f"[EmergencyEscalation] 创建 {count} 条升级通知")
                except Exception as e:
                    print(f"[EmergencyEscalation] Scan error: {e}")
                await asyncio.sleep(self.interval)
        
        self._task = asyncio.create_task(scan_loop())
    
    async def stop(self):
        """停止后台任务"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


async def add_timeline_node(
    session: AsyncSession,
    event_id: int,
    node_type: str,
    operator_id: int,
    node_title: Optional[str] = None,
    description: Optional[str] = None,
    attachments: Optional[list[dict]] = None
) -> EmergencyTimeline:
    """
    添加入置时间轴节点
    
    Args:
        session: DB Session
        event_id: 事件 ID
        node_type: 节点类型 (alarm/confirm/linkage/escalation/evacuate/control/check_in/photo/complete)
        operator_id: 操作人 ID
        node_title: 节点标题
        description: 描述
        attachments: 附件列表 [{type, url}]
        
    Returns:
        创建成功的时间轴节点
    """
    timeline = EmergencyTimeline(
        event_id=event_id,
        node_type=node_type,
        node_title=node_title or "",
        description=description or "",
        operator_id=operator_id,
        attachments=attachments or []
    )
    session.add(timeline)
    await session.flush()
    # `operated_at` / `created_at` 是 server_default 列：flush 后取值会在**同步**栈上
    # 触发懒加载刷新，async 下即 MissingGreenlet → 500。显式 refresh 把这一步变成
    # 可 await 的 IO。
    await session.refresh(timeline)
    return timeline


async def resolve_emergency_event(
    session: AsyncSession,
    event_id: int,
    summary: Optional[str],
    resolver_id: int
) -> EmergencyEvent:
    """
    标记应急事件处置完成
    
    Args:
        session: DB Session
        event_id: 事件 ID
        summary: 处置总结
        resolver_id: 完成操作人 ID
        
    Returns:
        更新后的 EmergencyEvent
    """
    stmt = select(EmergencyEvent).where(EmergencyEvent.id == event_id)
    event = (await session.execute(stmt)).scalar_one_or_none()
    
    if not event:
        raise ValueError(f"Event {event_id} not found")
    
    event.status = "resolved"
    event.resolved_at = datetime.now()
    if summary:
        event.summary = summary
    
    # 添加 complete 节点
    timeline = EmergencyTimeline(
        event_id=event.id,
        node_type="complete",
        node_title="处置完成",
        description=summary or "",
        operator_id=resolver_id
    )
    session.add(timeline)

    await session.flush()
    # `updated_at` 带 onupdate，flush 后取值同样会触发同步懒加载 → MissingGreenlet
    await session.refresh(event)
    return event


async def close_emergency_event(
    session: AsyncSession,
    event_id: int,
    closer_id: int
) -> EmergencyEvent:
    """
    强制关闭应急事件（主管权限）
    
    Args:
        session: DB Session
        event_id: 事件 ID
        closer_id: 关闭人 ID
        
    Returns:
        更新后的 EmergencyEvent
    """
    stmt = select(EmergencyEvent).where(EmergencyEvent.id == event_id)
    event = (await session.execute(stmt)).scalar_one_or_none()
    
    if not event:
        raise ValueError(f"Event {event_id} not found")
    
    event.status = "closed"
    event.closed_at = datetime.now()
    event.closed_by = closer_id
    
    # 添加 complete 节点（如果尚未存在）
    has_complete = False
    stmt = select(EmergencyTimeline).where(
        EmergencyTimeline.event_id == event_id,
        EmergencyTimeline.node_type == "complete"
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        has_complete = True
    
    if not has_complete:
        timeline = EmergencyTimeline(
            event_id=event.id,
            node_type="complete",
            node_title="事件关闭",
            description="主管强制关闭长期未决事件",
            operator_id=closer_id
        )
        session.add(timeline)

    await session.flush()
    await session.refresh(event)
    return event


# ==================== 通知中心服务 ====================

async def get_user_notifications(
    session: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    module: Optional[str] = None
):
    """
    获取用户通知列表（分页）
    
    Args:
        session: DB Session
        user_id: 用户 ID
        page: 页码
        page_size: 每页数量
        module: 模块筛选（emergency/linkage/system）
        
    Returns:
        分页结果 {"items": [...], "total": N, "page": P, ...}
    """
    from app.models.emergency import Notification as NotificationModel
    
    base_stmt = select(NotificationModel).where(NotificationModel.user_id == user_id)
    if module:
        base_stmt = base_stmt.where(NotificationModel.module == module)
    
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one_or_none() or 0
    
    stmt = base_stmt.order_by(NotificationModel.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)
    
    result = await session.execute(stmt)
    notifications = result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    
    return {
        "items": notifications,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


async def mark_notifications_as_read(
    session: AsyncSession,
    user_id: int,
    notification_ids: list[int]
):
    """
    批量标记通知为已读
    
    Args:
        session: DB Session
        user_id: 用户 ID
        notification_ids: 通知 ID 列表
        
    Returns:
        更新的记录数
    """
    from app.models.emergency import Notification as NotificationModel
    
    stmt = update(NotificationModel).where(
        NotificationModel.user_id == user_id,
        NotificationModel.id.in_(notification_ids)
    ).values(is_read=True)
    
    result = await session.execute(stmt)
    return result.rowcount


async def get_unread_count(
    session: AsyncSession,
    user_id: int
) -> int:
    """
    获取用户未读通知数量
    
    Args:
        session: DB Session
        user_id: 用户 ID
        
    Returns:
        未读数
    """
    from app.models.emergency import Notification as NotificationModel
    
    stmt = select(NotificationModel).where(
        NotificationModel.user_id == user_id,
        NotificationModel.is_read == False
    )
    result = await session.execute(stmt)
    return len(result.scalars().all())
