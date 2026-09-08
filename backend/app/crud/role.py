"""
角色 CRUD
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.user import Role, User


class RoleCRUD(CRUDBase[Role, None, None]):
    """角色 CRUD"""

    async def get_by_code(self, db: AsyncSession, role_code: str) -> Role | None:
        """按角色编码查询角色"""
        result = await db.execute(
            select(Role).where(Role.role_code == role_code)
        )
        return result.scalar_one_or_none()

    async def get_roles_by_user(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> list[Role]:
        """查询用户所有角色"""
        result = await db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            return list(user.roles)
        return []


role_crud = RoleCRUD(Role)
