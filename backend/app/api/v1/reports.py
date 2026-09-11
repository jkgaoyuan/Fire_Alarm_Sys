"""
报表导出 API（3.9 FR-052）
========================================
4 个导出相关接口：
- POST /reports/export - 创建导出任务
- GET /reports/export/{task_id}/status - 查询任务状态
- GET /reports/export/{task_id}/download - 下载文件
- GET /reports/export-tasks - 我的导出任务列表
权限码：statistics:export
"""

import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_db
from app.models.report_export import ReportExportTask
from app.models.user import User
from app.schemas.report_export import ExportTaskOut
from app.services.report_export_service import (
    create_export_task,
    execute_export_sync,
    execute_export_async,
)

router = APIRouter()


@router.post("/export", response_model=dict)
async def create_export_api(
    req: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("statistics:export")),
):
    """创建导出任务（Excel/CSV/Word）"""
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    task_type = body.get("task_type")
    if not task_type:
        raise HTTPException(400, "缺少 task_type")

    params = body.get("params", {})
    export_data = body.get("data", [])
    file_format = body.get("format", "xlsx")

    # 创建任务记录
    task = await create_export_task(db, task_type, params, user.id)

    # 根据数据量决定同步/异步
    if len(export_data) > 10000:
        task = await execute_export_async(background_tasks, db, task, export_data, file_format)
    else:
        task = await execute_export_sync(db, task, export_data, file_format)

    return {"code": 200, "message": "success", "data": {"task_id": task.id, "task_no": task.task_no}}


@router.get("/export-tasks", response_model=dict)
async def list_my_tasks_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("statistics:view")),
):
    """查询我的导出任务列表（仅查看自己的任务，DEC-004）"""
    skip = (page - 1) * page_size

    # 计数
    count_stmt = select(func.count(ReportExportTask.id)).where(
        ReportExportTask.created_by == user.id
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    # 查询
    stmt = (
        select(ReportExportTask)
        .where(ReportExportTask.created_by == user.id)
        .order_by(ReportExportTask.created_at.desc())
        .offset(skip)
        .limit(page_size)
    )
    tasks = (await db.execute(stmt)).scalars().all()

    items = [ExportTaskOut.model_validate(task) for task in tasks]

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/export/{task_id}/status", response_model=dict)
async def get_task_status_api(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("statistics:view")),
):
    """查询导出任务状态"""
    task = await db.get(ReportExportTask, task_id)

    if not task or task.created_by != user.id:
        raise HTTPException(status_code=404, detail="任务不存在或无权访问")

    out = ExportTaskOut.model_validate(task)

    return {
        "code": 200,
        "message": "success",
        "data": out.model_dump(),
    }


@router.get("/export/{task_id}/download")
async def download_file_api(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("statistics:export")),
):
    """下载导出文件"""
    task = await db.get(ReportExportTask, task_id)

    if not task:
        raise HTTPException(404, "任务不存在")

    if task.created_by != user.id:
        raise HTTPException(403, "无权下载此文件")

    if task.status != "completed":
        raise HTTPException(400, "任务未完成或已失败")

    if not task.file_path or not os.path.exists(task.file_path):
        raise HTTPException(404, "文件不存在")

    filename = task.file_name or os.path.basename(task.file_path)

    return FileResponse(task.file_path, filename=filename)
