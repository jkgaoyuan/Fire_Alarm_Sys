"""
报警记录 CRUD（3.3 B-12）
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.crud.base import CRUDBase
from app.models.alarm import OPEN_ALARM_STATUSES, Alarm


class AlarmCRUD(CRUDBase[Alarm, dict, dict]):
    """报警档案 CRUD

    报警不走 Pydantic Create schema——写入字段必须来自设备快照与报警类型策略，
    由 alarm_service 组装后直接构造 ORM 对象，因此泛型参数用 dict。
    """

    def with_relations(self) -> Select:
        """预加载设备/区域/处置人的基础查询，供 service 层叠加筛选与分页"""
        return select(Alarm).options(
            selectinload(Alarm.device),
            selectinload(Alarm.org),
            selectinload(Alarm.confirmer),
            selectinload(Alarm.creator),
        )

    async def get_with_relations(self, db: AsyncSession, alarm_id: int) -> Alarm | None:
        """查询报警并预加载设备/区域/处置人，避免 async 下懒加载"""
        result = await db.execute(self.with_relations().where(Alarm.id == alarm_id))
        return result.scalar_one_or_none()

    async def reload(self, db: AsyncSession, alarm_id: int) -> Alarm | None:
        """提交后重新加载关系（写操作返回前调用）"""
        return await self.get_with_relations(db, alarm_id)

    async def find_open(
        self, db: AsyncSession, device_id: int, alarm_type: str
    ) -> Alarm | None:
        """
        查找同设备同类型的未收敛报警（报警风暴去重依据）。
        只取最新一条，历史已收敛记录不参与去重。
        """
        result = await db.execute(
            select(Alarm)
            .where(
                Alarm.device_id == device_id,
                Alarm.alarm_type == alarm_type,
                Alarm.status.in_(OPEN_ALARM_STATUSES),
            )
            .order_by(Alarm.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_active_by_device_ids(
        self, db: AsyncSession, device_ids: list[int]
    ) -> dict[int, str]:
        """批量取设备的活动报警类型，供地图点位着色（避免 N+1）"""
        if not device_ids:
            return {}
        result = await db.execute(
            select(Alarm.device_id, Alarm.alarm_type)
            .where(
                Alarm.device_id.in_(device_ids),
                Alarm.status.in_(OPEN_ALARM_STATUSES),
            )
            .order_by(Alarm.device_id, Alarm.id.desc())
        )
        active: dict[int, str] = {}
        for device_id, alarm_type in result.all():
            active.setdefault(device_id, alarm_type)
        return active


alarm_crud = AlarmCRUD(Alarm)
