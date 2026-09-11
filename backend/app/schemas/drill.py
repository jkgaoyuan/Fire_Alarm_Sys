"""
消防演练相关 Pydantic Schemas（3.8 FR-043 ~ FR-047）
=====================================================
对应 PRD 5.1 章节的 API 请求/响应格式定义
遵循项目统一响应格式规范 `{code, message, data, timestamp}`
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


# ==================== 枚举类型 ====================

class DrillType(str, Enum):
    """演练类型"""
    evacuation = "evacuation"      # 疏散演练
    firefighting = "firefighting"  # 灭火演练
    comprehensive = "comprehensive" # 综合演练


class DrillStatus(str, Enum):
    """演练状态"""
    planned = "planned"     # 计划中
    ongoing = "ongoing"     # 执行中
    completed = "completed" # 已完成
    cancelled = "cancelled" # 已取消


# ==================== 请求体 Schema ====================

class DrillEventCreate(BaseModel):
    """创建演练事件请求体"""
    
    drill_name: str = Field(..., max_length=100, description="演练名称")
    drill_type: DrillType = Field(..., description="演练类型")
    planned_at: Optional[datetime] = Field(None, description="计划时间")
    location: Optional[str] = Field(None, max_length=255, description="演练地点")
    participant_user_ids: Optional[List[int]] = Field(None, description="参与人员用户 ID 列表")
    status: Optional[DrillStatus] = Field(DrillStatus.planned, description="初始状态")


class DrillEventUpdate(BaseModel):
    """更新演练事件请求体"""
    
    drill_name: Optional[str] = Field(None, max_length=100)
    drill_type: Optional[DrillType] = None
    planned_at: Optional[datetime] = None
    actual_start_at: Optional[datetime] = None
    actual_end_at: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=255)
    participant_user_ids: Optional[List[int]] = None
    status: Optional[DrillStatus] = None
    summary: Optional[str] = Field(None, description="现场总结记录")
    photos: Optional[List[Dict[str, str]]] = Field(None, description="现场照片 [{url, caption}]")
    videos: Optional[List[Dict[str, Any]]] = Field(None, description="现场视频 [{url, duration}]")


class ParticipantItem(BaseModel):
    """参与人员项（用于演练记录）"""
    user_id: int = Field(..., description="用户 ID")
    role: str = Field(..., max_length=50, description="参与角色")
    sign_in_at: Optional[datetime] = Field(None, description="签到时间")


class DrillParticipationRequest(BaseModel):
    """添加参与人员请求"""
    
    participant_user_id: int = Field(..., description="参与人员用户 ID")
    role: str = Field(..., max_length=50, description="参与角色，如：指挥员、疏散员、操作员等")


class EvaluationItem(BaseModel):
    """评估项打分"""
    
    item: str = Field(..., description="评估项名称，如：响应时间、疏散效率等")
    label: str = Field(..., description="评估项标签/描述")
    score: int = Field(..., ge=0, description="得分")
    max_score: int = Field(..., ge=0, description="满分")
    comment: Optional[str] = Field(None, description="该项评价说明")


class DrillEvaluationCreate(BaseModel):
    """提交演练评估请求"""
    
    drill_id: int = Field(..., description="关联演练 ID")
    items: List[EvaluationItem] = Field(..., description="评估项打分列表")
    problems: Optional[str] = Field(None, description="存在问题")
    improvements: Optional[str] = Field(None, description="改进措施")
    evaluation_summary: Optional[str] = Field(None, description="总体评估摘要（OQ-4 新增）")


# ==================== 响应体 Schema ====================

class DrillEventLite(BaseModel):
    """演练事件精简版（用于列表）"""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    drill_name: str
    drill_type: DrillType
    status: DrillStatus
    planned_at: Optional[datetime] = None
    location: Optional[str] = None
    created_at: datetime
    
    # 内联展示
    participant_count: int = Field(default=0, description="参与人数")
    has_evaluation: bool = Field(default=False, description="是否有评估")


class DrillEventResponse(DrillEventLite):
    """演练事件完整响应"""
    
    actual_start_at: Optional[datetime] = None
    actual_end_at: Optional[datetime] = None
    summary: Optional[str] = None
    photos: List[Dict[str, str]] = []
    videos: List[Dict[str, Any]] = []
    participants: List[ParticipantItem] = []
    created_by: Optional[int] = None
    updated_at: Optional[datetime] = None


class DrillEventWithEvaluation(DrillEventResponse):
    """演练事件 + 评估结果"""
    
    evaluation: Optional["DrillEvaluationResponse"] = None


# ==================== 评估响应 ====================

class DrillEvaluationLite(BaseModel):
    """评估精简版"""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    drill_id: int
    total_score: Optional[int] = None
    evaluated_at: Optional[datetime] = None
    evaluator_id: Optional[int] = None


class DrillEvaluationResponse(DrillEvaluationLite):
    """评估完整响应"""
    
    items: List[EvaluationItem]
    problems: Optional[str] = None
    improvements: Optional[str] = None
    evaluation_summary: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    evaluator_name: Optional[str] = None


# ==================== 分页封装 ====================

class DrillEventPagination(BaseModel):
    """演练事件分页响应"""
    
    items: List[DrillEventLite]
    total: int
    page: int
    page_size: int


class DrillEvaluationPagination(BaseModel):
    """演练评估分页响应"""
    
    items: List[DrillEvaluationLite]
    total: int
    page: int
    page_size: int


# ==================== 统计与导出 ====================

class DrillStatistics(BaseModel):
    """演练统计数据"""
    
    total_drills: int = Field(default=0, description="总演练数")
    completed_drills: int = Field(default=0, description="已完成演练数")
    this_month_drills: int = Field(default=0, description="本月演练数")
    avg_score: float = Field(default=0.0, description="平均评估分")
    completion_rate: float = Field(default=0.0, description="完成率")


class DrillExportParam(BaseModel):
    """演练报告导出参数"""
    
    drill_id: int = Field(..., description="演练 ID")
    include_photos: bool = Field(True, description="是否包含照片")
    include_videos: bool = Field(False, description="是否包含视频")
    language: str = Field("zh-CN", description="报告语言")


# ==================== 组合引用 ====================

DrillEvaluationResponse.model_forward_refs = {"DrillEventResponse": DrillEventResponse}
DrillEventWithEvaluation.model_forward_refs = {"DrillEvaluationResponse": DrillEvaluationResponse}

__all__ = [
    # 枚举
    "DrillType",
    "DrillStatus",
    # 请求体
    "DrillEventCreate",
    "DrillEventUpdate",
    "DrillParticipationRequest",
    "DrillEvaluationCreate",
    "EvaluationItem",
    # 响应体
    "DrillEventLite",
    "DrillEventResponse",
    "DrillEventWithEvaluation",
    "DrillEvaluationLite",
    "DrillEvaluationResponse",
    "ParticipantItem",
    "EvaluationItem",
    # 分页
    "DrillEventPagination",
    "DrillEvaluationPagination",
    # 其他
    "DrillStatistics",
    "DrillExportParam",
]
