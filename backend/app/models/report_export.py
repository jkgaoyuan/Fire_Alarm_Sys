"""
报表导出任务模型（3.9 FR-052）
========================================
设计决策：
- 统一异步导出框架：Excel/CSV/Word 均通过 report_export_tasks 表跟踪
- task_type 枚举：alarm_trend / device_status / fault_top10 / inspection / drill_report
- status 状态机：pending → running → completed / failed
- 首版不实现任务恢复（OQ-6），失败由用户重试
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.types import json_type


# ==================== 枚举常量 ====================

EXPORT_TASK_TYPES = (
    "alarm_trend",
    "device_status",
    "fault_top10",
    "inspection",
    "drill_report",
)

EXPORT_TASK_STATUSES = ("pending", "running", "completed", "failed")


# ==================== 模型类 ====================

class ReportExportTask(Base):
    """报表导出任务表（FR-052）

    异步导出任务载体，记录导出状态、文件路径与失败原因。
    created_by 遵循 DEC-004，用于数据权限过滤（仅查看自己的导出任务）。
    """

    __tablename__ = "report_export_tasks"

    task_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="任务编号")
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="导出类型")
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True, comment="状态 pending/running/completed/failed"
    )
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="文件存储路径")
    file_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="下载文件名")
    total_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="总行数")
    params: Mapped[Optional[dict]] = mapped_column(json_type(), nullable=True, comment="导出参数")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="失败原因")
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="创建人（DEC-004）"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="完成时间"
    )

    # 关联关系
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<ReportExportTask id={self.id} task_no='{self.task_no}' status={self.status}>"
