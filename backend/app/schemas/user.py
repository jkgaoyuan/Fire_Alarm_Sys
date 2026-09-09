"""
用户相关 Pydantic Schema
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRoleOut(BaseModel):
    """用户所属角色输出"""

    id: int
    role_code: str
    role_name: str

    model_config = ConfigDict(from_attributes=True)


class UserOut(BaseModel):
    """用户管理列表/详情输出"""

    id: int
    username: str
    real_name: str | None = None
    phone: str | None = None
    email: str | None = None
    org_id: int | None = None
    org_name: str | None = None
    data_scope: str
    status: str
    roles: list[UserRoleOut] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserListOut(BaseModel):
    """用户分页列表输出"""

    items: list[UserOut]
    total: int
    page: int
    page_size: int


class UserMeOut(BaseModel):
    """当前用户详细信息输出"""

    id: int
    username: str
    real_name: str | None = None
    phone: str | None = None
    email: str | None = None
    org: dict | None = None
    roles: list[dict] = []
    data_scope: str = "self"

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    """创建用户请求"""

    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    real_name: str | None = Field(None, max_length=50)
    phone: str | None = Field(None, max_length=20)
    email: EmailStr | None = None
    org_id: int | None = None
    data_scope: str = "self"
    role_ids: list[int] = []


class UserUpdate(BaseModel):
    """更新用户请求"""

    real_name: str | None = Field(None, max_length=50)
    phone: str | None = Field(None, max_length=20)
    email: EmailStr | None = None
    org_id: int | None = None
    data_scope: str | None = None
    role_ids: list[int] | None = None
    status: str | None = None


class UserStatusUpdate(BaseModel):
    """用户状态变更请求"""

    status: str = Field(..., pattern=r"^(active|locked|disabled)$")


class UserRolesUpdate(BaseModel):
    """用户角色分配请求"""

    role_ids: list[int] = []


class ResetPasswordOut(BaseModel):
    """重置密码响应"""

    new_password: str
