"""
组织架构模型
"""


from typing import Optional, List

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Organization(Base):
    """组织架构表"""

    __tablename__ = "organizations"

    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=True,
    )
    org_name: Mapped[str] = mapped_column(String(100), nullable=False)
    org_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # FR-015 平面图：URL 来自 PRD 4.2 DDL，宽高为原图像素基准尺寸，
    # devices.map_x/map_y 存的是原图像素坐标，前端按 width/height 归一化后再缩放
    map_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    map_image_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    map_image_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    map_origin: Mapped[Optional[str]] = mapped_column(
        String(20), default="top_left", nullable=True
    )
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    # 自关联关系
    children: Mapped[List["Organization"]] = relationship(
        "Organization",
        back_populates="parent",
        remote_side="Organization.id",
    )
    parent: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="children",
        foreign_keys=[parent_id],
    )
    users: Mapped[List["User"]] = relationship(
        "User",
        back_populates="org",
    )
    devices: Mapped[List["Device"]] = relationship(
        "Device",
        back_populates="org",
    )
