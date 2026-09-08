"""
用户 CRUD
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.user import User


class UserCRUD(CRUDBase[User, None, None]):
    """用户 CRUD"""

    async def get_by_username(self, db: AsyncSession, username: str) -> User | None:
        """按用户名查询用户（含角色、组织关系）"""
        result = await db.execute(
            select(User)
            .options(selectinload(User.roles), selectinload(User.org))
            .where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        """按邮箱查询用户"""
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def increment_login_fail(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> User | None:
        """增加失败计数"""
        user = await self.get(db, user_id)
        if user:
            user.login_fail_count += 1
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user

    async def reset_login_fail(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> User | None:
        """清零失败计数"""
        user = await self.get(db, user_id)
        if user:
            user.login_fail_count = 0
            user.locked_until = None
            user.status = "active"
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user

    async def lock_account(
        self,
        db: AsyncSession,
        user_id: int,
        locked_until: datetime,
    ) -> User | None:
        """锁定账户"""
        user = await self.get(db, user_id)
        if user:
            user.status = "locked"
            user.locked_until = locked_until
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user

    async def unlock_account(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> User | None:
        """解锁账户"""
        user = await self.get(db, user_id)
        if user:
            user.status = "active"
            user.locked_until = None
            user.login_fail_count = 0
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user


user_crud = UserCRUD(User)
