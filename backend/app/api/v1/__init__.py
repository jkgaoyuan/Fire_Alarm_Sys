"""
API v1 路由聚合
"""

from fastapi import APIRouter

from app.api.v1 import (
    alarms,
    auth,
    devices,
    login_logs,
    monitor,
    organizations,
    permissions,
    roles,
    users,
    linkage_plans,
    linkage_logs,
    repair,
)
from app.api.v1.emergency_events import router as emergency_router
from app.api.v1.notifications import router as notification_router
from app.api.v1 import inspection

router = APIRouter()

# 注册认证路由
router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 注册用户路由
router.include_router(users.router, prefix="/users", tags=["用户"])

# 注册权限路由
router.include_router(permissions.router, prefix="/permissions", tags=["权限"])

# 注册角色路由
router.include_router(roles.router, prefix="/roles", tags=["角色"])

# 注册登录日志路由（P1-003：审计查询）
router.include_router(login_logs.router, prefix="/login-logs", tags=["登录日志"])

# 注册组织架构路由（3.2 区域选择器前置依赖）
router.include_router(organizations.router, prefix="/organizations", tags=["组织架构"])

# 注册设备类型路由（供设备档案下拉框与动态表单使用）
router.include_router(devices.type_router, prefix="/device-types", tags=["设备类型"])

# 注册设备档案路由
router.include_router(devices.router, prefix="/devices", tags=["设备档案"])

# 注册实时监控路由（3.3：大屏统计、地图点位、WS Ticket、设备上报）
router.include_router(monitor.router, prefix="/monitor", tags=["实时监控"])

# 注册报警中心路由（3.3：查询、确认、消音、复位）
router.include_router(alarms.router, prefix="/alarms", tags=["报警中心"])

# Register linkage plans router (3.4)
router.include_router(linkage_plans.router, prefix="/linkage-plans", tags=["Linkage Plans"])

# Register linkage logs router (3.4)
router.include_router(linkage_logs.router, prefix="/alarm-linkage-logs", tags=["Linkage Logs"])

# 3.5 应急事件路由
router.include_router(emergency_router, prefix="/emergency-events", tags=["应急处置"])

# 3.5 通知中心路由（与应急事件关联）
router.include_router(notification_router, prefix="/notifications", tags=["通知中心"])

# 3.6 巡检管理路由
router.include_router(inspection.router, tags=["设备巡检"])

# 3.7 维修工单管理路由
router.include_router(repair.router, tags=["维修工单"])
