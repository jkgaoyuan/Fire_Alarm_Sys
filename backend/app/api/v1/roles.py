"""
角色管理 API 路由
全部接口需要 system:role 权限（仅主管可用）
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.core.dependencies import require_permission
from app.db.redis import get_redis_pool
from app.db.session import get_db
from app.schemas.role import RoleCreate, RoleListOut, RoleOut, RoleUpdate
from app.services.role_service import (
    create_role,
    delete_role,
    get_role_permissions,
    get_roles_with_pagination,
    update_role,
)

router = APIRouter()


@router.get("", response_model=dict)
async def get_roles(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str | None = Query(None, description="按角色编码或名称模糊搜索"),
    role_code: str | None = Query(None),
    role_name: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:role")),
):
    """分页查询角色列表"""
    roles, total = await get_roles_with_pagination(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        role_code=role_code,
        role_name=role_name,
    )

    # 组装 perm_ids
    items = []
    for role in roles:
        perm_ids = [p.id for p in role.permissions]
        items.append(
            RoleOut(
                id=role.id,
                role_code=role.role_code,
                role_name=role.role_name,
                description=role.description,
                is_builtin=role.is_builtin,
                created_at=role.created_at,
                perm_ids=perm_ids,
            )
        )

    return {
        "code": 200,
        "message": "success",
        "data": RoleListOut(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
    }


@router.post("", response_model=dict)
async def post_role(
    payload: RoleCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:role")),
):
    """创建角色"""
    role = await create_role(db, payload)

    perm_ids = [p.id for p in role.permissions]
    return {
        "code": 200,
        "message": "创建成功",
        "data": RoleOut(
            id=role.id,
            role_code=role.role_code,
            role_name=role.role_name,
            description=role.description,
            is_builtin=role.is_builtin,
            created_at=role.created_at,
            perm_ids=perm_ids,
        ),
    }


@router.put("/{role_id}", response_model=dict)
async def put_role(
    role_id: int,
    payload: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:role")),
):
    """更新角色"""
    role = await update_role(db, role_id, payload)
    if not role:
        return {"code": 404, "message": "角色不存在", "data": None}

    perm_ids = [p.id for p in role.permissions]
    return {
        "code": 200,
        "message": "更新成功",
        "data": RoleOut(
            id=role.id,
            role_code=role.role_code,
            role_name=role.role_name,
            description=role.description,
            is_builtin=role.is_builtin,
            created_at=role.created_at,
            perm_ids=perm_ids,
        ),
    }


@router.delete("/{role_id}", response_model=dict)
async def del_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis_pool),
    _=Depends(require_permission("system:role")),
):
    """删除角色（内置角色禁止删除）"""
    role = await delete_role(db, redis, role_id)
    if not role:
        return {"code": 404, "message": "角色不存在", "data": None}

    return {"code": 200, "message": "删除成功", "data": None}


@router.get("/{role_id}/permissions", response_model=dict)
async def get_role_perms(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:role")),
):
    """获取角色已绑定权限 ID 列表"""
    perm_ids = await get_role_permissions(db, role_id)
    return {
        "code": 200,
        "message": "success",
        "data": perm_ids,
    }
