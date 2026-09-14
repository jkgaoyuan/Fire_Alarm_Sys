"""
巡检相关 Pydantic Schemas（3.6 FR-032 ~ FR-037）
================================================
对应 PRD 5.1 章节的 API 请求/响应格式定义
遵循项目统一响应格式规范 `{code, message, data, timestamp}`
"""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


# ==================== 枚举类型 ====================

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


# ==================== 请求体 Schema ====================

class InspectionPlanCreate(BaseModel):
    """创建巡检计划请求体"""

    plan_name: str = Field(..., max_length=100, description="计划名称")
    org_id: Optional[int] = Field(None, description="区域 ID（可选，不填则默认为用户部门）")
    device_type_id: Optional[int] = Field(None, description="设备类型 ID（可选，不填则遍历所有设备）")
    cycle_type: InspectionCycleType = Field(..., description="周期类型")
    cycle_days: Optional[int] = Field(None, description="周期天数（周/月时使用，如每周的第几天）")
    responsible_user_id: int = Field(..., description="责任人 ID")
    start_date: date = Field(..., description="开始日期")
    end_date: Optional[date] = Field(None, description="结束日期（可选）")


class InspectionPlanUpdate(BaseModel):
    """更新巡检计划请求体"""

    plan_name: Optional[str] = Field(None, max_length=100)
    org_id: Optional[int] = Field(None)
    device_type_id: Optional[int] = Field(None)
    cycle_type: Optional[InspectionCycleType] = None
    cycle_days: Optional[int] = None
    responsible_user_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_enabled: Optional[bool] = None


# ==================== 响应体 Schema ====================

class InspectionPlanResponse(BaseModel):
    """巡检计划详情响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_name: str
    org_id: Optional[int] = None
    device_type_id: Optional[int] = None
    cycle_type: InspectionCycleType
    cycle_days: Optional[int] = None
    responsible_user_id: int
    start_date: date
    end_date: Optional[date] = None
    is_enabled: bool
    created_at: datetime


class InspectionPlanWithStats(InspectionPlanResponse):
    """巡检计划详情 + 统计信息"""

    total_tasks: int = Field(default=0, description="总任务数")
    completed_tasks: int = Field(default=0, description="已完成任务数")
    missed_tasks: int = Field(default=0, description="漏检任务数")
    completion_rate: float = Field(default=0.0, description="完成率（0~1）")


class InspectionTaskResponse(BaseModel):
    """巡检任务响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    task_date: date
    status: InspectionTaskStatus
    completed_at: Optional[datetime] = None
    created_at: datetime
    
    # 关联字段（内联展示）
    plan_name: Optional[str] = None
    plan_cycle_type: Optional[InspectionCycleType] = None
    responsible_user_id: Optional[int] = None
    responsible_user_name: Optional[str] = None

    # 该任务已提交的记录数，供列表页「已记录数」列使用。
    # ⚠️ 必须由端点**显式填充**，不能指望它自己冒出来：
    # 该指标此前以 `records`（列表）的形式声明在 InspectionTaskWithDetails 上，
    # 但列表端点从未填过它（全仓库 `records=` 无赋值）→ 永远是默认的 `[]`；
    # 而前端一个页面读 `records_count`（字段根本不存在）、
    # 另一个读 `records?.length`（恒为 0），**两个页面都恒显示 0**。
    # 列表页要的是「数量」不是「记录列表」，故在此声明计数字段。
    records_count: int = 0


class InspectionTaskWithDetails(InspectionTaskResponse):
    """巡检任务详情（包含记录列表）"""

    records: List["InspectionRecordLite"] = []


class InspectionRecordLite(BaseModel):
    """巡检记录精简版（用于任务详情）"""

    id: int
    device_id: int
    device_code: str
    device_name: str
    result: InspectionRecordResult
    abnormal_desc: Optional[str] = None
    photos: List[str] = []
    inspected_by: Optional[int] = None
    inspected_by_name: Optional[str] = None
    inspected_at: datetime


class InspectionRecordCreate(BaseModel):
    """提交巡检记录请求体"""

    task_id: int = Field(..., description="任务 ID")
    device_id: int = Field(..., description="设备 ID")
    result: InspectionRecordResult = Field(..., description="巡检结果")
    abnormal_desc: Optional[str] = Field(None, description="异常情况描述（仅异常时填写）")
    photos: List[str] = Field(default=[], description="照片 URL 数组")


class InspectionRecordResponse(BaseModel):
    """巡检记录响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    device_id: int
    device_code: str
    device_name: str
    result: InspectionRecordResult
    abnormal_desc: Optional[str] = None
    photos: List[str] = []
    inspected_by: Optional[int] = None
    inspected_by_name: Optional[str] = None
    created_by: Optional[int] = None
    inspected_at: datetime


class InspectionTaskDeviceItem(BaseModel):
    """
    巡检任务的「应检设备」条目（供执行巡检弹窗的设备选择器使用）。

    只保留选择器要展示/判断的字段，不返回设备档案的全量形态：
    这里要回答的是「这个任务该检哪些设备」，不是「设备档案长什么样」。
    """

    id: int
    device_code: str
    device_name: str
    type_id: Optional[int] = None
    type_name: Optional[str] = None
    org_id: Optional[int] = None
    org_name: Optional[str] = None
    status: str


class InspectionTaskDevicePagination(BaseModel):
    """应检设备分页响应"""

    items: List[InspectionTaskDeviceItem]
    total: int
    page: int
    page_size: int


class InspectionMissedStat(BaseModel):
    """漏检统计数据"""

    task_date: date
    missed_count: int
    overdue_hours: float
    affected_plans: List[dict] = []
    notification_sent: bool = False


# ==================== 分页封装 ====================


class InspectionPlanPagination(BaseModel):
    """巡检计划分页响应"""
    items: List[InspectionPlanWithStats]
    total: int
    page: int
    page_size: int


class InspectionTaskPagination(BaseModel):
    """巡检任务分页响应"""
    # 用 InspectionTaskResponse 而非 WithDetails：列表端点建的就是前者，
    # 而 WithDetails 多出的 `records` 列表从未被填充过——声明它只会让响应里
    # 出现一个恒为 [] 的字段，前端照着读就会显示 0（实际发生过）。
    # 需要记录数请用 InspectionTaskResponse.records_count。
    items: List[InspectionTaskResponse]
    total: int
    page: int
    page_size: int


class InspectionRecordPagination(BaseModel):
    """巡检记录分页响应"""
    items: List[InspectionRecordResponse]
    total: int
    page: int
    page_size: int


__all__ = [
    # 请求体
    "InspectionPlanCreate",
    "InspectionPlanUpdate",
    "InspectionRecordCreate",
    # 响应体
    "InspectionPlanResponse",
    "InspectionPlanWithStats",
    "InspectionTaskResponse",
    "InspectionTaskWithDetails",
    "InspectionRecordLite",
    "InspectionRecordResponse",
    "InspectionTaskDeviceItem",
    "InspectionTaskDevicePagination",
    "InspectionMissedStat",
    # 分页封装
    "InspectionPlanPagination",
    "InspectionTaskPagination",
    "InspectionRecordPagination",
]
