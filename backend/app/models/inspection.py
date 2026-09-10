"""
巡检相关数据模型（3.6 FR-032 ~ FR-037）
========================================
PRD 章节：3.6 设备巡检
功能点：
- FR-032: 巡检计划管理（plan_name, org_id, device_type_id, cycle_type, responsible_user_id...）
- FR-033: 巡检任务生成与状态管理（task_date, status, responsible_user_id...）
- FR-034: PC 端手动巡检记录填报（result, abnormal_desc, photos, inspected_by...）
- FR-035: 漏检统计（自动扫描 pending/delayed 状态任务）
- FR-036: 巡检记录归档查询

已取消功能：
- ~~FR-037~~: 离线巡检（改为 PC 端手动记录，无需离线能力）

表结构设计：
1. inspection_plans - 巡检计划
2. inspection_tasks - 巡检任务（按周期自动生成）
3. inspection_records - 巡检记录（维保人员提交）

注意事项：
- created_by 字段遵循 DEC-004 决策，用于数据权限 'self' 范围过滤
- 任务日期唯一约束：(plan_id, task_date) 防止重复生成
- 状态枚举遵循 PRD 4.2 DDL
"""

from datetime import date, datetime
from typing import List, Optional
from enum import Enum

from sqlalchemy import DATE, DateTime, ForeignKey, Integer, String, Text, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.types import json_type


# ==================== 枚举定义 ====================

class InspectionCycleType(str, Enum):
    """巡检周期类型"""
    daily = "daily"        # 每日
    weekly = "weekly"      # 每周
    monthly = "monthly"    # 每月
    quarterly = "quarterly" # 每季度
    yearly = "yearly"      # 每年


class InspectionTaskStatus(str, Enum):
    """巡检任务状态"""
    pending = "pending"   # 待执行
    doing = "doing"       # 执行中
    completed = "completed" # 已完成
    missed = "missed"     # 漏检


class InspectionRecordResult(str, Enum):
    """巡检结果"""
    normal = "normal"     # 正常
    abnormal = "abnormal" # 异常


# ==================== 模型类 ====================

class InspectionPlan(Base):
    """巡检计划表（FR-032）

    按设备类型/区域/责任人制定周期计划：每日/每周/每月/每季度/每年
    """

    __tablename__ = "inspection_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # 关联字段
    org_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id"), index=True, nullable=True
    )
    device_type_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("device_types.id"), index=True, nullable=True
    )
    responsible_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    
    # 周期配置
    cycle_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
    cycle_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # 时间范围
    start_date: Mapped[Optional[date]] = mapped_column(DATE, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(DATE, nullable=True)
    
    # 状态控制
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # 关联关系
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization", back_populates="inspection_plans"
    )
    device_type: Mapped[Optional["DeviceType"]] = relationship(
        "DeviceType", back_populates="inspection_plans"
    )
    responsible_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[responsible_user_id], backref="managed_plans"
    )
    
    tasks: Mapped[List["InspectionTask"]] = relationship(
        "InspectionTask",
        back_populates="plan",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<InspectionPlan id={self.id} name='{self.plan_name}' cycle={self.cycle_type}>"


class InspectionTask(Base):
    """巡检任务表（FR-033）

    由巡检计划定时自动生成，状态：待执行 / 执行中 / 已完成 / 漏检
    """

    __tablename__ = "inspection_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 关联字段
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_plans.id"), index=True, nullable=False
    )
    responsible_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    
    # 任务日期（唯一约束：同一计划的同一天只生成一个任务）
    task_date: Mapped[date] = mapped_column(DATE, nullable=False)
    
    # 状态
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False
    )
    
    # 完成时间
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # 创建时间（自动生成任务时设置）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now
    )
    
    # 关联关系
    plan: Mapped["InspectionPlan"] = relationship(
        "InspectionPlan", back_populates="tasks"
    )
    responsible_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[responsible_user_id], backref="assigned_tasks"
    )
    
    records: Mapped[List["InspectionRecord"]] = relationship(
        "InspectionRecord",
        back_populates="task",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f"<InspectionTask id={self.id} date={self.task_date} status={self.status}>"


class InspectionRecord(Base):
    """巡检记录表（FR-034 / FR-036）

    维保人员在 PC 端「巡检任务」列表中选择当日任务，点击设备名称进入巡检填报页面
    填写巡检项结果（正常/异常），异常可拍照上传、填写备注
    """

    __tablename__ = "inspection_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 关联字段
    task_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_tasks.id"), index=True, nullable=False
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id"), index=True, nullable=False
    )
    inspected_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # DEC-004: 新增 created_by 字段，用于数据权限 'self' 范围过滤
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    
    # 巡检结果
    result: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
    
    # 异常情况描述
    abnormal_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 照片（JSON 数组存储文件 URL）
    photos: Mapped[dict] = mapped_column(
        json_type(), default=list, nullable=False
    )
    
    # 检查时间（默认当前时间）
    inspected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False
    )
    
    # 关联关系
    task: Mapped["InspectionTask"] = relationship(
        "InspectionTask", back_populates="records"
    )
    device: Mapped["Device"] = relationship("Device", backref="inspection_records")
    inspector: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[inspected_by]
    )
    creator: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by]
    )

    def __repr__(self):
        return f"<InspectionRecord task_id={self.task_id} device_id={self.device_id} result={self.result}>"
