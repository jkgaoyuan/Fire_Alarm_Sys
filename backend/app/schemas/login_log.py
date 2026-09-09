"""
登录日志 Pydantic Schema
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LoginLogOut(BaseModel):
    """登录日志列表项输出"""

    id: int
    username: str | None = None
    login_type: str | None = None
    ip_address: str | None = None
    device_type: str | None = None
    device_os: str | None = None
    browser: str | None = None
    status: str | None = None
    fail_reason: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginLogListOut(BaseModel):
    """登录日志分页列表输出"""

    items: list[LoginLogOut]
    total: int
    page: int
    page_size: int
