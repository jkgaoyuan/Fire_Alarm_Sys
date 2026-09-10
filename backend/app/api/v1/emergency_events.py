"""
应急事件 API（3.5 B4/B5）
- GET /emergency-events - 列表查询
- GET /emergency-events/{id} - 详情
- POST /emergency-events/{id}/resolve - 处置完成
- POST /emergency-events/{id}/close - 强制关闭
- GET /emergency-events/{id}/timeline - 时间轴列表
- POST /emergency-events/{id}/timeline - 添加节点
"""

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.emergency import (
    EmergencyEventListOut,
    EmergencyEventDetailOut,
    EmergencyTimelineCreate,
    EmergencyTimelineListOut,
)
from app.services.emergency_service import (
    resolve_emergency_event,
    close_emergency_event,
    add_timeline_node,
)
from app.services.emergency_report_service import generate_event_report

router = APIRouter()


async def check_data_scope(event_id: int, user: User, db: AsyncSession):
    """检查用户是否有权限查看该事件（基于数据范围）"""
    from app.models.emergency import EmergencyEvent
    
    stmt = select(EmergencyEvent).where(EmergencyEvent.id == event_id)
    event = (await db.execute(stmt)).scalar_one_or_none()
    
    if not event:
        return None
    
    # 获取关联报警的 org_id
    from app.models.alarm import Alarm
    alarm_stmt = select(Alarm).where(Alarm.id == event.alarm_id)
    alarm = (await db.execute(alarm_stmt)).scalar_one_or_none()
    
    if not alarm:
        return None
    
    # 数据权限控制
    if user.data_scope == "all":
        return event
    elif user.data_scope == "self" and event.created_by != user.id:
        return None
    else:
        # dept/self 降级为按设备归属区域过滤
        if hasattr(user, 'org_id') and user.org_id:
            if alarm.org_id != user.org_id:
                # 检查是否属于子部门
                pass  # TODO: 递归检查组织树
        return event


@router.get("", response_model=dict)
async def list_emergency_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission("emergency:view"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="processing/resolved/closed"),
    start: Optional[str] = Query(None, description="开始时间 ISO8601"),
    end: Optional[str] = Query(None, description="结束时间 ISO8601"),
):
    """获取应急事件列表（分页 + 筛选）"""
    from app.models.emergency import EmergencyEvent
    
    base_stmt = select(EmergencyEvent)
    
    if status:
        base_stmt = base_stmt.where(EmergencyEvent.status == status)
    
    total = (await db.execute(base_stmt.count())).scalar()
    
    stmt = base_stmt.order_by(EmergencyEvent.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)
    
    result = await db.execute(stmt)
    events = result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    
    return {
        "code": 200,
        "data": {
            "items": events,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    }


@router.get("/{event_id}", response_model=dict)
async def get_emergency_event_detail(
    event_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission("emergency:view"))],
):
    """获取应急事件详情（含关联数据和权限检查）"""
    from app.models.emergency import EmergencyEvent, EmergencyTimeline
    
    stmt = select(EmergencyEvent).where(EmergencyEvent.id == event_id)
    event = (await db.execute(stmt)).scalar_one_or_none()
    
    if not event:
        return {"code": 404, "message": "事件不存在"}
    
    # 权限检查
    if not await check_data_scope(event_id, user, db):
        return {"code": 403, "message": "无权查看此事件"}
    
    # 获取关联报警
    from app.models.alarm import Alarm
    alarm_stmt = select(Alarm).where(Alarm.id == event.alarm_id)
    alarm = (await db.execute(alarm_stmt)).scalar_one_or_none()
    
    # 获取时间轴
    timeline_stmt = select(EmergencyTimeline).where(EmergencyTimeline.event_id == event_id)\
        .order_by(EmergencyTimeline.operated_at.asc())
    timelines = (await db.execute(timeline_stmt)).scalars().all()
    
    # 获取创建人和关闭人
    creator_stmt = select(User).where(User.id == event.created_by)
    creator = (await db.execute(creator_stmt)).scalar_one_or_none()
    
    closer = None
    if event.closed_by:
        closer_stmt = select(User).where(User.id == event.closed_by)
        closer = (await db.execute(closer_stmt)).scalar_one_or_none()
    
    return {
        "code": 200,
        "data": {
            "event": event,
            "alarm": alarm,
            "timelines": timelines,
            "creator": creator,
            "closer": closer
        }
    }


@router.post("/{event_id}/resolve", response_model=dict)
async def resolve_emergency_event_api(
    event_id: int,
    payload: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission("emergency:resolve"))],
):
    """标记应急事件处置完成（P0）"""
    summary = payload.get("summary")
    
    try:
        event = await resolve_emergency_event(db, event_id, summary, user.id)
        
        # TODO: WebSocket 广播事件更新
        
        return {"code": 200, "message": "处置完成", "data": event}
    except ValueError as e:
        return {"code": 404, "message": str(e)}


@router.post("/{event_id}/close", response_model=dict)
async def close_emergency_event_api(
    event_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission("emergency:close"))],
):
    """强制关闭应急事件（主管权限，P0）"""
    try:
        event = await close_emergency_event(db, event_id, user.id)
        
        # TODO: WebSocket 广播事件更新
        
        return {"code": 200, "message": "事件已关闭", "data": event}
    except ValueError as e:
        return {"code": 404, "message": str(e)}


@router.get("/{event_id}/report", response_model=dict)
async def get_event_report(
    event_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission("emergency:export"))],
):
    """导出事件报告（HTML/PDF，P0）"""
    http_status, content = await generate_event_report(db, event_id)
    
    if http_status == 200:
        # 返回 HTML（前端可打印为 PDF）
        return {
            "code": 200,
            "message": "报告生成成功",
            "content_type": "text/html; charset=utf-8",
            "data": content
        }
    elif http_status == 202:
        # 超大报告，提示异步导出
        return {
            "code": 202,
            "message": content,
            "status": "pending"
        }
    else:
        return {"code": http_status, "message": content}


@router.get("/{event_id}/timeline", response_model=dict)
async def list_timelines(
    event_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission("emergency:view"))],
):
    """获取时间轴列表（P0）"""
    from app.models.emergency import EmergencyTimeline
    
    stmt = select(EmergencyTimeline).where(EmergencyTimeline.event_id == event_id)\
        .order_by(EmergencyTimeline.operated_at.asc())
    
    result = await db.execute(stmt)
    timelines = result.scalars().all()
    
    return {
        "code": 200,
        "data": {
            "items": timelines,
            "total": len(timelines)
        }
    }


@router.post("/{event_id}/timeline", response_model=dict)
async def create_timeline(
    event_id: int,
    payload: EmergencyTimelineCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission("emergency:timeline"))],
):
    """添加入置时间轴节点（包含签到，P0）"""
    node_type = payload.node_type
    node_title = payload.node_title
    description = payload.description
    attachments = payload.attachments
    
    try:
        timeline = await add_timeline_node(
            db, event_id, node_type, user.id,
            node_title=node_title,
            description=description,
            attachments=attachments
        )
        
        # TODO: WebSocket 广播新节点
        
        return {"code": 200, "message": "添加成功", "data": timeline}
    except Exception as e:
        return {"code": 400, "message": f"添加失败：{e}"}
