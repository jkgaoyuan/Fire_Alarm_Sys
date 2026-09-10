"""
巡检模块 CRUD 操作（3.6 FR-032 ~ FR-037）
==========================================
对应模型：InspectionPlan, InspectionTask, InspectionRecord
遵循项目 CRUD 规范：继承 CRUDBase，提供分页与筛选方法
"""

from datetime import date, datetime
from typing import Optional, TypeVar
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.inspection import (
    InspectionPlan,
    InspectionTask,
    InspectionRecord,
)
from app.schemas.inspection import (
    InspectionPlanCreate,
    InspectionPlanUpdate,
)

# ==================== InspectionPlan CRUD ====================

ModelType = TypeVar("ModelType", bound=InspectionPlan)
CreateSchemaType = TypeVar("CreateSchemaType", bound=InspectionPlanCreate)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=InspectionPlanUpdate)


class InspectionPlanCRUD(CRUDBase[InspectionPlan, InspectionPlanCreate, InspectionPlanUpdate]):
    """巡检计划 CRUD 操作"""

    async def get_multi_by_org(
        self,
        db: AsyncSession,
        *,
        org_id: int,
        skip: int = 0,
        limit: int = 100,
        is_enabled: Optional[bool] = None,
    ) -> list[InspectionPlan]:
        """按区域获取巡检计划列表"""
        stmt = select(self.model).where(self.model.org_id == org_id)
        if is_enabled is not None:
            stmt = stmt.where(self.model.is_enabled == is_enabled)
        
        result = await db.execute(stmt.offset(skip).limit(limit))
        return list(result.scalars().all())

    async def get_multi_by_responsible_user(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[InspectionPlan]:
        """按责任人获取巡检计划列表"""
        stmt = (
            select(self.model)
            .where(self.model.responsible_user_id == user_id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_stats_by_plan(
        self,
        db: AsyncSession,
        *,
        plan_id: int,
    ) -> dict:
        """统计某计划的任务数（总/已完成/漏检）"""
        # 总数
        total_stmt = select(func.count()).select_from(InspectionTask).where(InspectionTask.plan_id == plan_id)
        total = (await db.execute(total_stmt)).scalar_one() or 0
        
        # 已完成
        completed_stmt = select(func.count()).select_from(InspectionTask).where(
            InspectionTask.plan_id == plan_id,
            InspectionTask.status == "completed"
        )
        completed = (await db.execute(completed_stmt)).scalar_one() or 0
        
        # 漏检
        missed_stmt = select(func.count()).select_from(InspectionTask).where(
            InspectionTask.plan_id == plan_id,
            InspectionTask.status == "missed"
        )
        missed = (await db.execute(missed_stmt)).scalar_one() or 0
        
        completion_rate = completed / total if total > 0 else 0.0
        
        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "missed_tasks": missed,
            "completion_rate": round(completion_rate, 4),
        }


# ==================== InspectionTask CRUD ====================

class InspectionTaskCRUD(CRUDBase):
    """巡检任务 CRUD 操作（无 Create/Update Schema）"""

    async def get_multi_by_date_range(
        self,
        db: AsyncSession,
        *,
        start_date: date,
        end_date: date,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        responsible_user_id: Optional[int] = None,
    ) -> list[InspectionTask]:
        """按日期范围获取任务列表"""
        stmt = select(self.model).where(
            self.model.task_date >= start_date,
            self.model.task_date <= end_date,
        )
        if status:
            stmt = stmt.where(self.model.status == status)
        if responsible_user_id:
            stmt = stmt.where(self.model.responsible_user_id == responsible_user_id)
        
        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_by_plan_and_date(
        self,
        db: AsyncSession,
        *,
        plan_id: int,
        task_date: date,
    ) -> Optional[InspectionTask]:
        """检查某计划在某一天的任务是否已生成"""
        stmt = (
            select(self.model)
            .where(
                self.model.plan_id == plan_id,
                self.model.task_date == task_date,
            )
            .options(selectinload(self.model.records))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status_to_completed(
        self,
        db: AsyncSession,
        *,
        task_id: int,
        completed_at: Optional[datetime] = None,
    ) -> Optional[InspectionTask]:
        """更新任务状态为已完成"""
        stmt = (
            select(self.model)
            .where(self.model.id == task_id)
            .options(selectinload(self.model.records))
        )
        task = (await db.execute(stmt)).scalar_one_or_none()
        if task:
            task.status = "completed"
            if not completed_at:
                completed_at = datetime.now()
            task.completed_at = completed_at
            db.add(task)
            await db.flush()
        return task

    async def mark_as_missed(
        self,
        db: AsyncSession,
        *,
        task_id: int,
    ) -> Optional[InspectionTask]:
        """标记任务为漏检"""
        stmt = select(self.model).where(self.model.id == task_id)
        task = (await db.execute(stmt)).scalar_one_or_none()
        if task:
            task.status = "missed"
            db.add(task)
            await db.flush()
        return task

    async def count_pending_tasks(
        self,
        db: AsyncSession,
        *,
        due_date: date,
    ) -> int:
        """统计指定日期的待执行任务数"""
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(
                self.model.task_date == due_date,
                self.model.status.in_(["pending", "doing"]),
            )
        )
        result = (await db.execute(stmt)).scalar_one()
        return result or 0

    async def count_missed_tasks(
        self,
        db: AsyncSession,
        *,
        before_date: date,
    ) -> int:
        """统计截止某日期的漏检任务总数"""
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(
                self.model.task_date < before_date,
                self.model.status == "missed",
            )
        )
        result = (await db.execute(stmt)).scalar_one()
        return result or 0


# ==================== InspectionRecord CRUD ====================

class InspectionRecordCRUD(CRUDBase):
    """巡检记录 CRUD 操作（无 Create/Update Schema）"""

    async def get_multi_by_task(
        self,
        db: AsyncSession,
        *,
        task_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[InspectionRecord]:
        """按任务 ID 获取记录列表"""
        stmt = (
            select(self.model)
            .where(self.model.task_id == task_id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_multi_by_device(
        self,
        db: AsyncSession,
        *,
        device_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[InspectionRecord]:
        """按设备 ID 获取记录列表"""
        stmt = (
            select(self.model)
            .where(self.model.device_id == device_id)
            .order_by(self.model.inspected_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_multi_by_user_created(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[InspectionRecord]:
        """按创建人获取记录列表（DEC-004）"""
        stmt = (
            select(self.model)
            .where(self.model.created_by == user_id)
            .order_by(self.model.inspected_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_multi_by_date_range(
        self,
        db: AsyncSession,
        *,
        start_date: date,
        end_date: date,
        skip: int = 0,
        limit: int = 100,
    ) -> list[InspectionRecord]:
        """按日期范围获取记录列表"""
        stmt = (
            select(self.model)
            .where(
                self.model.inspected_at >= datetime.combine(start_date, datetime.min.time().replace(tzinfo=None)),
                self.model.inspected_at <= datetime.combine(end_date, datetime.max.time()),
            )
            .order_by(self.model.inspected_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def create_with_user_tracking(
        self,
        db: AsyncSession,
        *,
        data: dict,
        created_by: int,
    ) -> InspectionRecord:
        """创建巡检记录并自动设置 created_by（DEC-004）"""
        data["created_by"] = created_by
        if "inspected_by" not in data:
            data["inspected_by"] = created_by
        return super().create(db=db, data=data)

    async def count_by_result(
        self,
        db: AsyncSession,
        *,
        device_id: int,
        result: str,
    ) -> int:
        """统计某设备的特定结果巡检次数"""
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(
                self.model.device_id == device_id,
                self.model.result == result,
            )
        )
        result = (await db.execute(stmt)).scalar_one()
        return result or 0


# Create CRUD instances
inspection_plan_crud = InspectionPlanCRUD(InspectionPlan)
inspection_task_crud = InspectionTaskCRUD(InspectionTask)
inspection_record_crud = InspectionRecordCRUD(InspectionRecord)
