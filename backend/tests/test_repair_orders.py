"""
维修工单单元测试（3.7 FR-038 ~ FR-042）
"""

import pytest
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repair import RepairOrder, RepairOrderStatus
from app.models.device import Device
from app.models.user import User
from app.crud.repair import RepairOrderCRUD
from app.schemas.repair import RepairOrderCreate, RepairOrderUpdate


class TestRepairOrderModel:
    """维修工单模型测试"""
    
    @pytest.mark.asyncio
    async def test_create_repair_order(self, db_session: AsyncSession, test_user: User):
        """测试创建维修工单"""
        # 先创建一个测试设备
        from app.models.device import Device
        from app.models.device_type import DeviceType
        device_type = DeviceType(
            type_code="test_smoke",
            type_name="测试烟感",
            category="detector",
            attribute_schema={},
        )
        db_session.add(device_type)
        await db_session.flush()
        
        test_device = Device(
            device_code="TEST001",
            device_name="测试设备",
            type_id=device_type.id,
            status="normal",
        )
        db_session.add(test_device)
        await db_session.commit()
        
        crud = RepairOrderCRUD(db_session)
        
        order_in = RepairOrderCreate(
            device_id=test_device.id,
            fault_desc="测试故障描述",
        )
        
        order = await crud.create(order_in, created_by=test_user.id)
        
        assert order.id is not None
        assert order.order_no.startswith("RO-")
        assert order.device_id == test_device.id
        assert order.fault_desc == "测试故障描述"
        assert order.status == RepairOrderStatus.pending
        assert order.created_by == test_user.id
    
    @pytest.mark.asyncio
    async def test_get_repair_order(self, db_session: AsyncSession):
        """测试获取单个维修工单"""
        # 占位测试
        pass
    
    @pytest.mark.asyncio
    async def test_list_repair_orders(self, db_session: AsyncSession):
        """测试获取维修工单列表"""
        # 占位测试
        pass
    
    @pytest.mark.asyncio
    async def test_list_repair_orders_with_filters(self, db_session: AsyncSession):
        """测试带筛选条件的维修工单列表"""
        # 占位测试
        pass


class TestRepairOrderStatusFlow:
    """维修工单状态流转测试"""
    
    @pytest.mark.asyncio
    async def test_assign_repair_order(self, db: AsyncSession, test_repair_order: RepairOrder, test_user: User):
        """测试派单"""
        crud = RepairOrderCRUD(db)
        
        order = await crud.assign(test_repair_order.id, test_user.id)
        
        assert order.status == RepairOrderStatus.assigned
        assert order.repairer_id == test_user.id
        assert order.assigned_at is not None
    
    @pytest.mark.asyncio
    async def test_assign_non_pending_order_fails(self, db: AsyncSession, test_repair_order: RepairOrder, test_user: User):
        """测试非待处理工单派单失败"""
        crud = RepairOrderCRUD(db)
        
        # 先派单
        await crud.assign(test_repair_order.id, test_user.id)
        
        # 再次派单应该失败
        with pytest.raises(ValueError, match="只能派单待处理工单"):
            await crud.assign(test_repair_order.id, test_user.id)
    
    @pytest.mark.asyncio
    async def test_complete_repair_order(self, db: AsyncSession, test_repair_order: RepairOrder, test_user: User):
        """测试完成维修"""
        crud = RepairOrderCRUD(db)
        
        # 先派单
        await crud.assign(test_repair_order.id, test_user.id)
        # 更新状态为维修中
        test_repair_order.status = RepairOrderStatus.repairing
        await db.commit()
        
        # 完成维修
        order = await crud.complete(test_repair_order.id, "更换烟感探测器 X1")
        
        assert order.status == RepairOrderStatus.pending_accept
        assert order.repair_result == "更换烟感探测器 X1"
        assert order.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_accept_repair_order(self, db: AsyncSession, test_repair_order: RepairOrder, test_user: User):
        """测试验收通过"""
        crud = RepairOrderCRUD(db)
        
        # 设置状态为待验收
        test_repair_order.status = RepairOrderStatus.pending_accept
        await db.commit()
        
        # 验收通过
        order = await crud.accept(test_repair_order.id, test_user.id)
        
        assert order.status == RepairOrderStatus.completed
        assert order.acceptor_id == test_user.id
        assert order.accepted_at is not None
        
        # 验证设备状态已恢复为正常
        device = await db.get(Device, test_repair_order.device_id)
        assert device.status == "normal"
    
    @pytest.mark.asyncio
    async def test_return_repair_order(self, db: AsyncSession, test_repair_order: RepairOrder, test_user: User):
        """测试验收退回"""
        crud = RepairOrderCRUD(db)
        
        # 设置状态为待验收
        test_repair_order.status = RepairOrderStatus.pending_accept
        await db.commit()
        
        # 验收退回
        order = await crud.return_order(test_repair_order.id, "维修不彻底", test_user.id)
        
        assert order.status == RepairOrderStatus.returned
        assert order.return_reason == "维修不彻底"
        assert order.acceptor_id == test_user.id


class TestInspectionAutoCreateRepair:
    """巡检异常自动创建维修工单测试"""
    
    @pytest.mark.asyncio
    async def test_auto_create_repair_from_inspection(self, db: AsyncSession, test_device: Device, test_user: User):
        """测试巡检异常自动创建维修工单"""
        from app.services.inspection_service import submit_inspection_record
        from app.models.inspection import InspectionTask, InspectionPlan
        
        # 创建巡检计划和任务
        plan = InspectionPlan(
            plan_name="测试巡检计划",
            cycle_type="daily",
            is_enabled=True,
        )
        db.add(plan)
        await db.flush()
        
        task = InspectionTask(
            plan_id=plan.id,
            task_date=datetime.now().date(),
            responsible_user_id=test_user.id,
            status="pending",
        )
        db.add(task)
        await db.flush()
        
        # 提交异常巡检记录
        record = await submit_inspection_record(
            db=db,
            task_id=task.id,
            device_id=test_device.id,
            result="abnormal",
            abnormal_desc="设备故障测试",
            inspected_by=test_user.id,
        )
        
        # 验证自动创建了维修工单
        crud = RepairOrderCRUD(db)
        repair_order = await crud.get_by_inspection_record(record.id)
        
        assert repair_order is not None
        assert repair_order.inspection_record_id == record.id
        assert repair_order.device_id == test_device.id
        assert repair_order.fault_desc == "设备故障测试"
        assert repair_order.status == RepairOrderStatus.pending
    
    @pytest.mark.asyncio
    async def test_no_duplicate_repair_order(self, db: AsyncSession, test_device: Device, test_user: User):
        """测试避免重复创建维修工单（幂等性）"""
        from app.services.inspection_service import submit_inspection_record
        from app.models.inspection import InspectionTask, InspectionPlan
        
        # 创建巡检计划和任务
        plan = InspectionPlan(
            plan_name="测试巡检计划 2",
            cycle_type="daily",
            is_enabled=True,
        )
        db.add(plan)
        await db.flush()
        
        task = InspectionTask(
            plan_id=plan.id,
            task_date=datetime.now().date(),
            responsible_user_id=test_user.id,
            status="pending",
        )
        db.add(task)
        await db.flush()
        
        # 提交异常巡检记录
        record = await submit_inspection_record(
            db=db,
            task_id=task.id,
            device_id=test_device.id,
            result="abnormal",
            abnormal_desc="设备故障测试",
            inspected_by=test_user.id,
        )
        
        # 再次提交相同巡检记录（模拟重复调用）
        record2 = await submit_inspection_record(
            db=db,
            task_id=task.id,
            device_id=test_device.id,
            result="abnormal",
            abnormal_desc="设备故障测试",
            inspected_by=test_user.id,
        )
        
        # 验证只创建了一个维修工单
        crud = RepairOrderCRUD(db)
        orders, total = await crud.get_multi(inspection_record_id=record.id)
        
        assert total == 1  # 只有一个工单关联到该巡检记录


class TestRepairOrderPermissions:
    """维修工单权限测试"""
    
    @pytest.mark.asyncio
    async def test_only_chief_can_accept(self, db: AsyncSession, test_repair_order: RepairOrder):
        """测试仅消防主管可验收"""
        # 这个测试需要在 API 层进行，这里只是占位
        pass
    
    @pytest.mark.asyncio
    async def test_only_repairer_can_complete(self, db: AsyncSession, test_repair_order: RepairOrder):
        """测试仅维修人员可完成维修"""
        # 这个测试需要在 API 层进行，这里只是占位
        pass
