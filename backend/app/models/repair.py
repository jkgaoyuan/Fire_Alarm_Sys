"""
维修工单模型（3.7 FR-038 ~ FR-042）
========================================
PRD 章节：3.7 故障维修
功能点：
- FR-038: 故障报修（巡检异常自动创建工单）
- FR-039: 工单流转（6 种状态枚举）
- FR-040: 维修记录（配件明细手动填写）
- FR-041: 维修验收（消防主管验收）
- FR-042: 维修统计（4 项统计指标）

表结构设计：
1. repair_orders - 维修工单表

注意事项：
- 内部系统，无数据权限过滤，所有人可访问
- reporter_id/created_by 仅用于审计追踪和统计报表
- 验收权限：仅消防主管可执行
- 巡检异常自动转工单：inspection_record_id 唯一约束防止重复
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


# ==================== 枚举定义 ====================

class RepairOrderStatus(str, Enum):
    """工单状态枚举（6 种）"""
    pending = "pending"                    # 待处理
    assigned = "assigned"                  # 已派单
    repairing = "repairing"                # 维修中
    pending_accept = "pending_accept"      # 待验收
    completed = "completed"                # 已完成（验收通过）
    returned = "returned"                  # 已退回（验收不通过）


# 状态流转规则
REPAIR_ORDER_STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "pending": ("assigned",),
    "assigned": ("repairing",),
    "repairing": ("pending_accept",),
    "pending_accept": ("completed", "returned"),
    "returned": ("repairing",),  # 退回后重新维修
    "completed": (),  # 终态
}


# ==================== 模型类 ====================

class RepairOrder(Base):
    """维修工单表（FR-038 ~ FR-042）

    巡检发现故障或监控发现故障时，自动生成报修工单。
    工单关联设备与故障描述。
    """

    __tablename__ = "repair_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 工单编号（唯一）
    order_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    
    # 关联字段
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id"), index=True, nullable=False
    )
    alarm_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("alarms.id"), index=True, nullable=True
    )
    inspection_record_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("inspection_records.id"), index=True, unique=True, nullable=True
    )
    
    # 故障描述
    fault_desc: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 状态
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    
    # 人员字段
    reporter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    repairer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    acceptor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    
    # 时间字段
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # 维修结果（含配件明细）
    repair_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 退回原因
    return_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 审计字段
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False
    )
    
    # 关联关系
    device: Mapped["Device"] = relationship("Device", backref="repair_orders")
    alarm: Mapped[Optional["Alarm"]] = relationship("Alarm", backref="repair_orders")
    inspection_record: Mapped[Optional["InspectionRecord"]] = relationship(
        "InspectionRecord", backref="repair_order"
    )
    reporter: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[reporter_id], backref="reported_repairs"
    )
    repairer: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[repairer_id], backref="assigned_repairs"
    )
    acceptor: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[acceptor_id], backref="accepted_repairs"
    )
    creator: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by], backref="created_repairs"
    )
    
    def __repr__(self):
        return f"<RepairOrder id={self.id} order_no='{self.order_no}' status={self.status}>"


# ==================== 索引定义 ====================

# 为高频查询字段添加索引
Index("idx_repair_orders_device_status", RepairOrder.device_id, RepairOrder.status)
Index("idx_repair_orders_repairer_status", RepairOrder.repairer_id, RepairOrder.status)
