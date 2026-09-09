"""
报警与实时监控相关 Pydantic Schema（3.3）

响应字段命名与 3.2 schemas/device.py 保持一致风格；
统一响应体仍沿用项目既有 {code, message, data} 结构。
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

ALARM_TYPE_PATTERN = r"^(fire|pre_fire|fault|shield)$"
ALARM_STATUS_PATTERN = r"^(pending|confirmed|false_alarm|processing|resolved)$"
CONFIRM_RESULT_PATTERN = r"^(real|false_alarm)$"

# FR-017 分级配色与提示音键，前端直接消费，避免魔法字散落组件
ALARM_LEVEL_COLOR = {
    "critical": "red",
    "major": "orange",
    "minor": "yellow",
}


class AlarmOut(BaseModel):
    """报警输出（含设备与区域快照，供大屏/地图/报警中心共用）"""

    id: int
    device_id: int
    device_code: str | None = None
    device_name: str | None = None
    org_id: int | None = None
    org_name: str | None = None
    map_x: float | None = None
    map_y: float | None = None
    alarm_type: str
    alarm_level: str | None = None
    status: str
    location_description: str | None = None
    is_drill: bool
    confirmed_by: int | None = None
    confirmed_at: datetime | None = None
    confirm_result: str | None = None
    false_reason: str | None = None
    silenced_by: int | None = None
    silenced_at: datetime | None = None
    reset_at: datetime | None = None
    pending_since: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime

    @field_validator("map_x", "map_y", mode="before")
    @classmethod
    def _decimal_to_float(cls, v):
        return float(v) if v is not None else None

    class Config:
        from_attributes = True


class AlarmListOut(BaseModel):
    """报警分页列表"""

    items: list[AlarmOut]
    total: int
    page: int
    page_size: int


class AlarmConfirmRequest(BaseModel):
    """FR-025/FR-026 火警确认（最小状态流转）"""

    confirm_result: str = Field(..., pattern=CONFIRM_RESULT_PATTERN)
    false_reason: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def _require_false_reason(self):
        # 误报必须填写原因（FR-026）。field_validator 在校验默认值时不会触发，
        # 缺省的 false_reason 会绕过它，因此只能在模型层判。
        reason = self.false_reason and self.false_reason.strip()
        if self.confirm_result == "false_alarm" and not reason:
            raise ValueError("确认为误报时必须填写误报原因")
        return self


class AlarmResetRequest(BaseModel):
    """FR-016.2 系统复位。physical_restored 是显式的人工确认位。"""

    physical_restored: bool = Field(..., description="已确认设备物理状态恢复正常")
    remark: str | None = Field(None, max_length=255)


DEVICE_STATUS_PATTERN = r"^(normal|alarm|fault|shield|offline|retired)$"


class DeviceReportRequest(BaseModel):
    """设备上报（模拟器 / 网关 / 后续 MQTT 适配层共用）"""

    device_id: int | None = None
    device_code: str | None = Field(None, max_length=100)
    status: str = Field("normal", pattern=DEVICE_STATUS_PATTERN)
    alarm_type: str | None = Field(None, pattern=ALARM_TYPE_PATTERN)
    location_description: str | None = Field(None, max_length=255)
    is_drill: bool = False
    reported_at: datetime | None = None

    @model_validator(mode="after")
    def _require_identifier(self):
        if self.device_id is None and not self.device_code:
            raise ValueError("device_id 与 device_code 至少提供一个")
        return self


class DeviceReportOut(BaseModel):
    """上报处理结果，便于网关侧核对状态迁移与报警去重命中情况"""

    device_id: int
    device_code: str
    old_status: str | None = None
    status: str
    status_changed: bool
    alarm_id: int | None = None
    alarm_created: bool = False


class DashboardOut(BaseModel):
    """FR-014 监控大屏总览"""

    total: int = 0
    online: int = 0
    offline: int = 0
    alarm: int = 0
    fault: int = 0
    shield: int = 0
    retired: int = 0
    normal: int = 0
    pending_alarm: int = 0
    pending_fire: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)


class MapMetaOut(BaseModel):
    """FR-015 平面图元数据"""

    org_id: int
    org_name: str | None = None
    resolved_org_id: int | None = None
    resolved_org_name: str | None = None
    map_image_url: str | None = None
    map_image_width: int | None = None
    map_image_height: int | None = None
    map_origin: str | None = "top_left"


class MapDeviceOut(BaseModel):
    """地图点位（仅渲染所需字段，减少大屏传输量）"""

    id: int
    device_code: str
    device_name: str
    status: str
    org_id: int | None = None
    type_name: str | None = None
    category: str | None = None
    map_x: float | None = None
    map_y: float | None = None
    has_active_alarm: bool = False
    alarm_type: str | None = None
    # 网格聚合桶内的实际设备数；普通点位恒为 1
    count: int = 1

    @field_validator("map_x", "map_y", mode="before")
    @classmethod
    def _decimal_to_float(cls, v):
        return float(v) if v is not None else None


class MapDevicesOut(BaseModel):
    """视口懒加载响应（FR-015 性能优化）"""

    items: list[MapDeviceOut]
    total: int
    aggregated: bool = False
    bbox: list[float] | None = None
    limit: int = 500


class WsTicketOut(BaseModel):
    """WS 握手一次性 Ticket"""

    ticket: str
    expires_in: int
    ws_path: str = "/ws/devices"
