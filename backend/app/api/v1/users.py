"""
用户 API 路由
GET /users/me          当前用户基本信息
GET /users/me/menus    动态菜单树
GET /users/me/permissions  权限码列表
/users                 用户管理 CRUD（需 system:user 权限）
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_permission
from app.crud.user import user_crud
from app.db.session import get_db
from app.models.user import User
from app.schemas.permission import MenuTreeOut, PermissionCodeListOut
from app.schemas.user import (
    ResetPasswordOut,
    UserCreate,
    UserListOut,
    UserOut,
    UserRolesUpdate,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.permission_service import build_menu_tree, get_user_permissions
from app.services.user_service import (
    create_user,
    delete_user,
    get_all_roles,
    get_user_with_roles,
    get_users_with_pagination,
    reset_user_password,
    update_user,
    update_user_status,
)
from app.services.user_service import bind_user_roles as assign_roles_to_user

router = APIRouter()


# ========== 当前用户相关（无需显式权限码，登录即可）==========


@router.get("/me", response_model=dict)
async def get_me(
    user: User = Depends(get_current_active_user),
):
    """返回当前用户基本信息 + 所属组织 + 角色列表"""
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "phone": user.phone,
            "email": user.email,
            "org": {
                "id": user.org.id if user.org else None,
                "org_name": user.org.org_name if user.org else None,
            },
            "roles": [
                {"id": r.id, "role_code": r.role_code, "role_name": r.role_name}
                for r in user.roles
            ],
            "data_scope": user.data_scope,
        },
    }


@router.get("/me/menus", response_model=dict)
async def get_my_menus(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前用户的动态菜单树（Vue Router 兼容格式）"""
    menus = await build_menu_tree(user, db)
    return {
        "code": 200,
        "message": "success",
        "data": menus,
    }


@router.get("/me/permissions", response_model=dict)
async def get_my_permissions(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前用户所有权限码列表（供前端 v-permission 指令使用）"""
    perms = await get_user_permissions(user, db)
    return {
        "code": 200,
        "message": "success",
        "data": perms,
    }


# ========== 用户管理（需 system:user 权限）==========


def _user_to_out(user: User) -> UserOut:
    """将 User ORM 对象转换为 UserOut schema"""
    return UserOut(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        phone=user.phone,
        email=user.email,
        org_id=user.org_id,
        org_name=user.org.org_name if user.org else None,
        data_scope=user.data_scope,
        status=user.status,
        roles=[
            {
                "id": r.id,
                "role_code": r.role_code,
                "role_name": r.role_name,
            }
            for r in user.roles
        ],
        created_at=user.created_at,
    )


@router.get("", response_model=dict)
async def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str | None = Query(None),
    permission: str | None = Query(
        None, description="只返回持有该权限码的用户（如 repair:repair）"
    ),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:user")),
):
    """分页查询用户列表"""
    users, total = await get_users_with_pagination(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        permission=permission,
    )

    items = [_user_to_out(user) for user in users]

    return {
        "code": 200,
        "message": "success",
        "data": UserListOut(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
    }


@router.post("", response_model=dict)
async def post_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:user")),
):
    """创建用户"""
    # 校验用户名唯一性
    existing = await user_crud.get_by_username(db, payload.username)
    if existing:
        return {"code": 400, "message": "用户名已存在", "data": None}

    user = await create_user(db, payload.model_dump())
    return {
        "code": 200,
        "message": "创建成功",
        "data": _user_to_out(user),
    }


@router.get("/roles/all", response_model=dict)
async def get_roles_all(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:user")),
):
    """获取所有角色（用于用户分配角色弹窗）"""
    roles = await get_all_roles(db)
    return {
        "code": 200,
        "message": "success",
        "data": [
            {"id": r.id, "role_code": r.role_code, "role_name": r.role_name}
            for r in roles
        ],
    }


@router.put("/{user_id}", response_model=dict)
async def put_user(
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:user")),
):
    """更新用户基础信息"""
    user = await update_user(db, user_id, payload.model_dump(exclude_unset=True))
    if not user:
        return {"code": 404, "message": "用户不存在", "data": None}

    return {
        "code": 200,
        "message": "更新成功",
        "data": _user_to_out(user),
    }


@router.put("/{user_id}/status", response_model=dict)
async def put_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("system:user")),
):
    """变更用户状态（active / locked / disabled）"""
    if user_id == current_user.id:
        return {"code": 400, "message": "不能操作当前登录用户", "data": None}

    user = await update_user_status(db, user_id, payload.status)
    if not user:
        return {"code": 404, "message": "用户不存在", "data": None}

    return {
        "code": 200,
        "message": "状态更新成功",
        "data": _user_to_out(user),
    }


@router.put("/{user_id}/roles", response_model=dict)
async def put_user_roles(
    user_id: int,
    payload: UserRolesUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:user")),
):
    """分配用户角色"""
    user = await assign_roles_to_user(db, user_id, payload.role_ids)
    if not user:
        return {"code": 404, "message": "用户不存在", "data": None}

    return {
        "code": 200,
        "message": "角色分配成功",
        "data": _user_to_out(user),
    }


@router.put("/{user_id}/reset-password", response_model=dict)
async def put_user_reset_password(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:user")),
):
    """重置用户密码"""
    new_password = await reset_user_password(db, user_id)
    if new_password is None:
        return {"code": 404, "message": "用户不存在", "data": None}

    return {
        "code": 200,
        "message": "密码重置成功",
        "data": ResetPasswordOut(new_password=new_password),
    }


@router.delete("/{user_id}", response_model=dict)
async def del_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("system:user")),
):
    """删除用户"""
    if user_id == current_user.id:
        return {"code": 400, "message": "不能删除当前登录用户", "data": None}

    user = await delete_user(db, user_id)
    if not user:
        return {"code": 404, "message": "用户不存在", "data": None}

    return {"code": 200, "message": "删除成功", "data": None}
