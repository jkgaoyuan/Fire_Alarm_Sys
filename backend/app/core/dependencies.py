"""
统一鉴权依赖
get_current_user / require_permission / get_data_scope_filter
"""

from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import redis.asyncio as aioredis

from app.core.exceptions import AuthError, PermissionDenied
from app.core.security import decode_token
from app.db.redis import get_redis_pool
from app.db.session import get_db
from app.models.permission import Permission
from app.models.user import Role, User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    解码 Access Token，校验 Redis 黑名单，返回 User ORM 对象。
    若 Token 无效、已过期或在黑名单中，则抛出 401。
    """
    if not credentials or not hasattr(credentials, "credentials"):
        raise AuthError(401, "未提供 Access Token")

    access_token = credentials.credentials
    payload = decode_token(access_token)
    if not payload:
        raise AuthError(401, "Access Token 无效或已过期")

    # 校验黑名单
    jti = payload.get("jti")
    if jti:
        blacklist_key = f"token_blacklist:{jti}"
        if await redis.exists(blacklist_key):
            raise AuthError(401, "Access Token 已被注销")

    # 查询用户
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise AuthError(401, "Token 格式错误")

    result = await db.execute(
        select(User)
        .options(selectinload(User.roles), selectinload(User.org))
        .where(User.id == int(user_id_str))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise AuthError(401, "用户不存在")

    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    """
    get_current_user + 状态校验
    锁定或禁用状态均拒绝访问。
    """
    if user.status == "disabled":
        raise AuthError(4004, "账户已禁用")
    if user.status == "locked":
        from app.core.security import utc_to_cst_iso
        raise AuthError(
            4003,
            "账户已锁定",
            {"locked_until": utc_to_cst_iso(user.locked_until)},
        )
    return user


def require_permission(perm_code: str):
    """
    返回依赖函数，校验当前用户是否拥有指定权限码。
    无权限则抛出 PermissionDenied (403)。
    """
    async def _check_permission(
        user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # 查询用户所有角色的权限码
        user_roles_ids = [r.id for r in user.roles]
        if not user_roles_ids:
            raise PermissionDenied(f"缺少权限: {perm_code}")

        result = await db.execute(
            select(Permission.perm_code)
            .join(Role, Permission.roles)
            .where(Role.id.in_(user_roles_ids))
            .where(Permission.perm_code == perm_code)
        )
        if result.scalar_one_or_none() is None:
            raise PermissionDenied(f"缺少权限: {perm_code}")

        return user

    return _check_permission


async def get_data_scope_filter(
    user: User,
    db: AsyncSession,
) -> list[int]:
    """
    根据用户 data_scope 返回可访问的数据范围 ID 列表。
    - 'all'   -> 返回空列表（表示不过滤）
    - 'dept'  -> 递归查用户 org_id 及所有子部门 ID
    - 'self'  -> 返回 [user.id]（用于 created_by 过滤）
    """
    if user.data_scope == "all":
        return []

    if user.data_scope == "self":
        return [user.id]

    if user.data_scope == "dept":
        from app.models.organization import Organization

        if user.org_id is None:
            return []

        # 使用 CTE 递归查询子部门
        from sqlalchemy import union_all

        # 递归 CTE：从用户 org_id 开始，查询所有子部门
        cte = (
            select(Organization.id)
            .where(Organization.id == user.org_id)
            .cte(recursive=True)
        )
        cte = cte.union_all(
            select(Organization.id).where(Organization.parent_id == cte.c.id)
        )
        result = await db.execute(select(cte.c.id))
        org_ids = [row[0] for row in result.all()]
        return org_ids if org_ids else []

    # 默认 self
    return [user.id]
