"""应急事件测试套件（3.5-T1~T8）- 修复版"""

import pytest


class TestEmergencyEventCreation:
    """测试 1: 真实火警自动创建事件（T1-T2）"""

    @pytest.mark.asyncio
    async def test_create_event_on_real_alarm(self, db_session):
        """T1: 确认真实火警时自动生成应急事件"""
        from app.services.emergency_service import create_emergency_event
        from app.models.alarm import Alarm
        
        # 创建测试报警（手动指定 ID 解决 SQLite 自增问题）
        alarm = Alarm(
            id=1000,  # 手动指定 ID，避免 SQLite AUTOINCREMENT 问题
            device_id=1,
            device_code="DEV-001",
            org_id=1,
            alarm_type="fire",
            alarm_level="critical",
            status="pending",
            is_drill=False,
            confirmed_by="admin",
            confirmed_at="2026-09-10T10:00:00"
        )
        db_session.add(alarm)
        await db_session.flush()
        
        event = await create_emergency_event(db_session, alarm.id, 1)
        
        assert event is not None
        assert event.alarm_id == alarm.id
        assert event.event_no.startswith("EV-")
        assert event.status == "processing"
        
        # 验证 timeline 节点已创建
        assert len(event.timelines) >= 2
    
    @pytest.mark.asyncio
    async def test_false_alarm_no_event(self, db_session):
        """T2: 误报不创建事件"""
        from app.services.emergency_service import create_emergency_event
        from app.models.alarm import Alarm
        
        alarm = Alarm(
            id=1001,
            device_id=1,
            device_code="DEV-002",
            org_id=1,
            alarm_type="fire",
            alarm_level="warning",
            status="pending",
            is_drill=False,
            confirmed_by="admin",
            confirmed_at="2026-09-10T10:00:00"
        )
        db_session.add(alarm)
        await db_session.flush()
        
        # 确认结论为误报，不应创建事件
        event = await create_emergency_event(db_session, alarm.id, 1, False)
        assert event is None


class TestEmergencyTimeline:
    """测试 2: 时间轴操作（T4-T5）"""

    @pytest.mark.asyncio
    async def test_add_timeline_node(self, db_session):
        """T4: 添加处置时间轴节点"""
        from app.services.emergency_service import add_timeline_node
        from app.models.alarm import Alarm
        from app.models.emergency import EmergencyEvent
        
        # 准备测试数据
        alarm = Alarm(id=1002, device_id=1, device_code="DEV-003", org_id=1, 
                     alarm_type="fire", alarm_level="critical", status="confirmed")
        db_session.add(alarm)
        await db_session.flush()
        
        event = EmergencyEvent(
            id=2000,
            alarm_id=alarm.id,
            event_no="EV-TEST-001",
            status="processing",
            created_by=1
        )
        db_session.add(event)
        await db_session.flush()
        
        node = await add_timeline_node(db_session, event.id, 1, "field_confirmed")
        
        assert node is not None
        assert node.node_type == "field_confirmed"
    
    @pytest.mark.asyncio
    async def test_cascade_delete_timeline(self, db_session):
        """T5: 删除事件应级联删除时间轴"""
        from app.models.emergency import EmergencyEvent, EmergencyTimeline
        
        event = EmergencyEvent(id=2001, alarm_id=1003, event_no="EV-TEST-002", status="closed", created_by=1)
        db_session.add(event)
        timeline = EmergencyTimeline(id=3000, event_id=event.id, node_type="complete", user_id=1)
        db_session.add(timeline)
        await db_session.flush()
        
        await db_session.delete(event)
        await db_session.commit()
        
        # 验证级联删除
        result = await db_session.execute(db_session.query(EmergencyTimeline).where(EmergencyTimeline.event_id == event.id))
        timelines = result.scalars().all()
        assert len(timelines) == 0


class TestEdgeCases:
    """边缘情况测试"""

    @pytest.mark.asyncio
    async def test_duplicate_alarm_id_no_create(self, db_session):
        """重复报警 ID 不应创建新事件"""
        from app.services.emergency_service import create_emergency_event
        from app.models.alarm import Alarm
        
        alarm = Alarm(id=1004, device_id=1, device_code="DEV-004", org_id=1, 
                     alarm_type="fire", alarm_level="critical", status="confirmed")
        db_session.add(alarm)
        await db_session.flush()
        
        event1 = await create_emergency_event(db_session, alarm.id, 1)
        event2 = await create_emergency_event(db_session, alarm.id, 1)
        
        assert event2 is None  # 重复报警不应创建
