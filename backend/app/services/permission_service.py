"""
权限服务层
菜单树构建 / 用户权限码查询 / 完整权限树
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.permission import Permission
from app.models.user import Role, User


async def build_menu_tree(user: User, db: AsyncSession) -> list[dict]:
    """
    查询用户所有角色的权限，筛选 perm_type='menu'，
    按 parent_id + sort_order 构建树形结构。
    返回 Vue Router 兼容格式。
    """
    user_role_ids = [r.id for r in user.roles]
    if not user_role_ids:
        return []

    # 查询用户所有菜单权限（去重）
    result = await db.execute(
        select(Permission)
        .join(Role, Permission.roles)
        .where(Role.id.in_(user_role_ids))
        .where(Permission.perm_type == "menu")
        .order_by(Permission.parent_id.nullsfirst(), Permission.sort_order)
    )
    perms = result.scalars().all()

    # 去重
    seen = set()
    unique_perms = []
    for p in perms:
        if p.id not in seen:
            seen.add(p.id)
            unique_perms.append(p)

    # 构建 ID -> node 映射
    perm_map: dict[int, dict] = {}
    for p in unique_perms:
        perm_map[p.id] = {
            "id": p.id,
            "path": p.route_path or "",
            "name": p.perm_code,
            "component": p.component,
            "meta": {
                "title": p.perm_name or p.perm_code,
                "icon": p.icon,
            },
            "children": [],
            "sort_order": p.sort_order,
            "parent_id": p.parent_id,
        }

    # 构建树
    roots = []
    for node in perm_map.values():
        parent_id = node["parent_id"]
        if parent_id is None or parent_id not in perm_map:
            roots.append(node)
        else:
            parent = perm_map.get(parent_id)
            if parent:
                parent["children"].append(node)

    # 按 sort_order 排序
    roots.sort(key=lambda x: x["sort_order"])
    for node in perm_map.values():
        node["children"].sort(key=lambda x: x["sort_order"])

    # 清理辅助字段
    def _clean(node: dict) -> dict:
        return {
            "path": node["path"],
            "name": node["name"],
            "component": node["component"],
            "meta": node["meta"],
            "children": [_clean(c) for c in node["children"]],
        }

    return [_clean(r) for r in roots]


async def get_user_permissions(user: User, db: AsyncSession) -> list[str]:
    """
    返回用户所有权限码列表（去重）。
    包含 menu、button、api 所有类型。
    """
    user_role_ids = [r.id for r in user.roles]
    if not user_role_ids:
        return []

    result = await db.execute(
        select(Permission.perm_code)
        .join(Role, Permission.roles)
        .where(Role.id.in_(user_role_ids))
    )
    perms = {row[0] for row in result.all() if row[0]}
    return sorted(list(perms))


async def get_permission_tree(db: AsyncSession) -> list[dict]:
    """
    返回完整权限树（用于角色管理页面）。
    包含所有权限节点，按 parent_id + sort_order 构建树。
    """
    result = await db.execute(
        select(Permission)
        .order_by(Permission.parent_id.nullsfirst(), Permission.sort_order)
    )
    perms = result.scalars().all()

    perm_map: dict[int, dict] = {}
    for p in perms:
        perm_map[p.id] = {
            "id": p.id,
            "perm_code": p.perm_code,
            "perm_name": p.perm_name,
            "perm_type": p.perm_type,
            "route_path": p.route_path,
            "component": p.component,
            "icon": p.icon,
            "sort_order": p.sort_order,
            "parent_id": p.parent_id,
            "children": [],
        }

    roots = []
    for node in perm_map.values():
        parent_id = node["parent_id"]
        if parent_id is None or parent_id not in perm_map:
            roots.append(node)
        else:
            parent = perm_map.get(parent_id)
            if parent:
                parent["children"].append(node)

    roots.sort(key=lambda x: x["sort_order"])
    for node in perm_map.values():
        node["children"].sort(key=lambda x: x["sort_order"])

    return roots
