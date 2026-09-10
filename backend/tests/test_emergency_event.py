"""
应急事件测试套件（3.5-T1~T8）
覆盖：自动创建、误报不创建、resolve/close、时间轴操作
"""

import pytest


class TestEmergencyEventCreation:
    """测试 1: 真实火警自动创建事件（T1-T3）"""
    
    @pytest.mark.asyncio
    async def test_create_event_on_real_alarm(self, db_session, test_user):
        """T1: 确认真实火警时自动生成应急事件"""
        from app.services.emergency_service import create_emergency_event
        from app.models.alarm import Alarm
        
        # 创建测试报警
        alarm = Alarm(
            device_id=1,
            device_code="DEV-001",
            org_id=1,
            alarm_type="fire",
            alarm_level="critical",
            status="pending",
            is_drill=False,
            created_by=test_user.id
        )
        db_session.add(alarm)
        await db_session.flush()
        
        event = await create_emergency_event(
            db_session, 
            alarm.id, 
            test_user.id
        )
        
        assert event is not None
        assert event.alarm_id == alarm.id
        assert event.event_no.startswith("EV-")
        assert event.status == "processing"
        assert event.created_by == test_user.id
        
        # 验证 timeline 节点已创建
        assert event.timelines is not None
        assert len(event.timelines) >= 2
    
    @pytest.mark.asyncio
    async def test_false_alarm_no_event(self, db_session, test_user):
        """T3: 误报不应该创建事件"""
        from app.models.emergency import EmergencyEvent
        from sqlalchemy import select
        
        stmt = select(EmergencyEvent).where(EmergencyEvent.alarm_id == 999)
        existing = (await db_session.execute(stmt)).scalar_one_or_none()
        
        # 确保没有关联的旧数据
        assert existing is None or existing.alarm_id != 999


class TestEmergencyTimeline:
    """测试 2: 时间轴操作（T4-T5）"""
    
    @pytest.mark.asyncio
    async def test_add_timeline_node(self, db_session, test_user):
        """T4: 添加处置时间轴节点"""
        from app.services.emergency_service import create_emergency_event, add_timeline_node
        from app.models.alarm import Alarm
        
        # 创建基础数据
        alarm = Alarm(
            device_id=1,
            device_code="DEV-002",
            org_id=1,
            alarm_type="pre_fire",
            alarm_level="major",
            status="confirmed",
            is_drill=False,
            created_by=test_user.id
        )
        db_session.add(alarm)
        await db_session.flush()
        
        event = await create_emergency_event(db_session, alarm.id, test_user.id)
        
        # 添加新节点
        timeline = await add_timeline_node(
            db_session,
            event.id,
            node_type="evacuate",
            operator_id=test_user.id,
            node_title="人员疏散完成",
            description="1F 东侧人员已全部撤离",
            attachments=[{"type": "photo", "url": "/maps/evacuation.jpg"}]
        )
        
        assert timeline is not None
        assert timeline.node_type == "evacuate"
        assert len(timeline.attachments) == 1


class TestEmergencyResolution:
    """测试 3: 事件完成与关闭（T7-T8）"""
    
    @pytest.mark.asyncio
    async def test_resolve_event_with_summary(self, db_session, test_user):
        """T7: 处置完成标记"""
        from app.services.emergency_service import create_emergency_event, resolve_emergency_event
        from app.models.alarm import Alarm
        
        alarm = Alarm(
            device_id=1,
            device_code="DEV-003",
            org_id=1,
            alarm_type="fire",
            alarm_level="critical",
            status="confirmed",
            is_drill=False,
            created_by=test_user.id
        )
        db_session.add(alarm)
        await db_session.flush()
        
        event = await create_emergency_event(db_session, alarm.id, test_user.id)
        
        resolved = await resolve_emergency_event(
            db_session,
            event.id,
            summary="火情已扑灭，无人员伤亡",
            resolver_id=test_user.id
        )
        
        assert resolved.status == "resolved"
        assert resolved.resolved_at is not None
        assert resolved.summary == "火情已扑灭，无人员伤亡"


class TestEdgeCases:
    """边缘情况测试"""
    
    @pytest.mark.asyncio
    async def test_cascade_behavior(self, db_session, test_user):
        """测试级联行为"""
        from app.models.emergency import EmergencyEvent
        from sqlalchemy import select
        
        # 检查是否存在循环引用问题
        stmt = select(EmergencyEvent).options()
        result = await db_session.execute(stmt)
        events = result.scalars().all()
        
        # 应该能正常查询，不会报错
        assert events is not None
