"""
登录日志服务层
提供分页查询与过滤能力
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import LoginLog


async def get_login_logs_with_pagination(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 10,
    username: str | None = None,
    status: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[list[LoginLog], int]:
    """
    分页查询登录日志

    Args:
        db: 数据库会话
        page: 页码（从 1 开始）
        page_size: 每页条数
        username: 用户名模糊过滤
        status: 登录状态（success / fail / locked）
        start_time: 创建时间起始（含）
        end_time: 创建时间截止（含）

    Returns:
        (日志列表, 总数)
    """
    stmt = select(LoginLog)

    if username:
        stmt = stmt.where(LoginLog.username.ilike(f"%{username}%"))
    if status:
        stmt = stmt.where(LoginLog.status == status)
    if start_time:
        stmt = stmt.where(LoginLog.created_at >= start_time)
    if end_time:
        stmt = stmt.where(LoginLog.created_at <= end_time)

    # 总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # 分页
    stmt = (
        stmt.order_by(LoginLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    logs = list(result.scalars().all())

    return logs, total
