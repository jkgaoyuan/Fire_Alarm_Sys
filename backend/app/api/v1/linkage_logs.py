"""
联动日志 API（3.4-B5）
独立的日志查询和导出功能
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional

from app.core.dependencies import get_db, require_permission
from app.models.linkage import AlarmLinkageLog
from app.crud.linkage import alarm_linkage_log_crud
from app.schemas.linkage import AlarmLinkageLogOut

router = APIRouter(tags=["Linkage Logs"])


@router.get(
    "",
    summary="查询联动日志列表"
)
async def get_alarm_linkage_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    alarm_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    status: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    分页查询联动日志
    支持按 alarm_id、plan_id、status、时间范围筛选
    """
    skip = (page - 1) * page_size
    
    stmt = select(AlarmLinkageLog).order_by(AlarmLinkageLog.created_at.desc())
    
    if alarm_id is not None:
        stmt = stmt.where(AlarmLinkageLog.alarm_id == alarm_id)
    if plan_id is not None:
        stmt = stmt.where(AlarmLinkageLog.plan_id == plan_id)
    if status is not None:
        stmt = stmt.where(AlarmLinkageLog.status == status)
    if start_time is not None:
        stmt = stmt.where(AlarmLinkageLog.created_at >= start_time)
    if end_time is not None:
        stmt = stmt.where(AlarmLinkageLog.created_at <= end_time)
    
    # 总数统计 (SQLAlchemy 2.0 正确语法)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one_or_none()
    
    # 获取数据
    stmt = stmt.offset(skip).limit(page_size)
    results = (await db.execute(stmt)).scalars().all()
    
    items = [AlarmLinkageLogOut.model_validate(log) for log in results]
    
    return {
        "items": items,
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/export",
    summary="导出联动日志",
    dependencies=[Depends(require_permission("linkage:view"))]
)
async def export_alarm_linkage_logs(
    alarm_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    导出联动日志为 CSV
    限制最多 1 万行
    """
    from fastapi.responses import PlainTextResponse

    stmt = select(AlarmLinkageLog)

    if alarm_id is not None:
        stmt = stmt.where(AlarmLinkageLog.alarm_id == alarm_id)
    if plan_id is not None:
        stmt = stmt.where(AlarmLinkageLog.plan_id == plan_id)
    if start_time is not None:
        stmt = stmt.where(AlarmLinkageLog.created_at >= start_time)
    if end_time is not None:
        stmt = stmt.where(AlarmLinkageLog.created_at <= end_time)

    results = (await db.execute(stmt)).scalars().all()

    if len(results) > 10000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="导出行数超过 1 万，请缩小筛选范围"
        )

    # 生成 CSV
    lines = ["id,alarm_id,plan_id,action_type,target_device_id,status,result_message,is_simulation,created_at"]
    for log in results:
        lines.append(
            f"{log.id},{log.alarm_id},{log.plan_id},"
            f"{log.action_type},{log.target_device_id},{log.status},"
            f'"{log.result_message or ""}",{log.is_simulation},{log.created_at}'
        )

    csv_content = "\n".join(lines)
    return PlainTextResponse(csv_content, media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="linkage_logs.csv"'
    })


# 注意：`/{log_id}` 必须注册在 `/export` 之后。
# Starlette 按注册顺序匹配且 `{log_id}` 段无正则约束，
# 若排在前面会把 "export" 当成 log_id 捕获 → 422 int_parsing。
@router.get(
    "/{log_id}",
    summary="获取日志详情",
    dependencies=[Depends(require_permission("linkage:view"))]
)
async def get_alarm_linkage_log_detail(
    log_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取单个日志详情"""
    log = await alarm_linkage_log_crud.get(db, log_id)
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="日志不存在"
        )
    return AlarmLinkageLogOut.model_validate(log)
