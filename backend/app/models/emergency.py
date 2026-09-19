"""
应急事件与时间轴模型
3.5 模块新增模型
"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import relationship
from app.models.base import Base
from app.models.types import bigint_pk


class EmergencyEvent(Base):
    """
    应急事件表
    关联报警，记录真实火警的应急处置全过程
    """
    __tablename__ = "emergency_events"

    id = Column(bigint_pk(), primary_key=True, autoincrement=True)
    alarm_id = Column(BigInteger, ForeignKey("alarms.id"), unique=True, index=True, nullable=False)
    event_no = Column(String(50), unique=True, nullable=False)  # EV-YYYYMMDD-NNN
    status = Column(String(20), default="processing")  # processing / resolved / closed
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    summary = Column(Text, nullable=True)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关联关系
    alarm = relationship("Alarm", backref="emergency_event")
    creator = relationship("User", foreign_keys=[created_by])
    closer = relationship("User", foreign_keys=[closed_by])


class EmergencyTimeline(Base):
    """
    应急处置时间轴
    记录处置过程中的关键节点
    """
    __tablename__ = "emergency_timelines"

    id = Column(bigint_pk(), primary_key=True, autoincrement=True)
    event_id = Column(BigInteger, ForeignKey("emergency_events.id"), index=True, nullable=False)
    node_type = Column(String(50), nullable=False)  # alarm / confirm / linkage / escalation / evacuate / control / check_in / photo / complete
    node_title = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    operator_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    operated_at = Column(DateTime(timezone=True), server_default=func.now())
    attachments = Column(JSON, default=list)  # [{"type": "photo", "url": "..."}] 仅支持照片附件
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关联关系
    event = relationship("EmergencyEvent", backref="timelines")
    operator = relationship("User", foreign_keys=[operator_id])


class Notification(Base):
    """
    系统通知表
    用于超时升级通知及其他系统消息
    """
    __tablename__ = "notifications"

    id = Column(bigint_pk(), primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True, nullable=False)
    title = Column(String(100), nullable=False)
    content = Column(Text, nullable=True)
    module = Column(String(50), nullable=True)  # emergency / linkage / system
    ref_id = Column(BigInteger, nullable=True)  # 关联业务 ID
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关联关系
    user = relationship("User", backref="notifications")
