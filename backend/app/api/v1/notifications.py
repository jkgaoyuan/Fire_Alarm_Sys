"""
通知中心 API（3.5 B7）
- GET /notifications - 当前用户通知列表
- POST /notifications/{id}/read - 标记已读
- POST /notifications/read-all - 全部已读
- GET /notifications/unread-count - 未读数统计
"""

from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.emergency import NotificationListOut, UnreadCountOut
from app.services.emergency_service import (
    get_user_notifications,
    mark_notifications_as_read,
    get_unread_count
)

router = APIRouter()


@router.get("", response_model=dict)
async def list_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    module: str = Query(None, description="emergency/linkage/system"),
):
    """获取当前用户的通知列表（P1）"""
    result = await get_user_notifications(db, user.id, page, page_size, module)
    
    return {
        "code": 200,
        "data": {
            "items": result["items"],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
            "total_pages": result["total_pages"]
        }
    }


@router.post("/{notification_id}/read", response_model=dict)
async def read_notification(
    notification_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """标记单个通知为已读（P1）"""
    from app.models.emergency import Notification
    
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.user_id == user.id
    )
    notification = (await db.execute(stmt)).scalar_one_or_none()
    
    if not notification:
        return {"code": 404, "message": "通知不存在或无权访问"}
    
    notification.is_read = True
    await db.flush()
    
    return {"code": 200, "message": "已标记为已读"}


@router.post("/read-all", response_model=dict)
async def read_all_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """标记所有通知为已读（P1）"""
    from app.models.emergency import Notification
    from sqlalchemy import update
    
    stmt = update(Notification).where(
        Notification.user_id == user.id,
        Notification.is_read == False
    ).values(is_read=True)
    
    await db.execute(stmt)
    await db.commit()
    
    return {"code": 200, "message": "已全部标记为已读"}


@router.get("/unread-count", response_model=dict)
async def get_unread_count_api(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)]
):
    """获取当前用户的未读通知数量（P1）"""
    count = await get_unread_count(db, user.id)
    
    return {
        "code": 200,
        "data": {
            "unread_count": count
        }
    }
