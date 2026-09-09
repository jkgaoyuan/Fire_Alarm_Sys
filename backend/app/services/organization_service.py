"""
组织架构服务层
树形构建 —— 与 permission_service.build_menu_tree 同构，
手动按 parent_id 组装而非依赖自关联 relationship（Organization.children 的 remote_side 声明有误，
且自关联在 async 下会触发懒加载）。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


async def get_organizations_flat(db: AsyncSession) -> list[Organization]:
    """按 sort_order 返回全部组织节点"""
    result = await db.execute(
        select(Organization).order_by(Organization.sort_order, Organization.id)
    )
    return list(result.scalars().all())


def build_org_tree(orgs: list[Organization]) -> list[dict]:
    """
    将扁平组织列表组装为树。
    parent_id 为空或指向不存在节点的，视为根节点（避免脏数据导致整棵子树丢失）。
    """
    node_map: dict[int, dict] = {
        o.id: {
            "id": o.id,
            "parent_id": o.parent_id,
            "org_name": o.org_name,
            "org_type": o.org_type,
            "sort_order": o.sort_order,
            "children": [],
        }
        for o in orgs
    }

    roots: list[dict] = []
    for node in node_map.values():
        parent = node_map.get(node["parent_id"]) if node["parent_id"] else None
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)

    def _sort(nodes: list[dict]) -> None:
        nodes.sort(key=lambda n: (n["sort_order"], n["id"]))
        for n in nodes:
            _sort(n["children"])

    _sort(roots)
    return roots


async def get_organization_tree(db: AsyncSession) -> list[dict]:
    """返回完整组织架构树"""
    orgs = await get_organizations_flat(db)
    return build_org_tree(orgs)
