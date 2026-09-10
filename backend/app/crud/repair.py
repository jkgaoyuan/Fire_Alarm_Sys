"""
维修工单 CRUD 操作
"""

from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.repair import RepairOrder
from app.models.device import Device
from app.models.user import User
from app.schemas.repair import RepairOrderCreate, RepairOrderUpdate


class RepairOrderCRUD:
    """维修工单 CRUD 操作类"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create(self, obj_in: RepairOrderCreate, created_by: Optional[int] = None) -> RepairOrder:
        """创建维修工单"""
        # 生成工单编号
        order_no = await self._generate_order_no()
        
        db_obj = RepairOrder(
            order_no=order_no,
            device_id=obj_in.device_id,
            alarm_id=obj_in.alarm_id,
            inspection_record_id=obj_in.inspection_record_id,
            fault_desc=obj_in.fault_desc,
            status="pending",
            reporter_id=created_by,
            created_by=created_by
        )
        
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        
        return db_obj
    
    async def get(self, id: int) -> Optional[RepairOrder]:
        """获取单个维修工单（含关联信息）"""
        query = (
            select(RepairOrder)
            .options(
                selectinload(RepairOrder.device),
                selectinload(RepairOrder.reporter),
                selectinload(RepairOrder.repairer),
                selectinload(RepairOrder.acceptor),
            )
            .where(RepairOrder.id == id)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        device_id: Optional[int] = None,
        repairer_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[List[RepairOrder], int]:
        """获取维修工单列表（分页 + 筛选）"""
        # 构建查询条件
        conditions = []
        if status:
            conditions.append(RepairOrder.status == status)
        if device_id:
            conditions.append(RepairOrder.device_id == device_id)
        if repairer_id:
            conditions.append(RepairOrder.repairer_id == repairer_id)
        if start_date:
            conditions.append(RepairOrder.created_at >= start_date)
        if end_date:
            conditions.append(RepairOrder.created_at <= end_date)
        
        where_clause = and_(*conditions) if conditions else True
        
        # 查询总数
        count_query = select(func.count(RepairOrder.id)).where(where_clause)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 查询列表
        list_query = (
            select(RepairOrder)
            .options(
                selectinload(RepairOrder.device),
                selectinload(RepairOrder.reporter),
                selectinload(RepairOrder.repairer),
                selectinload(RepairOrder.acceptor),
            )
            .where(where_clause)
            .order_by(desc(RepairOrder.created_at))
            .offset(skip)
            .limit(limit)
        )
        list_result = await self.db.execute(list_query)
        items = list_result.scalars().all()
        
        return items, total
    
    async def update(self, id: int, obj_in: RepairOrderUpdate) -> Optional[RepairOrder]:
        """更新维修工单"""
        db_obj = await self.get(id)
        if not db_obj:
            return None
        
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db_obj.updated_at = datetime.now()
        await self.db.commit()
        await self.db.refresh(db_obj)
        
        return db_obj
    
    async def assign(self, id: int, repairer_id: int) -> Optional[RepairOrder]:
        """派单"""
        db_obj = await self.get(id)
        if not db_obj:
            return None
        
        if db_obj.status != "pending":
            raise ValueError("只能派单待处理工单")
        
        db_obj.repairer_id = repairer_id
        db_obj.status = "assigned"
        db_obj.assigned_at = datetime.now()
        db_obj.updated_at = datetime.now()
        
        await self.db.commit()
        await self.db.refresh(db_obj)
        
        return db_obj
    
    async def complete(self, id: int, repair_result: str) -> Optional[RepairOrder]:
        """完成维修"""
        db_obj = await self.get(id)
        if not db_obj:
            return None
        
        if db_obj.status != "repairing":
            raise ValueError("只能完成维修中的工单")
        
        db_obj.repair_result = repair_result
        db_obj.status = "pending_accept"
        db_obj.completed_at = datetime.now()
        db_obj.updated_at = datetime.now()
        
        await self.db.commit()
        await self.db.refresh(db_obj)
        
        return db_obj
    
    async def accept(self, id: int, acceptor_id: int) -> Optional[RepairOrder]:
        """验收通过"""
        db_obj = await self.get(id)
        if not db_obj:
            return None
        
        if db_obj.status != "pending_accept":
            raise ValueError("只能验收待验收工单")
        
        db_obj.acceptor_id = acceptor_id
        db_obj.status = "completed"
        db_obj.accepted_at = datetime.now()
        db_obj.updated_at = datetime.now()
        
        # 恢复设备状态
        await self._update_device_status(db_obj.device_id, "normal")
        
        await self.db.commit()
        await self.db.refresh(db_obj)
        
        return db_obj
    
    async def return_order(self, id: int, return_reason: str, acceptor_id: int) -> Optional[RepairOrder]:
        """验收退回"""
        db_obj = await self.get(id)
        if not db_obj:
            return None
        
        if db_obj.status != "pending_accept":
            raise ValueError("只能退回待验收工单")
        
        db_obj.return_reason = return_reason
        db_obj.status = "returned"
        db_obj.acceptor_id = acceptor_id
        db_obj.updated_at = datetime.now()
        
        await self.db.commit()
        await self.db.refresh(db_obj)
        
        return db_obj
    
    async def _generate_order_no(self) -> str:
        """生成工单编号：RO-YYYYMMDD-XXX"""
        today = datetime.now().strftime("%Y%m%d")
        prefix = f"RO-{today}-"
        
        # 查询今天已创建的工单数量
        query = select(func.count(RepairOrder.id)).where(
            RepairOrder.order_no.like(f"{prefix}%")
        )
        result = await self.db.execute(query)
        count = result.scalar() or 0
        
        return f"{prefix}{str(count + 1).zfill(3)}"
    
    async def _update_device_status(self, device_id: int, status: str):
        """更新设备状态"""
        query = select(Device).where(Device.id == device_id)
        result = await self.db.execute(query)
        device = result.scalar_one_or_none()
        
        if device:
            device.status = status
            device.updated_at = datetime.now()
            await self.db.commit()
    
    async def get_by_inspection_record(self, inspection_record_id: int) -> Optional[RepairOrder]:
        """根据巡检记录 ID 获取工单（用于幂等性检查）"""
        query = select(RepairOrder).where(
            RepairOrder.inspection_record_id == inspection_record_id
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
