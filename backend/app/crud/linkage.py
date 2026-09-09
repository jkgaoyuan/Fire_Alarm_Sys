from typing import Optional, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.linkage import AlarmLinkageLog, LinkagePlan
from app.schemas.linkage import (
    AlarmLinkageLogCreate,
    AlarmLinkageLogUpdate,
    LinkagePlanCreate,
    LinkagePlanUpdate,
)

# Type variables for generics
ModelType = TypeVar("ModelType", bound=LinkagePlan)
CreateSchemaType = TypeVar("CreateSchemaType", bound=LinkagePlanCreate)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=LinkagePlanUpdate)


class LinkagePlanCRUD(
    CRUDBase[LinkagePlan, LinkagePlanCreate, LinkagePlanUpdate]
):
    """
    CRUD operations for LinkagePlan model.
    """

    async def get_multi_by_org(
        self, db: AsyncSession, *, org_id: int, skip: int = 0, limit: int = 100
    ) -> list[LinkagePlan]:
        """
        Get multiple linkage plans by organization ID.
        """
        stmt = (
            select(self.model)
            .where(self.model.org_id == org_id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_multi_enabled(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> list[LinkagePlan]:
        """
        Get multiple enabled linkage plans.
        """
        stmt = (
            select(self.model)
            .where(self.model.is_enabled.is_(True))
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


# Type variables for generics
ModelType2 = TypeVar("ModelType2", bound=AlarmLinkageLog)
CreateSchemaType2 = TypeVar("CreateSchemaType2", bound=AlarmLinkageLogCreate)
UpdateSchemaType2 = TypeVar("UpdateSchemaType2", bound=AlarmLinkageLogUpdate)


class AlarmLinkageLogCRUD(
    CRUDBase[AlarmLinkageLog, AlarmLinkageLogCreate, AlarmLinkageLogUpdate]
):
    """
    CRUD operations for AlarmLinkageLog model.
    """

    async def get_multi_by_alarm(
        self, db: AsyncSession, *, alarm_id: int, skip: int = 0, limit: int = 100
    ) -> list[AlarmLinkageLog]:
        """
        Get multiple linkage logs by alarm ID.
        """
        stmt = (
            select(self.model)
            .where(self.model.alarm_id == alarm_id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_multi_by_plan(
        self, db: AsyncSession, *, plan_id: int, skip: int = 0, limit: int = 100
    ) -> list[AlarmLinkageLog]:
        """
        Get multiple linkage logs by plan ID.
        """
        stmt = (
            select(self.model)
            .where(self.model.plan_id == plan_id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_multi_by_status(
        self, db: AsyncSession, *, status: str, skip: int = 0, limit: int = 100
    ) -> list[AlarmLinkageLog]:
        """
        Get multiple linkage logs by status.
        """
        stmt = (
            select(self.model)
            .where(self.model.status == status)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_plan_logs(
        self, db: AsyncSession, plan_id: int
    ) -> int:
        """
        Count logs for a specific plan.
        """
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.plan_id == plan_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one() or 0


# Create CRUD instances
linkage_plan_crud = LinkagePlanCRUD(LinkagePlan)
alarm_linkage_log_crud = AlarmLinkageLogCRUD(AlarmLinkageLog)
