"""
登录日志 API 路由（P1-003）
GET /login-logs 查询登录日志（分页 + 筛选）
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_db
from app.schemas.login_log import LoginLogListOut, LoginLogOut
from app.services.login_log_service import get_login_logs_with_pagination

router = APIRouter()


@router.get("", response_model=dict)
async def get_login_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    username: str | None = Query(None),
    status: str | None = Query(None),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:log:view")),
):
    """分页查询登录日志（支持用户名、状态、时间范围筛选）"""
    logs, total = await get_login_logs_with_pagination(
        db,
        page=page,
        page_size=page_size,
        username=username,
        status=status,
        start_time=start_time,
        end_time=end_time,
    )

    return {
        "code": 200,
        "message": "success",
        "data": LoginLogListOut(
            items=[LoginLogOut.model_validate(log).model_dump() for log in logs],
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
    }
