"""
报表导出相关 Pydantic Schema（3.9 FR-052）
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ExportTaskCreate(BaseModel):
    """创建导出任务请求体"""
    task_type: str = Field(..., description="导出类型：alarm_trend/device_status/fault_top10/inspection/drill_report")
    params: Optional[dict] = Field(default=None, description="导出参数（时间范围、区域等）")


class ExportTaskOut(BaseModel):
    """导出任务输出"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_no: str
    task_type: str
    status: str
    file_name: Optional[str] = None
    total_rows: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class ExportTaskListOut(BaseModel):
    """导出任务列表输出"""
    items: list[ExportTaskOut]
    total: int
