"""
权限相关 Pydantic Schema
"""

from pydantic import BaseModel


class PermissionOut(BaseModel):
    """权限输出"""

    id: int
    perm_code: str
    perm_name: str | None = None
    perm_type: str | None = None
    parent_id: int | None = None
    route_path: str | None = None
    component: str | None = None
    icon: str | None = None
    sort_order: int = 0
    children: list = []

    class Config:
        from_attributes = True


class MenuTreeOut(BaseModel):
    """菜单树输出"""

    code: int = 200
    message: str = "success"
    data: list = []


class PermissionCodeListOut(BaseModel):
    """权限码列表输出"""

    code: int = 200
    message: str = "success"
    data: list[str] = []
