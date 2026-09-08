"""
SQLAlchemy 声明式基类
所有模型继承此类，自动获得 id、created_at、updated_at
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """声明式基类"""

    # 通用主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 通用时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"

    def to_dict(self) -> dict[str, Any]:
        """转为字典（用于序列化）"""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }


# 用户角色关联表（不继承 Base，避免复合主键与自增 id 冲突）
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
)

# 角色权限关联表
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
    Column("perm_id", Integer, ForeignKey("permissions.id", ondelete="RESTRICT"), primary_key=True),
)
