"""
设备档案相关 Pydantic Schema（3.2）
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 计划 一、设备状态枚举
DEVICE_STATUS_PATTERN = r"^(normal|alarm|fault|shield|offline|retired)$"


class DeviceTypeOut(BaseModel):
    """设备类型输出（含扩展属性模板）"""

    id: int
    type_code: str
    type_name: str
    category: str | None = None
    attribute_schema: dict = {}
    icon_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DeviceBase(BaseModel):
    """设备公共字段"""

    device_name: str = Field(..., min_length=1, max_length=100)
    type_id: int | None = None
    org_id: int | None = None
    manufacturer: str | None = Field(None, max_length=100)
    model: str | None = Field(None, max_length=100)
    brand: str | None = Field(None, max_length=50)
    spec: str | None = Field(None, max_length=100)
    install_date: date | None = None
    warranty_expire_date: date | None = None
    maintain_cycle: int | None = Field(None, ge=0, le=3650)
    map_x: float | None = Field(None, ge=-99999999, le=99999999)
    map_y: float | None = Field(None, ge=-99999999, le=99999999)
    attributes: dict = {}
    remark: str | None = Field(None, max_length=500)

    @field_validator("map_x", "map_y", mode="before")
    @classmethod
    def _decimal_to_float(cls, v):
        """SQLite/PostgreSQL 的 Numeric 返回 Decimal，JSON 序列化需为数值"""
        return float(v) if v is not None else None


class DeviceCreate(DeviceBase):
    """创建设备请求"""

    device_code: str = Field(..., min_length=1, max_length=100)
    status: str = Field("normal", pattern=DEVICE_STATUS_PATTERN)


class DeviceUpdate(BaseModel):
    """更新设备请求（所有字段可选）"""

    device_code: str | None = Field(None, min_length=1, max_length=100)
    device_name: str | None = Field(None, min_length=1, max_length=100)
    type_id: int | None = None
    org_id: int | None = None
    manufacturer: str | None = Field(None, max_length=100)
    model: str | None = Field(None, max_length=100)
    brand: str | None = Field(None, max_length=50)
    spec: str | None = Field(None, max_length=100)
    install_date: date | None = None
    warranty_expire_date: date | None = None
    maintain_cycle: int | None = Field(None, ge=0, le=3650)
    status: str | None = Field(None, pattern=DEVICE_STATUS_PATTERN)
    map_x: float | None = None
    map_y: float | None = None
    attributes: dict | None = None
    remark: str | None = Field(None, max_length=500)

    @field_validator("map_x", "map_y", mode="before")
    @classmethod
    def _decimal_to_float(cls, v):
        return float(v) if v is not None else None


class DeviceRetireRequest(BaseModel):
    """设备退役请求"""

    reason: str | None = Field(None, max_length=255)


class DeviceOut(BaseModel):
    """设备档案输出（含类型与区域展示字段）"""

    id: int
    device_code: str
    device_name: str
    type_id: int | None = None
    type_name: str | None = None
    category: str | None = None
    org_id: int | None = None
    org_name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    brand: str | None = None
    spec: str | None = None
    install_date: date | None = None
    warranty_expire_date: date | None = None
    maintain_cycle: int | None = None
    status: str
    map_x: float | None = None
    map_y: float | None = None
    attributes: dict = {}
    remark: str | None = None
    is_deleted: bool
    created_by: int | None = None
    creator_name: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("map_x", "map_y", mode="before")
    @classmethod
    def _decimal_to_float(cls, v):
        return float(v) if v is not None else None

    model_config = ConfigDict(from_attributes=True)


class DeviceListOut(BaseModel):
    """设备分页列表输出"""

    items: list[DeviceOut]
    total: int
    page: int
    page_size: int


class HistoryItemOut(BaseModel):
    """设备历史记录条目（统一时间轴）"""

    category: str = Field(..., description="记录类别：status_change / alarm / repair / inspection")
    title: str
    detail: str | None = None
    operator: str | None = None
    created_at: datetime


class DeviceHistoryOut(BaseModel):
    """设备历史记录输出

    3.4 巡检与 3.7 维修已接入，四类数据源（状态变更 / 报警 / 巡检 / 维修）全部可聚合，
    原先用于标记「哪些数据源暂缺」的 `unavailable_sources` 字段随之移除。
    """

    device_id: int
    device_code: str
    total: int
    items: list[HistoryItemOut] = []


class TrajectoryPointOut(BaseModel):
    """历史轨迹采样点（device_status_logs 同构，按时间升序）"""

    time: datetime
    old_status: str | None = None
    new_status: str
    status_label: str | None = None
    reason: str | None = None
    operator: str | None = None


class TrajectoryOut(BaseModel):
    """FR-018 历史轨迹查询结果"""

    device_id: int
    device_code: str
    device_name: str
    start: datetime
    end: datetime
    total: int
    page: int
    page_size: int
    items: list[TrajectoryPointOut] = []


class ImportFailureOut(BaseModel):
    """导入失败明细条目"""

    row: int = Field(..., description="Excel 行号（含表头，从 1 开始）")
    device_code: str | None = None
    reason: str


class ImportResultOut(BaseModel):
    """批量导入结果（计划 3.3 响应结构）"""

    total: int
    success: int
    failed: int
    failures: list[ImportFailureOut] = []
    rolled_back: bool = False
    message: str | None = None
