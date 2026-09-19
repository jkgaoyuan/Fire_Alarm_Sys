"""
报警中心 API（3.3 B-15 / B-16）

分页筛选、详情、确认、消音（FR-016.1）、系统复位（FR-016.2）。
所有写操作在事务提交后 XADD 事件，由 WS 扇出到大屏与报警中心。
"""

from datetime import datetime
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.redis import get_redis_pool
from app.db.session import get_db
from app.models.alarm import Alarm
from app.models.user import User
from app.schemas.alarm import (
    AlarmConfirmRequest,
    AlarmListOut,
    AlarmOut,
    AlarmResetRequest,
)
from app.services import alarm_service

router = APIRouter()

RedisDep = Annotated[aioredis.Redis, Depends(get_redis_pool)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=dict)
async def list_alarms(
    db: DbDep,
    user: Annotated[User, Depends(require_permission("alarm:view"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    alarm_type: str | None = Query(None, description="fire/pre_fire/fault/shield"),
    alarm_level: str | None = Query(None, description="critical/major/minor"),
    status: str | None = Query(None, description="状态筛选，多值以逗号分隔"),
    org_id: int | None = Query(None),
    device_id: int | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    include_drill: bool = Query(False),
):
    """FR-016 报警记录分页查询（默认排除演练报警）"""
    alarms, total = await alarm_service.list_alarms(
        db,
        user,
        page=page,
        page_size=page_size,
        alarm_type=alarm_type,
        alarm_level=alarm_level,
        status=status,
        org_id=org_id,
        device_id=device_id,
        start=start,
        end=end,
        include_drill=include_drill,
    )
    return {
        "code": 200,
        "message": "success",
        "data": AlarmListOut(
            items=[alarm_out(a) for a in alarms],
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
    }


@router.get("/{alarm_id}", response_model=dict)
async def get_alarm(
    alarm_id: int,
    db: DbDep,
    user: Annotated[User, Depends(require_permission("alarm:view"))],
):
    """报警详情（越权与不存在统一返回 code=404）"""
    alarm = await alarm_service.get_alarm_for_user(db, alarm_id, user)
    return {"code": 200, "message": "success", "data": alarm_out(alarm)}


@router.post("/{alarm_id}/confirm", response_model=dict)
async def confirm_alarm(
    alarm_id: int,
    payload: AlarmConfirmRequest,
    db: DbDep,
    redis: RedisDep,
    user: Annotated[User, Depends(require_permission("alarm:confirm"))],
):
    """FR-025/FR-026 报警确认；误报必须填写原因"""
    alarm = await alarm_service.confirm_alarm(db, redis, alarm_id, user, payload)
    return {"code": 200, "message": "确认成功", "data": alarm_out(alarm)}


@router.post("/{alarm_id}/silence", response_model=dict)
async def silence_alarm(
    alarm_id: int,
    db: DbDep,
    redis: RedisDep,
    user: Annotated[User, Depends(require_permission("alarm:silence"))],
):
    """
    FR-016.1 单条消音。
    只留痕不改状态，报警仍留在列表中；页面级全局静音是前端本地态（计划 OQ-4）。
    """
    alarm = await alarm_service.silence_alarm(db, redis, alarm_id, user)
    return {"code": 200, "message": "已消音", "data": alarm_out(alarm)}


@router.post("/{alarm_id}/reset", response_model=dict)
async def reset_alarm(
    alarm_id: int,
    payload: AlarmResetRequest,
    db: DbDep,
    redis: RedisDep,
    user: Annotated[User, Depends(require_permission("alarm:reset"))],
):
    """
    FR-016.2 系统复位（计划 5.5 规则）。
    报警置 resolved + 设备回 normal + 状态日志同事务，并广播 alarm_reset / device_status。
    """
    alarm = await alarm_service.reset_alarm(db, redis, alarm_id, user, payload)
    return {"code": 200, "message": "复位成功", "data": alarm_out(alarm)}


def alarm_out(alarm: Alarm) -> dict:
    """
    序列化 = ORM 列 + 设备/区域上下文。

    AlarmOut 里的 device_name/org_name/map_x/map_y 不是 alarms 的列，
    直接 model_validate(orm) 会静默留空，因此显式并入 WS 帧载荷。
    """
    data = alarm.to_dict()
    data.update(alarm_service.alarm_payload(alarm))
    return AlarmOut.model_validate(data).model_dump()
