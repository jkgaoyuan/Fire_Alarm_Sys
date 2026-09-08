"""
权限模型
"""


from typing import Optional, List

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, role_permissions


class Permission(Base):
    """权限表（菜单 / 按钮 / API）"""

    __tablename__ = "permissions"

    perm_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    perm_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    perm_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("permissions.id"),
        nullable=True,
    )
    route_path: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    component: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    # 自关联树形结构
    children: Mapped[List["Permission"]] = relationship(
        "Permission",
        back_populates="parent",
        remote_side="Permission.id",
    )
    parent: Mapped[Optional["Permission"]] = relationship(
        "Permission",
        back_populates="children",
        foreign_keys=[parent_id],
    )

    # 多对多关联角色
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
    )

