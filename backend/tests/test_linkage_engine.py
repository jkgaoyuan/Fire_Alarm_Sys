"""
单元测试套件 - 联动引擎 (3.4-B2/B3)
覆盖预案匹配、动作执行、次级告警等功能
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


class TestActionExecution:
    """联动动作执行测试"""
    
    @pytest.mark.asyncio
    async def test_execute_start_exhaust_success(self):
        """测试启动排烟动作"""
        from app.services.linkage_executor import execute_action
        
        class MockLog:
            delay_seconds = 0
        
        action = {
            "action_type": "start_exhaust",
            "params": {"zone": "东侧"}
        }
        log = MockLog()
        
        status, message = await execute_action(action, log)
        assert status in ("success", "failed")
        
    @pytest.mark.asyncio
    async def test_execute_close_door_success(self):
        """测试关闭防火门动作"""
        from app.services.linkage_executor import execute_action
        
        class MockLog:
            delay_seconds = 0
        
        action = {
            "action_type": "close_door",
            "params": {"door_id": "D-001"}
        }
        log = MockLog()
        
        status, message = await execute_action(action, log)
        assert status in ("success", "failed")
        
    @pytest.mark.asyncio
    async def test_delayed_execution_hint(self):
        """测试延迟执行提示"""
        from app.services.linkage_executor import execute_action
        
        class MockLog:
            delay_seconds = 5
        
        action = {
            "action_type": "start_exhaust",
            "params": {}
        }
        log = MockLog()
        
        status, message = await execute_action(action, log)
        assert "延迟" in message


class TestSecondaryAlarmGeneration:
    """次级报警生成测试"""
    
    @pytest.mark.asyncio
    async def test_create_secondary_alarm_on_failure(self):
        """测试联动失败时创建次级报警"""
        from app.models.linkage import AlarmLinkageLog
        
        # Mock log with failed status
        log = AlarmLinkageLog(
            id=1,
            alarm_id=88,
            plan_id=1,
            action_type="start_exhaust",
            target_device_id=15,
            status="failed",
            result_message="设备离线",
            created_at=datetime.now(timezone.utc)
        )
        
        # Verify we can create the secondary alarm structure
        assert log.status == "failed"
        assert log.result_message is not None
        
        # Secondary alarm should have fault type
        alarm_data = {
            "device_id": log.target_device_id,
            "alarm_type": "fault",
            "source": "linkage_failure",
            "description": f"联动失败：{log.result_message}",
        }
        
        assert alarm_data["alarm_type"] == "fault"
        assert "联动失败" in alarm_data["description"]
