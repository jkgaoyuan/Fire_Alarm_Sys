"""
维修工单 CRUD 操作
"""

from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.repair import REPAIR_ORDER_STATUS_TRANSITIONS, RepairOrder
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
    
    async def get(self, id: int, scope_condition=None) -> Optional[RepairOrder]:
        """
        获取单个维修工单（含关联信息）。

        `scope_condition` 是数据权限范围表达式（见 services/repair_service.py）。
        传入后越权的工单按「不存在」返回 None，调用方据此回 404，不泄露存在性。

        ⚠️ 这里的四个 `selectinload` 不能省：响应构造会访问 `order.device`、
        `order.reporter` 等关系，异步会话下**懒加载会抛 MissingGreenlet**。
        调用方若绕开本方法自己拼 `select(RepairOrder)` 而不带这些 options，
        线上就是 500（2026-09-13 详情接口实际踩过；单测没抓到是因为测试夹具
        与请求共用会话，关系对象已在 identity map 里，压根没触发懒加载）。
        """
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
        if scope_condition is not None:
            query = query.where(scope_condition)
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
        scope_condition=None,
    ) -> Tuple[List[RepairOrder], int]:
        """
        获取维修工单列表（分页 + 筛选）。

        `scope_condition` 是数据权限范围表达式（见 services/repair_service.py），
        由调用方传入。它同时作用于 count 与 items——否则会出现
        「总数 2、只回 1 条」这种分页错位。
        """
        # 构建查询条件
        conditions = []
        if scope_condition is not None:
            conditions.append(scope_condition)
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
    
    async def start(self, id: int) -> Optional[RepairOrder]:
        """
        开始维修：`assigned` / `returned` → `repairing`。

        可转移性查 `REPAIR_ORDER_STATUS_TRANSITIONS` 而不是硬编码状态字符串——
        状态机表是唯一真相源，另写一套判断迟早与它漂移
        （此前 `assigned → repairing`、`returned → repairing` 两条转移在表里
        定义着，却没有任何代码实现，工单卡在「已派单」走不动）。

        归属校验（只有被指派的维修人本人能开始）在端点做，与 `complete` 同口径。
        """
        db_obj = await self.get(id)
        if not db_obj:
            return None

        if "repairing" not in REPAIR_ORDER_STATUS_TRANSITIONS.get(db_obj.status, ()):
            raise ValueError("只能开始已派单或已退回的工单")

        db_obj.status = "repairing"
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

    # ==================== 统计查询 ====================

    async def get_avg_repair_duration(self) -> float:
        """计算平均维修时长（小时），仅统计已完成工单"""
        query = select(
            func.avg(
                func.extract('epoch', RepairOrder.completed_at) -
                func.extract('epoch', RepairOrder.created_at)
            )
        ).where(
            RepairOrder.status == "completed",
            RepairOrder.completed_at.isnot(None),
        )
        result = await self.db.execute(query)
        avg_seconds = result.scalar()
        if avg_seconds is None:
            return 0.0
        return round(avg_seconds / 3600, 1)

    async def get_status_distribution(self) -> list[dict]:
        """获取工单状态分布"""
        query = (
            select(RepairOrder.status, func.count(RepairOrder.id).label('count'))
            .group_by(RepairOrder.status)
        )
        result = await self.db.execute(query)
        return [{"status": row.status, "count": row.count} for row in result.all()]

    async def get_workload_by_repairer(self) -> list[dict]:
        """获取维修人员工作量统计"""
        query = (
            select(
                User.real_name.label('name'),
                func.count(RepairOrder.id).label('total'),
                func.count().filter(RepairOrder.status == 'completed').label('completed'),
            )
            .join(User, RepairOrder.repairer_id == User.id)
            .where(RepairOrder.repairer_id.isnot(None))
            .group_by(User.id, User.real_name)
            .order_by(desc('total'))
        )
        result = await self.db.execute(query)
        return [
            {"name": row.name, "total": row.total, "completed": row.completed}
            for row in result.all()
        ]

    async def get_fault_type_distribution(self) -> list[dict]:
        """获取故障类型分布（按设备类型分组）"""
        from app.models.device_type import DeviceType
        query = (
            select(
                DeviceType.type_name.label('type'),
                func.count(RepairOrder.id).label('count'),
            )
            .join(Device, RepairOrder.device_id == Device.id)
            .join(DeviceType, Device.type_id == DeviceType.id)
            .group_by(DeviceType.id, DeviceType.type_name)
            .order_by(desc('count'))
        )
        result = await self.db.execute(query)
        return [{"type": row.type, "count": row.count} for row in result.all()]

    async def get_top10_fault_devices(self) -> list[dict]:
        """获取故障设备 TOP10"""
        from app.models.device_type import DeviceType
        query = (
            select(
                Device.device_code,
                Device.device_name,
                DeviceType.type_name,
                func.count(RepairOrder.id).label('fault_count'),
            )
            .join(Device, RepairOrder.device_id == Device.id)
            .join(DeviceType, Device.type_id == DeviceType.id)
            .group_by(Device.id, Device.device_code, Device.device_name, DeviceType.type_name)
            .order_by(desc('fault_count'))
            .limit(10)
        )
        result = await self.db.execute(query)
        return [
            {
                "device_code": row.device_code,
                "device_name": row.device_name,
                "type_name": row.type_name,
                "fault_count": row.fault_count,
            }
            for row in result.all()
        ]
