"""
设备类型模型（3.2 FR-007）
"""

from typing import List, Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.types import json_type


class DeviceType(Base):
    """消防设备类型表（预置 8 种，各自定义扩展属性模板）"""

    __tablename__ = "device_types"

    type_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    type_name: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    attribute_schema: Mapped[dict] = mapped_column(
        json_type(), default=dict, nullable=False
    )
    icon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    devices: Mapped[List["Device"]] = relationship(
        "Device",
        back_populates="device_type",
    )
