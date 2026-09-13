"""
维修工单 Pydantic schemas（请求/响应模型）
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ==================== 基础 Schema ====================

class RepairOrderBase(BaseModel):
    """维修工单基础字段"""
    device_id: int = Field(..., description="关联设备 ID")
    alarm_id: Optional[int] = Field(None, description="关联告警 ID")
    inspection_record_id: Optional[int] = Field(None, description="关联巡检记录 ID")
    fault_desc: str = Field(..., description="故障描述")
    repair_result: Optional[str] = Field(None, description="维修结果（含配件明细）")
    return_reason: Optional[str] = Field(None, description="退回原因")


# ==================== 创建 Schema ====================

class RepairOrderCreate(RepairOrderBase):
    """创建维修工单请求"""
    pass


# ==================== 更新 Schema ====================

class RepairOrderUpdate(BaseModel):
    """更新维修工单请求"""
    fault_desc: Optional[str] = None
    repair_result: Optional[str] = None
    return_reason: Optional[str] = None


# ==================== 派单 Schema ====================

class RepairOrderAssign(BaseModel):
    """派单请求"""
    repairer_id: int = Field(..., description="维修人员 ID")


# ==================== 完成维修 Schema ====================

class RepairOrderComplete(BaseModel):
    """完成维修请求"""
    repair_result: str = Field(..., description="维修结果（含配件明细）")


# ==================== 验收退回 Schema ====================

class RepairOrderReturn(BaseModel):
    """验收退回请求"""
    return_reason: str = Field(..., description="退回原因")


# ==================== 响应 Schema ====================

class RepairOrderResponse(RepairOrderBase):
    """维修工单响应"""
    id: int
    order_no: str
    status: str
    reporter_id: Optional[int] = None
    repairer_id: Optional[int] = None
    acceptor_id: Optional[int] = None
    assigned_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    created_by: Optional[int] = None
    
    # 关联信息（可选，需要时通过 joinedload 加载）
    device_name: Optional[str] = None
    device_code: Optional[str] = None
    reporter_name: Optional[str] = None
    repairer_name: Optional[str] = None
    acceptor_name: Optional[str] = None
    
    class Config:
        from_attributes = True


# ==================== 列表响应 Schema ====================

class RepairOrderListResponse(BaseModel):
    """维修工单列表响应"""
    items: List[RepairOrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================== 统计响应 Schema ====================

class AvgRepairDurationResponse(BaseModel):
    """平均维修时长响应"""
    avg_hours: float = Field(..., description="平均维修时长（小时）")


class RepairOverviewStatusItem(BaseModel):
    """工单状态分布项"""
    status: str = Field(..., description="工单状态")
    count: int = Field(..., description="该状态工单数")


class RepairOverviewResponse(BaseModel):
    """
    维修概览统计响应。

    端点此前直接 return 裸 dict，连 response_model 都没有；
    补上模型后 OpenAPI 才有真实 schema，信封也能按类型校验。
    """

    avg_repair_hours: float = Field(..., description="平均维修时长（小时）")
    total_orders: int = Field(..., description="工单总数")
    status_distribution: List[RepairOverviewStatusItem] = Field(
        default_factory=list, description="工单状态分布"
    )


class FaultDistributionItem(BaseModel):
    """故障类型分布项"""
    type: str = Field(..., description="设备类型")
    count: int = Field(..., description="工单数量")


class FaultDistributionResponse(BaseModel):
    """故障类型分布响应"""
    items: List[FaultDistributionItem]


class WorkloadItem(BaseModel):
    """维修人员工作量项"""
    name: str = Field(..., description="维修人员姓名")
    total: int = Field(..., description="总工单数")
    completed: int = Field(..., description="已完成工单数")


class WorkloadResponse(BaseModel):
    """维修人员工作量响应"""
    items: List[WorkloadItem]


class Top10FaultDeviceItem(BaseModel):
    """故障设备 TOP10 项"""
    device_code: str = Field(..., description="设备编码")
    device_name: str = Field(..., description="设备名称")
    type_name: str = Field(..., description="设备类型")
    fault_count: int = Field(..., description="故障次数")


class Top10FaultDevicesResponse(BaseModel):
    """故障设备 TOP10 响应"""
    items: List[Top10FaultDeviceItem]
