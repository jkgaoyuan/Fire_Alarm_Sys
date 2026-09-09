from sqlalchemy import ForeignKey, String, Boolean, Integer, Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base
from app.models.alarm import Alarm
from app.models.device import Device
from app.models.device_type import DeviceType
from app.models.organization import Organization
from app.models.user import User


class LinkagePlan(Base):
    __tablename__ = "linkage_plans"

    # 基础字段
    plan_name: Mapped[str] = mapped_column(String(100), nullable=False)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    fire_type: Mapped[str | None] = mapped_column(String(20))
    trigger_device_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("device_types.id"), index=True
    )
    trigger_alarm_type: Mapped[str | None] = mapped_column(String(20))
    actions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # DEC-004: created_by
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    # 关系
    creator: Mapped[User] = relationship("User", foreign_keys=[created_by])
    organization: Mapped[Organization] = relationship("Organization", foreign_keys=[org_id])
    trigger_device_type: Mapped[DeviceType] = relationship(
        "DeviceType", foreign_keys=[trigger_device_type_id]
    )


class AlarmLinkageLog(Base):
    __tablename__ = "alarm_linkage_logs"

    # 基础字段
    alarm_id: Mapped[int] = mapped_column(ForeignKey("alarms.id"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("linkage_plans.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(50))
    target_device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    executed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    result_message: Mapped[str | None] = mapped_column(Text)
    is_simulation: Mapped[bool] = mapped_column(Boolean, default=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=func.now())

    # 关系
    alarm: Mapped[Alarm] = relationship("Alarm", foreign_keys=[alarm_id])
    plan: Mapped[LinkagePlan] = relationship("LinkagePlan", foreign_keys=[plan_id])
    target_device: Mapped[Device] = relationship("Device", foreign_keys=[target_device_id])
