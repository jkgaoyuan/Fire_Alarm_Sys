"""
用户与角色模型
"""


from datetime import datetime

from typing import Optional, List

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, role_permissions, user_roles


class User(Base):
    """用户表"""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    real_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    org_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=True,
    )
    data_scope: Mapped[str] = mapped_column(String(20), default="self", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    login_fail_count: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # 关联关系
    org: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="users",
    )
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
    )
    login_logs: Mapped[List["LoginLog"]] = relationship(
        "LoginLog",
        back_populates="user",
    )


class Role(Base):
    """角色表"""

    __tablename__ = "roles"

    role_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(default=False, nullable=False)

    # 关联关系
    users: Mapped[List["User"]] = relationship(
        "User",
        secondary=user_roles,
        back_populates="roles",
    )
    permissions: Mapped[List["Permission"]] = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
    )


class LoginLog(Base):
    """登录审计日志表"""

    __tablename__ = "login_logs"

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    username: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    login_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    device_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    device_os: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    browser: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    fail_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 关联关系
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="login_logs",
    )
