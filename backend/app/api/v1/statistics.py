"""
统计看板 API（3.9 FR-048 ~ FR-051）
========================================
5 个看板接口 + 公共查询参数。
权限码：statistics:view
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import statistics_service

router = APIRouter()


@router.get("/device-status", response_model=dict)
async def device_status_api(
    org_id: Optional[int] = Query(None, description="区域 ID（下钻）"),
    include_drill: bool = Query(False, description="是否包含演练数据"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("statistics:view")),
):
    """设备完好率看板（FR-048）"""
    data = await statistics_service.get_device_status_distribution(db, org_id=org_id, include_drill=include_drill)
    return {"code": 200, "message": "success", "data": data}


@router.get("/alarm-trend", response_model=dict)
async def alarm_trend_api(
    days: int = Query(7, ge=1, le=365, description="查询天数"),
    org_id: Optional[int] = Query(None, description="区域 ID"),
    include_drill: bool = Query(False, description="是否包含演练数据"),
    start: Optional[date] = Query(None, description="起始日期（优先于 days）"),
    end: Optional[date] = Query(None, description="结束日期（优先于 days）"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("statistics:view")),
):
    """报警趋势图（FR-049）"""
    data = await statistics_service.get_alarm_trend(
        db, days=days, org_id=org_id, include_drill=include_drill, start=start, end=end
    )
    return {"code": 200, "message": "success", "data": data}


@router.get("/fault-top10", response_model=dict)
async def fault_top10_api(
    org_id: Optional[int] = Query(None, description="区域 ID"),
    start: Optional[date] = Query(None, description="起始日期"),
    end: Optional[date] = Query(None, description="结束日期"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("statistics:view")),
):
    """故障 TOP10（FR-050）"""
    data = await statistics_service.get_fault_top10(db, org_id=org_id, start=start, end=end)
    return {"code": 200, "message": "success", "data": data}


@router.get("/inspection-completion", response_model=dict)
async def inspection_completion_api(
    org_id: Optional[int] = Query(None, description="区域 ID"),
    start: Optional[date] = Query(None, description="起始日期"),
    end: Optional[date] = Query(None, description="结束日期"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("statistics:view")),
):
    """巡检完成率（FR-051）"""
    data = await statistics_service.get_inspection_completion(db, org_id=org_id, start=start, end=end)
    return {"code": 200, "message": "success", "data": data}


@router.get("/overview", response_model=dict)
async def overview_api(
    org_id: Optional[int] = Query(None, description="区域 ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("statistics:view")),
):
    """综合概览卡片"""
    data = await statistics_service.get_overview(db, org_id=org_id)
    return {"code": 200, "message": "success", "data": data}
