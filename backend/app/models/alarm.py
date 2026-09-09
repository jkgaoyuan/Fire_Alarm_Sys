"""
报警模型（3.3 FR-013 ~ FR-017）

alarms 表在 PRD 4.2 基础上按开发计划 4.1 补齐：
- org_id / device_code：设备归属区域与编码快照，供数据权限过滤与地图定位
- silenced_* / reset_*：FR-016.1 消音与 FR-016.2 复位的留痕
- pending_since：为 FR-025 超时升级预留（本模块只写不判）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

ALARM_TYPES = ("fire", "pre_fire", "fault", "shield")

ALARM_STATUSES = ("pending", "confirmed", "false_alarm", "processing", "resolved")

CONFIRM_RESULTS = ("real", "false_alarm")

# FR-031 状态机在 3.3 的子集：closed 与 processing 的后续流转属 3.5 应急处置
ALARM_STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "pending": ("confirmed", "false_alarm", "resolved"),
    "confirmed": ("processing", "resolved"),
    "processing": ("resolved",),
    "false_alarm": ("resolved",),
    "resolved": (),
}

# FR-017 报警分级 → 级别、提示音键与设备状态：前端按 alarm_level 选择音频与配色，
# B-13 上报入库按 device_status 驱动 devices.status（单一事实源，避免两处映射漂移）
ALARM_TYPE_PROFILE: dict[str, dict[str, str]] = {
    "fire": {
        "alarm_level": "critical",
        "color": "red",
        "sound": "fire",
        "device_status": "alarm",
    },
    "pre_fire": {
        "alarm_level": "major",
        "color": "orange",
        "sound": "pre_fire",
        "device_status": "alarm",
    },
    "fault": {
        "alarm_level": "minor",
        "color": "yellow",
        "sound": "fault",
        "device_status": "fault",
    },
    "shield": {
        "alarm_level": "minor",
        "color": "gray",
        "sound": "shield",
        "device_status": "shield",
    },
}

# 未收敛报警：同设备同类型在该集合内时更新而非新建（防报警风暴）
OPEN_ALARM_STATUSES = ("pending", "confirmed", "processing")


class Alarm(Base):
    """报警记录表"""

    __tablename__ = "alarms"
    __table_args__ = (
        Index("idx_alarms_pending_top", "status", "alarm_type", "created_at"),
        Index("idx_alarms_device_status", "device_id", "status"),
    )

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
    )
    device_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    alarm_type: Mapped[str] = mapped_column(String(20), nullable=False)
    alarm_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

    confirmed_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirm_result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    false_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    silenced_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    silenced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reset_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reset_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reset_remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    location_description: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    is_drill: Mapped[bool] = mapped_column(default=False, nullable=False)
    pending_since: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    device: Mapped[Optional["Device"]] = relationship("Device")
    org: Mapped[Optional["Organization"]] = relationship("Organization")
    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])
    confirmer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[confirmed_by])


def can_transition(old_status: str, new_status: str) -> bool:
    """报警状态流转是否合法"""
    return new_status in ALARM_STATUS_TRANSITIONS.get(old_status, ())
