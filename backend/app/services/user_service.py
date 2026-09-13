"""
用户服务层
用户信息查询 / 数据范围过滤 / 用户管理
"""

import secrets
import string

from sqlalchemy import false, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.core.security import get_password_hash
from app.crud.role import role_crud
from app.crud.user import user_crud
from app.models.organization import Organization
from app.models.permission import Permission
from app.models.user import Role, User


async def get_user_with_roles(db: AsyncSession, user_id: int) -> User | None:
    """返回用户 + 角色列表（预加载）"""
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles), selectinload(User.org))
        .where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def apply_data_scope(query: Select, user: User, db: AsyncSession) -> Select:
    """
    根据用户 data_scope 追加过滤条件。
    需要接收 SQLAlchemy Select 对象并返回修改后的 Select。

    - data_scope='all'   -> 不追加过滤
    - data_scope='dept'  -> 追加 org_id IN (用户部门及所有子部门)
    - data_scope='self'  -> 追加 created_by = user.id
    """
    if user.data_scope == "all":
        return query

    # 获取查询对应的模型类（假设是 select(Model) 形式）
    model = query.column_descriptions[0]["entity"]

    if user.data_scope == "self":
        if not hasattr(model, "created_by"):
            return query
        return query.where(model.created_by == user.id)

    if user.data_scope == "dept":
        if user.org_id is None:
            # 无部门则不可见任何数据
            if hasattr(model, "org_id"):
                return query.where(false())
            return query

        # 递归 CTE 查询子部门
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

        if hasattr(model, "org_id"):
            if org_ids:
                return query.where(model.org_id.in_(org_ids))
            return query.where(false())
        return query

    return query


def _generate_random_password(length: int = 12) -> str:
    """生成随机密码（字母 + 数字）"""
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
        ):
            return password


async def get_users_with_pagination(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 10,
    keyword: str | None = None,
    permission: str | None = None,
) -> tuple[list[User], int]:
    """
    分页查询用户列表，支持按用户名/真实姓名/手机号模糊搜索。
    返回 (用户列表, 总数)

    `permission` 按「是否持有某权限码」过滤（经角色折算，与 `/users/me/permissions`
    同一口径）。用于「只在候选人里列出真正能干这件事的人」——如派单弹窗只列
    持有 `repair:repair` 的用户，避免把工单派给无法开始/完成维修的人。
    条件同时作用于 items 与 count，否则会出现「共 N 条却只给 M 行」的分页错位。
    """
    stmt = (
        select(User)
        .options(selectinload(User.roles), selectinload(User.org))
        .order_by(User.id.desc())
    )
    count_stmt = select(func.count()).select_from(User)

    filters = []
    if keyword:
        filters.append(
            User.username.ilike(f"%{keyword}%")
            | User.real_name.ilike(f"%{keyword}%")
            | User.phone.ilike(f"%{keyword}%")
        )

    if permission:
        filters.append(
            User.roles.any(Role.permissions.any(Permission.perm_code == permission))
        )

    if filters:
        for f in filters:
            stmt = stmt.where(f)
            count_stmt = count_stmt.where(f)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    skip = (page - 1) * page_size
    stmt = stmt.offset(skip).limit(page_size)
    result = await db.execute(stmt)
    users = list(result.scalars().all())

    return users, total


async def create_user(db: AsyncSession, obj_in: dict) -> User:
    """
    创建用户并绑定角色。
    """
    role_ids = obj_in.pop("role_ids", [])

    db_obj = User(
        username=obj_in["username"],
        password_hash=get_password_hash(obj_in["password"]),
        real_name=obj_in.get("real_name"),
        phone=obj_in.get("phone"),
        email=obj_in.get("email"),
        org_id=obj_in.get("org_id"),
        data_scope=obj_in.get("data_scope", "self"),
        status="active",
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)

    if role_ids:
        await bind_user_roles(db, db_obj.id, role_ids)

    # 重新查询以加载角色关系
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles), selectinload(User.org))
        .where(User.id == db_obj.id)
    )
    return result.scalar_one()


async def update_user(db: AsyncSession, user_id: int, obj_in: dict) -> User | None:
    """
    更新用户基础信息，并重新绑定角色（如传入 role_ids）。
    """
    user = await user_crud.get(db, user_id)
    if not user:
        return None

    update_data = {k: v for k, v in obj_in.items() if v is not None}
    role_ids = update_data.pop("role_ids", None)

    # 邮箱字段可能为 None，需要显式处理
    for field, value in update_data.items():
        if hasattr(user, field):
            setattr(user, field, value)

    db.add(user)
    await db.commit()
    await db.refresh(user)

    if role_ids is not None:
        await bind_user_roles(db, user_id, role_ids)

    # 重新查询以加载最新角色关系（避免后续序列化触发懒加载）
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles), selectinload(User.org))
        .where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def update_user_status(
    db: AsyncSession, user_id: int, status: str
) -> User | None:
    """
    更新用户状态。
    - active: 正常（解锁时同时清空锁定时间和失败计数）
    - locked: 锁定（保留 locked_until，前端通过 unlock 触发 active）
    - disabled: 禁用
    """
    user = await user_crud.get(db, user_id)
    if not user:
        return None

    user.status = status
    if status == "active":
        user.locked_until = None
        user.login_fail_count = 0

    db.add(user)
    await db.commit()

    # 重新查询以加载关联关系，避免序列化时触发懒加载
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles), selectinload(User.org))
        .where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def delete_user(db: AsyncSession, user_id: int) -> User | None:
    """
    删除用户。注意：本系统不校验是否关联业务数据，实际业务中可扩展。
    """
    user = await user_crud.get(db, user_id)
    if not user:
        return None

    await db.delete(user)
    await db.commit()
    return user


async def bind_user_roles(db: AsyncSession, user_id: int, role_ids: list[int]) -> User | None:
    """
    重新绑定用户角色（先删后插）。
    返回重新加载关联关系的 User 对象。
    """
    from app.models.base import user_roles

    user = await user_crud.get(db, user_id)
    if not user:
        return None

    # 删除现有绑定
    await db.execute(user_roles.delete().where(user_roles.c.user_id == user_id))

    # 过滤有效角色 ID
    if role_ids:
        result = await db.execute(
            select(role_crud.model.id).where(role_crud.model.id.in_(role_ids))
        )
        valid_role_ids = {row[0] for row in result.all()}

        for role_id in role_ids:
            if role_id in valid_role_ids:
                await db.execute(
                    user_roles.insert().values(user_id=user_id, role_id=role_id)
                )

    await db.commit()

    # 重新查询加载最新角色关系
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles), selectinload(User.org))
        .where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def reset_user_password(db: AsyncSession, user_id: int) -> str | None:
    """
    重置用户密码为随机字符串，返回新密码明文。
    """
    user = await user_crud.get(db, user_id)
    if not user:
        return None

    new_password = _generate_random_password()
    user.password_hash = get_password_hash(new_password)
    user.status = "active"
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return new_password


async def get_all_roles(db: AsyncSession) -> list:
    """
    获取全部角色（用于用户分配角色弹窗）。
    """
    result = await db.execute(
        select(role_crud.model).order_by(role_crud.model.id.asc())
    )
    return list(result.scalars().all())
