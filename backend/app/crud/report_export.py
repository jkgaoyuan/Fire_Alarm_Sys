"""
报表导出任务 CRUD（3.9）
"""

from typing import Optional, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.report_export import ReportExportTask
from app.schemas.report_export import ExportTaskCreate


class CRUDReportExportTask(CRUDBase[ReportExportTask, ExportTaskCreate, None]):
    """导出任务 CRUD"""

    async def get_multi(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        created_by: Optional[int] = None,
    ) -> Tuple[List[ReportExportTask], int]:
        """分页查询我的导出任务（仅查看自己的）"""
        stmt = select(ReportExportTask)
        if created_by:
            stmt = stmt.where(ReportExportTask.created_by == created_by)

        count_stmt = select(func.count(ReportExportTask.id)).select_from(
            stmt.subquery()
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(ReportExportTask.created_at.desc()).offset(skip).limit(limit)
        results = (await db.execute(stmt)).scalars().all()
        return results, total


report_export_crud = CRUDReportExportTask(ReportExportTask)
