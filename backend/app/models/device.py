"""
设备档案与设备状态变更日志模型（3.2 FR-008 / FR-011）
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.types import json_type

DEVICE_STATUSES = (
    "normal",
    "alarm",
    "fault",
    "shield",
    "offline",
    "retired",
)


class Device(Base):
    """消防设备档案表

    退役（status='retired'）与逻辑删除（is_deleted=TRUE）是两条不同路径：
    退役为常规操作且必须保留关联历史，逻辑删除仅主管极少使用。
    """

    __tablename__ = "devices"

    device_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(100), nullable=False)
    type_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("device_types.id"),
        nullable=True,
    )
    org_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=True,
    )
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    spec: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    install_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    warranty_expire_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    maintain_cycle: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    last_report_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    map_x: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    map_y: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    attributes: Mapped[dict] = mapped_column(
        json_type(), default=dict, nullable=False
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    # 关联关系
    device_type: Mapped[Optional["DeviceType"]] = relationship(
        "DeviceType",
        back_populates="devices",
    )
    org: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="devices",
    )
    creator: Mapped[Optional["User"]] = relationship("User")
    status_logs: Mapped[List["DeviceStatusLog"]] = relationship(
        "DeviceStatusLog",
        back_populates="device",
        cascade="all, delete-orphan",
    )


class DeviceStatusLog(Base):
    """设备状态变更日志表（PRD ER 图包含，DDL 未给出，计划 2.1 补充）"""

    __tablename__ = "device_status_logs"

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    device: Mapped["Device"] = relationship(
        "Device",
        back_populates="status_logs",
    )
    changer: Mapped[Optional["User"]] = relationship("User")
