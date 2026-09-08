"""
认证相关 Pydantic Schema
"""


from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class LoginRequest(BaseModel):
    """登录请求"""

    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class TokenResponse(BaseModel):
    """Token 响应"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshRequest(BaseModel):
    """刷新请求（空体，Refresh Token 从 Cookie 读取）"""

    pass


class ResponseModel(BaseModel, Generic[T]):
    """统一响应包装"""

    code: int = 200
    message: str = "success"
    data: T | None = None
