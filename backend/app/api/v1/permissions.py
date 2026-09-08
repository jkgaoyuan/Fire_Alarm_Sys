"""
权限 API 路由
GET /permissions/tree  返回完整权限树（仅主管可用）
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_db
from app.services.permission_service import get_permission_tree

router = APIRouter()


@router.get("/tree", response_model=dict)
async def get_permissions_tree(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("system:role")),
):
    """返回完整权限树（用于角色管理页面）"""
    tree = await get_permission_tree(db)
    return {
        "code": 200,
        "message": "success",
        "data": tree,
    }
