"""
登录日志 CRUD
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.user import LoginLog


class LoginLogCRUD(CRUDBase[LoginLog, None, None]):
    """登录日志 CRUD"""

    async def get_logs_by_user(
        self,
        db: AsyncSession,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[LoginLog]:
        """查询用户的登录日志"""
        result = await db.execute(
            select(LoginLog)
            .where(LoginLog.user_id == user_id)
            .offset(skip)
            .limit(limit)
            .order_by(LoginLog.created_at.desc())
        )
        return list(result.scalars().all())


login_log_crud = LoginLogCRUD(LoginLog)
