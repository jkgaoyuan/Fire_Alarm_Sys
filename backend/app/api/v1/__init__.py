"""
API v1 路由聚合
"""

from fastapi import APIRouter

from app.api.v1 import auth, permissions, roles, users

router = APIRouter()

# 注册认证路由
router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 注册用户路由
router.include_router(users.router, prefix="/users", tags=["用户"])

# 注册权限路由
router.include_router(permissions.router, prefix="/permissions", tags=["权限"])

# 注册角色路由
router.include_router(roles.router, prefix="/roles", tags=["角色"])
