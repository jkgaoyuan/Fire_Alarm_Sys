"""
应急事件相关 Schema
3.5 模块新增
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class EmergencyEventBase(BaseModel):
    """应急事件基础字段"""
    alarm_id: int = Field(..., description="关联报警 ID")
    event_no: Optional[str] = Field(None, max_length=50, description="事件编号 EV-YYYYMMDD-NNN")
    status: str = Field(default="processing", description="处理中/已完成/已关闭")


class EmergencyEventCreate(EmergencyEventBase):
    """创建应急事件（通常由系统自动创建）"""
    pass


class EmergencyEventOut(EmergencyEventBase):
    """应急事件输出 schema"""
    id: int
    started_at: Optional[str] = None
    resolved_at: Optional[str] = None
    closed_at: Optional[str] = None
    closed_by: Optional[int] = None
    summary: Optional[str] = None
    created_by: int
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class EmergencyEventDetailOut(EmergencyEventOut):
    """应急事件详情（包含关联数据）"""
    alarm: dict = Field(..., description="关联报警信息")
    timelines: list = Field(default=[], description="时间轴节点列表")
    creator: dict = Field(..., description="创建人信息")
    closer: Optional[dict] = Field(None, description="关闭人信息")


class EmergencyEventListOut(BaseModel):
    """分页事件列表"""
    items: list[EmergencyEventOut]
    total: int
    page: int
    page_size: int
    total_pages: int

    class Config:
        from_attributes = True


class EmergencyEventStatusChange(BaseModel):
    """事件状态变更请求"""
    summary: Optional[str] = Field(None, max_length=1000, description="处置总结（resolve 时使用）")


class EmergencyTimelineBase(BaseModel):
    """时间轴节点基础字段"""
    node_type: str = Field(..., max_length=50, description="节点类型：alarm/confirm/linkage/escalation/evacuate/control/check_in/photo/complete")
    node_title: Optional[str] = Field(None, max_length=100, description="节点标题")
    description: Optional[str] = Field(None, description="描述")
    attachments: list[dict] = Field(default=list, description="附件 [{type, url}] 仅支持照片")


class EmergencyTimelineCreate(EmergencyTimelineBase):
    """创建设置时间轴节点"""
    pass


class EmergencyTimelineOut(EmergencyTimelineBase):
    """时间轴节点输出"""
    id: int
    event_id: int
    operator_id: Optional[int] = None
    operated_at: str
    created_at: str

    class Config:
        from_attributes = True


class EmergencyTimelineWithOperatorOut(EmergencyTimelineOut):
    """带操作人信息的时间轴节点"""
    operator: Optional[dict] = None


class EmergencyTimelineListOut(BaseModel):
    """时间轴列表"""
    items: list[EmergencyTimelineWithOperatorOut]
    total: int

    class Config:
        from_attributes = True


class CheckInRequest(BaseModel):
    """签到请求（复用 timeline API，node_type='check_in'）"""
    description: Optional[str] = Field(None, max_length=255, description="签到备注")


# ==================== 通知中心 Schema ====================

class NotificationBase(BaseModel):
    """通知基础字段"""
    title: str = Field(..., max_length=100)
    content: Optional[str] = Field(None)
    module: Optional[str] = Field(None, description="emergency/linkage/system")
    ref_id: Optional[int] = Field(None, description="关联业务 ID")


class NotificationCreate(NotificationBase):
    """创建通知"""
    user_id: int


class NotificationOut(BaseModel):
    """通知输出"""
    id: int
    user_id: int
    title: str
    content: Optional[str] = None
    module: Optional[str] = None
    ref_id: Optional[int] = None
    is_read: bool
    created_at: str

    class Config:
        from_attributes = True


class NotificationListOut(BaseModel):
    """分页通知列表"""
    items: list[NotificationOut]
    total: int
    page: int
    page_size: int
    total_pages: int

    class Config:
        from_attributes = True


class ReadNotificationRequest(BaseModel):
    """标记已读请求"""
    notification_ids: list[int] = Field(..., description="通知 ID 列表")


class UnreadCountOut(BaseModel):
    """未读数统计"""
    unread_count: int


class EventReportRequest(BaseModel):
    """报告导出请求"""
    include_timeline: bool = Field(default=True, description="包含时间轴")
    include_photos: bool = Field(default=True, description="包含照片")
    format: str = Field(default="pdf", description="pdf/html")
