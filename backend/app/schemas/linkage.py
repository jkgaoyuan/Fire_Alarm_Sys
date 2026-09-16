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
    is_simulation_allowed: bool = Field(True, description="是否允许模拟测试")


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
    is_simulation_allowed: Optional[bool] = None


class LinkagePlanOut(BaseModel):
    """预案响应"""

    id: int
    plan_name: str
    org_id: int
    # 关联区域名。前端表格与详情抽屉都要显示，只给 org_id 的话前端得再查一次
    # 组织接口才能显示名字。口径与 device/inspection/user 等模块一致：扁平字段，
    # 由端点在 ORM → schema 时补上（见 linkage_plans._plan_out）。
    org_name: Optional[str] = None
    fire_type: Optional[str] = None
    trigger_device_type_id: Optional[int] = None
    trigger_alarm_type: Optional[str] = None
    actions: list[dict]
    is_enabled: bool
    is_simulation_allowed: bool = True
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
    # 展示用：列表页只有 id 的话还得再查一次预案/设备才能显示名字
    plan_name: Optional[str] = None
    action_type: str
    target_device_id: Optional[int] = None
    target_device_name: Optional[str] = None
    status: str
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_message: Optional[str] = None
    is_simulation: bool
    # 该日志是否由演练告警触发。日志表本身没有这个字段，取自关联告警的
    # `is_drill`——「这条联动是真火警跑的，还是模拟测试跑的」必须能分辨，
    # 否则事后回看时两者长得一模一样。
    is_drill: bool = False
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
    """
    手动执行预案请求。

    `plan_id` 是**必填**：路由是 `/linkage-plans/execute`，以预案为中心，
    端点内部也一直按 `data.plan_id` 在取——但本 schema 漏了这个字段，
    导致每次调用都在 `data.plan_id` 上抛 AttributeError → HTTP 500
    （见 tests/test_linkage_plans_api.py 的 TC-LP-009）。
    同文件的 `LinkageSimulateTrigger` 早就有 `plan_id`，此处与之对齐。
    `alarm_id` 仍可空：为空即「独立演练」，不为空则记录是哪条报警触发的。
    """

    plan_id: int = Field(..., description="预案 ID")
    alarm_id: Optional[int] = Field(None, description="报警 ID，可为空（演练模式）")
    is_simulation: bool = Field(False, description="是否模拟执行")
    remark: Optional[str] = Field(None, description="执行备注")


class LinkageSimulateTrigger(BaseModel):
    """模拟触发预案请求"""

    plan_id: int = Field(..., description="预案 ID")
    is_simulation: bool = Field(True, description="固定为 True")
    remark: Optional[str] = Field(None, description="备注")


class LinkageExecuteResult(BaseModel):
    """
    手动执行预案的响应体。

    端点此前直接返回裸 dict `{message, logs}`——注意内层那个 `message`
    会与外层信封的 `message` 撞名，读响应时极易混淆，所以单独建模收进 data。
    字段名与改造前一致，不影响调用方。
    """

    message: str
    logs: list[AlarmLinkageLogOut]


class LinkageSimulateResult(BaseModel):
    """
    模拟测试的结果。

    模拟会生成一条**演练告警**并交给联动引擎按真实规则匹配，因此结果里
    必须能看出「到底命中了哪些预案」——`included_self` 是其中的关键信号：
    它为假说明**被点击的这条预案在当前配置下不会被任何报警触发**，
    而这正是旧实现（直接跑预案动作、绕开匹配）永远暴露不出来的问题。
    """

    alarm_id: int = Field(..., description="生成的演练告警 ID")
    alarm_type: str = Field(..., description="所用报警类型：fire/pre_fire")
    org_id: Optional[int] = Field(None, description="告警所属区域")
    device_id: int = Field(..., description="承载该告警的设备")
    device_code: Optional[str] = None
    is_drill: bool = Field(True, description="固定为 True")
    matched_plan_ids: list[int] = Field(default_factory=list, description="命中的预案 ID")
    matched_plan_names: list[str] = Field(default_factory=list, description="命中的预案名称")
    included_self: bool = Field(
        False, description="被点击的预案是否在命中列表里"
    )
    logs: list[AlarmLinkageLogOut] = Field(
        default_factory=list, description="本次模拟新产生的联动日志"
    )


# ==================== Action Schema ====================

ACTION_TYPES = [
    "start_exhaust",      # 启动排烟
    "close_door",         # 关闭防火门
    "start_lighting",     # 启动应急照明
    "broadcast",          # 疏散广播
]
