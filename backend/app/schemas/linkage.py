"""
联动预案相关 Schema（3.4-B1）
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ==================== LinkagePlan Schema ====================

class LinkagePlanBase(BaseModel):
    """预案基础字段"""
    
    plan_name: str = Field(..., min_length=1, max_length=100, description="预案名称")
    org_id: int = Field(..., description="关联区域 ID")
    fire_type: Optional[str] = Field(None, description="火灾类型：A/B/C/electrical")
    trigger_device_type_id: Optional[int] = Field(None, description="触发设备类型 ID")
    trigger_alarm_type: Optional[str] = Field(
        None, 
        description="触发报警类型：fire/pre_fire/fault/shield"
    )
    actions: list[dict] = Field(default=list, description="动作列表")
    is_enabled: bool = Field(True, description="是否启用")


class LinkagePlanCreate(LinkagePlanBase):
    """创建预案请求"""
    pass


class LinkagePlanUpdate(BaseModel):
    """更新预案请求"""
    
    plan_name: Optional[str] = Field(None, min_length=1, max_length=100)
    org_id: Optional[int] = None
    fire_type: Optional[str] = None
    trigger_device_type_id: Optional[int] = None
    trigger_alarm_type: Optional[str] = None
    actions: Optional[list[dict]] = None
    is_enabled: Optional[bool] = None


class LinkagePlanOut(BaseModel):
    """预案响应"""
    
    id: int
    plan_name: str
    org_id: int
    fire_type: Optional[str] = None
    trigger_device_type_id: Optional[int] = None
    trigger_alarm_type: Optional[str] = None
    actions: list[dict]
    is_enabled: bool
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class LinkagePlanPagination(BaseModel):
    """预案分页响应"""
    
    items: list[LinkagePlanOut]
    total: int
    page: int
    page_size: int


# ==================== AlarmLinkageLog Schema ====================

class AlarmLinkageLogBase(BaseModel):
    """日志基础字段"""
    
    alarm_id: int = Field(..., description="触发报警 ID")
    plan_id: Optional[int] = Field(None, description="来源预案 ID")
    action_type: str = Field(..., description="动作类型")
    target_device_id: Optional[int] = Field(None, description="目标设备 ID")
    status: str = Field("pending", description="执行状态：pending/sent/success/failed")
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_message: Optional[str] = None
    is_simulation: bool = Field(False, description="是否为模拟触发")
    delay_seconds: int = Field(0, description="延迟秒数")


class AlarmLinkageLogCreate(AlarmLinkageLogBase):
    """创建日志请求"""
    pass


class AlarmLinkageLogUpdate(BaseModel):
    """更新日志请求"""
    
    status: Optional[str] = None
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_message: Optional[str] = None
    is_simulation: Optional[bool] = None


class AlarmLinkageLogOut(BaseModel):
    """日志响应"""
    
    id: int
    # 模拟触发的日志没有真实告警，故可空
    alarm_id: Optional[int] = None
    plan_id: Optional[int] = None
    action_type: str
    target_device_id: Optional[int] = None
    status: str
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_message: Optional[str] = None
    is_simulation: bool
    delay_seconds: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class AlarmLinkageLogPagination(BaseModel):
    """日志分页响应"""
    
    items: list[AlarmLinkageLogOut]
    total: int
    page: int
    page_size: int


# ==================== Manual Execute Schema ====================

class LinkageManualExecute(BaseModel):
    """手动执行预案请求"""
    
    alarm_id: Optional[int] = Field(None, description="报警 ID，可为空（演练模式）")
    is_simulation: bool = Field(False, description="是否模拟执行")
    remark: Optional[str] = Field(None, description="执行备注")


class LinkageSimulateTrigger(BaseModel):
    """模拟触发预案请求"""
    
    plan_id: int = Field(..., description="预案 ID")
    is_simulation: bool = Field(True, description="固定为 True")
    remark: Optional[str] = Field(None, description="备注")


# ==================== Action Schema ====================

ACTION_TYPES = [
    "start_exhaust",      # 启动排烟
    "close_door",         # 关闭防火门
    "start_lighting",     # 启动应急照明
    "broadcast",          # 疏散广播
]
