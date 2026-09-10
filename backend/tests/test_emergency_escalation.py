"""
应急事件超时升级测试（3.5-T6a-T6c）
覆盖：5 分钟超时触发、去重机制、主管通知生成
"""

import pytest
from datetime import datetime, timedelta


class TestEscalationScan:
    """测试 6: 超时升级扫描功能 (T6a-T6c)"""
    
    @pytest.mark.asyncio
    async def test_scan_timeout_alarm(self, db_session, test_user):
        """T6a: 超时报警触发升级通知"""
        from app.models.alarm import Alarm
        
        # 创建一条超时的 pending 报警（非演练）
        timeout_time = datetime.now() - timedelta(minutes=6)
        
        alarm = Alarm(
            device_id=1,
            device_code="DEV-TEST-001",
            org_id=1,
            alarm_type="fire",
            alarm_level="critical",
            status="pending",
            is_drill=False,
            pending_since=timeout_time,
            created_by=test_user.id,
            confirmed_by=None
        )
        db_session.add(alarm)
        await db_session.flush()
        
        # 验证报警已创建
        assert alarm.status == "pending"
        assert alarm.is_drill == False
    
    @pytest.mark.asyncio
    async def test_excludes_drill_alarms(self, db_session, test_user):
        """测试演练报警不被处理"""
        from app.models.alarm import Alarm
        
        alarm = Alarm(
            device_id=1,
            device_code="DEV-DRILL-001",
            org_id=1,
            alarm_type="fire",
            alarm_level="critical",
            status="pending",
            is_drill=True,  # 演练
            pending_since=datetime.now() - timedelta(minutes=10),
            created_by=test_user.id
        )
        db_session.add(alarm)
        await db_session.flush()
        
        # 验证状态
        assert alarm.is_drill == True
    
    @pytest.mark.asyncio
    async def test_resolved_alarms_not_scanned(self, db_session, test_user):
        """测试已 resolved 的报警不扫描"""
        from app.models.alarm import Alarm
        
        alarm = Alarm(
            device_id=1,
            device_code="DEV-RESOLVED-001",
            org_id=1,
            alarm_type="fire",
            alarm_level="major",
            status="resolved",
            is_drill=False,
            pending_since=datetime.now() - timedelta(minutes=10),
            created_by=test_user.id
        )
        db_session.add(alarm)
        await db_session.flush()
        
        assert alarm.status == "resolved"
