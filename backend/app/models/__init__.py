"""
模型导出入口
"""

from app.models.alarm import Alarm
from app.models.device import Device, DeviceStatusLog
from app.models.device_type import DeviceType
from app.models.drill import DrillEvent, DrillEvaluation
from app.models.emergency import EmergencyEvent, EmergencyTimeline, Notification
from app.models.inspection import (
    InspectionPlan,
    InspectionTask,
    InspectionRecord,
)
from app.models.organization import Organization
from app.models.permission import Permission
from app.models.repair import RepairOrder
from app.models.report_export import ReportExportTask
from app.models.user import LoginLog, Role, User

__all__ = [
    "Organization",
    "Permission",
    "User",
    "Role",
    "LoginLog",
    "DeviceType",
    "Device",
    "DeviceStatusLog",
    "Alarm",
    "EmergencyEvent",
    "EmergencyTimeline",
    "Notification",
    # 3.6 巡检模块新增
    "InspectionPlan",
    "InspectionTask",
    "InspectionRecord",
    # 3.7 维修工单新增
    "RepairOrder",
    # 3.8 消防演练新增
    "DrillEvent",
    "DrillEvaluation",
    # 3.9 统计报表新增
    "ReportExportTask",
]
