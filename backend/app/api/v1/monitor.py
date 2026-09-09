"""
实时监控 API（3.3 B-13 / B-14 / B-15）

大屏统计、TopN 报警、地图点位、WS 握手 Ticket、设备上报（受开关保护）。
"""

from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import require_permission
from app.core.exceptions import AuthError, NotFoundError
from app.db.redis import get_redis_pool
from app.db.session import get_db
from app.models.user import User
from app.schemas.alarm import DeviceReportOut, DeviceReportRequest, WsTicketOut
from app.services import alarm_service, device_report_service, monitor_service
from app.ws.auth import issue_ticket

settings = get_settings()

router = APIRouter()

RedisDep = Annotated[aioredis.Redis, Depends(get_redis_pool)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
MonitorUser = Annotated[User, Depends(require_permission("monitor:view"))]


def verify_device_key(x_device_key: str | None) -> None:
    """校验设备侧预共享凭据；服务端未配置 DEVICE_REPORT_KEY 时一律拒绝"""
    expected = settings.DEVICE_REPORT_KEY
    if not expected or x_device_key != expected:
        raise AuthError(401, "设备凭据无效或未配置 DEVICE_REPORT_KEY")


@router.get("/dashboard", response_model=dict)
async def get_dashboard(
    db: DbDep,
    user: MonitorUser,
    org_id: int | None = Query(None, description="区域下钻，含其全部子区域"),
):
    """FR-014 监控大屏统计卡片"""
    data = await monitor_service.get_dashboard(db, user, org_id)
    return {"code": 200, "message": "success", "data": data.model_dump()}


@router.get("/alarms/recent", response_model=dict)
async def get_recent_alarms(
    db: DbDep,
    user: MonitorUser,
    limit: int = Query(20, ge=1, le=100),
    org_id: int | None = Query(None),
    include_drill: bool = Query(False),
):
    """
    FR-014 大屏报警 TopN。
    排序：未确认火警强制置顶，其余按报警时间倒序（计划 5.1）。
    """
    alarms = await monitor_service.get_recent_alarms(
        db, user, limit=limit, org_id=org_id, include_drill=include_drill
    )
    return {
        "code": 200,
        "message": "success",
        "data": [alarm_service.alarm_payload(a) for a in alarms],
    }


@router.get("/map", response_model=dict)
async def get_map_meta(
    db: DbDep,
    user: MonitorUser,
    org_id: int = Query(..., description="定位到的楼层/区域节点"),
):
    """FR-015 平面图元数据（自动向上继承最近持有平面图的楼层）"""
    meta = await monitor_service.get_map_meta(db, user, org_id)
    if meta is None:
        return {"code": 404, "message": "区域不存在或无权访问", "data": None}
    return {"code": 200, "message": "success", "data": meta.model_dump()}


@router.get("/map/devices", response_model=dict)
async def get_map_devices(
    db: DbDep,
    user: MonitorUser,
    org_id: int | None = Query(None),
    bbox: str | None = Query(None, description="xmin,ymin,xmax,ymax（原图像素坐标）"),
    limit: int = Query(monitor_service.MAP_RENDER_LIMIT, ge=1, le=2000),
):
    """FR-015 视口内设备点位；超过 limit 时返回网格聚合桶"""
    data = await monitor_service.get_map_devices(
        db, user, org_id=org_id, bbox=monitor_service.parse_bbox(bbox), limit=limit
    )
    return {"code": 200, "message": "success", "data": data.model_dump()}


@router.post("/ws-ticket", response_model=dict)
async def create_ws_ticket(redis: RedisDep, user: MonitorUser):
    """
    FR-013 WS 握手 Ticket。

    浏览器 WebSocket 无法自定义请求头，故用一次性短时效 ticket 替代 Bearer（计划 3.3）。
    """
    ticket = await issue_ticket(redis, user.id)
    data = WsTicketOut(ticket=ticket, expires_in=settings.WS_TICKET_TTL_SECONDS)
    return {"code": 200, "message": "success", "data": data.model_dump()}


@router.post("/report", response_model=dict)
async def report_device(
    db: DbDep,
    redis: RedisDep,
    payload: DeviceReportRequest,
    x_device_key: Annotated[str | None, Header(alias="X-Device-Key")] = None,
):
    """
    设备状态上报（模拟器 / 网关）。

    凭据为预共享 X-Device-Key，不使用用户 JWT，因此不走 require_permission；
    生产默认关闭（ALLOW_DEVICE_REPORT=false 且 DEBUG=false → 视为端点不存在）。
    """
    if not (settings.ALLOW_DEVICE_REPORT or settings.DEBUG):
        raise NotFoundError("设备上报端点未启用")
    verify_device_key(x_device_key)

    result = await device_report_service.handle_device_report(db, redis, payload)
    return {
        "code": 200,
        "message": "success",
        "data": DeviceReportOut.model_validate(result).model_dump(),
    }
