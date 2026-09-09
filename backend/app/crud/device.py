"""
设备档案 CRUD
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.device import Device
from app.schemas.device import DeviceCreate, DeviceUpdate


class DeviceCRUD(CRUDBase[Device, DeviceCreate, DeviceUpdate]):
    """设备档案 CRUD"""

    async def get_by_code(
        self, db: AsyncSession, device_code: str
    ) -> Device | None:
        """按设备编码查询（用于唯一性校验与导入去重）"""
        result = await db.execute(
            select(self.model).where(self.model.device_code == device_code)
        )
        return result.scalar_one_or_none()

    async def get_with_relations(self, db: AsyncSession, device_id: int) -> Device | None:
        """查询设备并预加载类型/区域/创建人，避免 async 下懒加载"""
        result = await db.execute(
            select(Device)
            .options(
                selectinload(Device.device_type),
                selectinload(Device.org),
                selectinload(Device.creator),
            )
            .where(Device.id == device_id)
        )
        return result.scalar_one_or_none()

    async def reload(self, db: AsyncSession, device_id: int) -> Device | None:
        """提交后重新加载关系（写操作返回前调用）"""
        return await self.get_with_relations(db, device_id)

    async def get_codes_in_use(
        self, db: AsyncSession, codes: list[str]
    ) -> set[str]:
        """批量查询已占用的设备编码（导入时一次性查重，避免 N+1）"""
        if not codes:
            return set()
        result = await db.execute(
            select(self.model.device_code).where(self.model.device_code.in_(codes))
        )
        return {row[0] for row in result.all()}


device_crud = DeviceCRUD(Device)
