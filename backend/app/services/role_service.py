"""
角色服务层
角色 CRUD / 权限绑定 / 删除校验
"""

import re

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import redis.asyncio as aioredis

from app.core.exceptions import AuthError
from app.crud.role import role_crud
from app.models.base import role_permissions
from app.models.permission import Permission
from app.models.user import Role, User
from app.schemas.role import RoleCreate, RoleUpdate


async def _generate_unique_role_code(db: AsyncSession, role_name: str) -> str:
    """根据角色名称生成唯一的 role_code"""
    base = re.sub(r"[^a-zA-Z0-9]+", "_", role_name.strip()).lower().strip("_")
    if not base:
        base = "role"

    code = base
    counter = 1
    while await role_crud.get_by_code(db, code):
        code = f"{base}_{counter}"
        counter += 1
    return code


async def create_role(db: AsyncSession, obj_in: RoleCreate) -> Role:
    """
    创建角色（is_builtin=false），并绑定权限
    """
    role_code = await _generate_unique_role_code(db, obj_in.role_name)

    db_obj = Role(
        role_code=role_code,
        role_name=obj_in.role_name,
        description=obj_in.description,
        is_builtin=False,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)

    # 绑定权限
    if obj_in.perm_ids:
        await bind_permissions(db, db_obj.id, obj_in.perm_ids)

    # 重新查询以加载 permissions 关系（async 不支持懒加载）
    result = await db.execute(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == db_obj.id)
    )
    return result.scalar_one()


async def update_role(
    db: AsyncSession,
    role_id: int,
    obj_in: RoleUpdate,
) -> Role | None:
    """
    更新角色名称/描述/权限绑定
    """
    role = await role_crud.get(db, role_id)
    if not role:
        return None

    # 更新基础字段
    update_data = obj_in.model_dump(exclude_unset=True)
    perm_ids = update_data.pop("perm_ids", None)

    for field, value in update_data.items():
        if hasattr(role, field) and value is not None:
            setattr(role, field, value)

    db.add(role)
    await db.commit()
    await db.refresh(role)

    # 重新绑定权限
    if perm_ids is not None:
        await bind_permissions(db, role_id, perm_ids)

    # 重新查询以加载 permissions 关系
    result = await db.execute(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    )
    return result.scalar_one_or_none()


async def delete_role(
    db: AsyncSession,
    redis: aioredis.Redis,
    role_id: int,
) -> Role | None:
    """
    删除角色
    - 内置角色禁止删除
    - 删除前校验是否关联用户
    """
    role = await role_crud.get(db, role_id)
    if not role:
        return None

    if role.is_builtin:
        raise AuthError(400, "内置角色禁止删除")

    # 校验是否关联用户
    result = await db.execute(
        select(func.count()).select_from(User).where(User.roles.any(Role.id == role_id))
    )
    user_count = result.scalar() or 0
    if user_count > 0:
        raise AuthError(400, "角色已关联用户，无法删除")

    await db.delete(role)
    await db.commit()
    return role


async def get_role_permissions(db: AsyncSession, role_id: int) -> list[int]:
    """
    获取角色已绑定权限 ID 列表
    """
    role = await db.execute(
        select(Role)
        .options(selectinload(Role.permissions))
        .where(Role.id == role_id)
    )
    role_obj = role.scalar_one_or_none()
    if not role_obj:
        return []
    return [p.id for p in role_obj.permissions]


async def bind_permissions(db: AsyncSession, role_id: int, perm_ids: list[int]) -> None:
    """
    重新绑定权限（先删后插）
    """
    # 删除现有绑定
    await db.execute(
        role_permissions.delete().where(role_permissions.c.role_id == role_id)
    )

    # 插入新绑定
    if perm_ids:
        # 过滤掉不存在的权限 ID
        result = await db.execute(select(Permission.id).where(Permission.id.in_(perm_ids)))
        valid_perm_ids = {row[0] for row in result.all()}

        for perm_id in perm_ids:
            if perm_id in valid_perm_ids:
                await db.execute(
                    role_permissions.insert().values(role_id=role_id, perm_id=perm_id)
                )

    await db.commit()


async def get_roles_with_pagination(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 10,
    keyword: str | None = None,
    role_code: str | None = None,
    role_name: str | None = None,
) -> tuple[list[Role], int]:
    """
    分页查询角色列表，支持关键字 / role_code / role_name 过滤
    keyword 同时匹配角色编码与角色名称（前端列表页只有一个搜索框）
    返回 (角色列表, 总数)
    """
    # 构建基础查询（eager load permissions）
    stmt = select(Role).options(selectinload(Role.permissions)).order_by(Role.id.desc())
    count_stmt = select(func.count()).select_from(Role)

    # 过滤条件
    filters = []
    if keyword:
        filters.append(
            or_(
                Role.role_code.contains(keyword),
                Role.role_name.contains(keyword),
            )
        )
    if role_code:
        filters.append(Role.role_code == role_code)
    if role_name:
        filters.append(Role.role_name.contains(role_name))

    if filters:
        for f in filters:
            stmt = stmt.where(f)
            count_stmt = count_stmt.where(f)

    # 查询总数
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # 分页查询
    skip = (page - 1) * page_size
    stmt = stmt.offset(skip).limit(page_size)
    result = await db.execute(stmt)
    roles = list(result.scalars().all())

    return roles, total
