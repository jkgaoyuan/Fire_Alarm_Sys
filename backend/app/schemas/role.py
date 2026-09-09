"""
角色相关 Pydantic Schema
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RoleBase(BaseModel):
    """角色基础字段"""

    role_name: str = Field(..., min_length=1, max_length=50)
    description: str | None = Field(None, max_length=255)


class RoleCreate(RoleBase):
    """创建角色请求"""

    perm_ids: list[int] = []


class RoleUpdate(BaseModel):
    """更新角色请求（所有字段可选）"""

    role_name: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = Field(None, max_length=255)
    perm_ids: list[int] | None = None


class RoleOut(BaseModel):
    """角色输出"""

    id: int
    role_code: str
    role_name: str
    description: str | None = None
    is_builtin: bool
    created_at: datetime
    perm_ids: list[int] | None = None

    model_config = ConfigDict(from_attributes=True)


class RoleListOut(BaseModel):
    """角色分页列表输出"""

    items: list[RoleOut]
    total: int
    page: int
    page_size: int
