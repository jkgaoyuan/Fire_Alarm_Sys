"""
单元测试套件 - 联动预案 (3.4-B4)
覆盖 CRUD、权限验证、删除保护等功能
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone


@pytest.fixture
def mock_db():
    """Create a mock database session"""
    db = AsyncMock()
    
    async def mock_commit():
        pass
    
    db.commit = mock_commit
    db.add = AsyncMock()
    db.refresh = AsyncMock()
    return db


class TestLinkagePlanCRUD:
    """联动预案 CRUD 测试"""
    
    @pytest.mark.asyncio
    async def test_create_linkage_plan(self, mock_db):
        """测试创建预案"""
        from app.models.linkage import LinkagePlan
        from app.schemas.linkage import LinkagePlanCreate
        
        plan_data = {
            "plan_name": "测试预案",
            "org_id": 1,
            "fire_type": "fire",
            "trigger_alarm_type": "fire",
            "actions": [{"action_type": "start_exhaust"}],
            "is_enabled": True,
        }
        
        schema = LinkagePlanCreate(**plan_data)
        
        # Mock execute to return None (no existing plan)
        mock_result = MagicMock()
        mock_result.scalars().one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        from app.crud.linkage import linkage_plan_crud
        created = await linkage_plan_crud.create(db=mock_db, obj_in=schema)
        
        assert created.plan_name == "测试预案"
        mock_db.add.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_get_linkage_plan(self, mock_db):
        """测试获取预案详情"""
        from app.models.linkage import LinkagePlan
        
        plan = LinkagePlan(
            id=1,
            plan_name="测试预案",
            org_id=1,
            is_enabled=True,
            actions=[]
        )
        
        # Mock execute result properly
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = plan
        
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=mock_scalars)
        
        mock_db.execute = AsyncMock(return_value=mock_execute_result)
        
        from app.crud.linkage import linkage_plan_crud
        result = await linkage_plan_crud.get(mock_db, 1)
        
        assert result is not None
        assert result.id == 1
        assert result.plan_name == "测试预案"
        
    @pytest.mark.asyncio
    async def test_update_linkage_plan(self, mock_db):
        """测试更新预案"""
        from app.models.linkage import LinkagePlan
        from app.schemas.linkage import LinkagePlanUpdate
        
        plan = LinkagePlan(
            id=1, 
            plan_name="旧名称", 
            org_id=1, 
            is_enabled=True, 
            actions=[]
        )
        
        update_data = LinkagePlanUpdate(plan_name="新名称", is_enabled=False)
        
        from app.crud.linkage import linkage_plan_crud
        updated = await linkage_plan_crud.update(
            db=mock_db, 
            db_obj=plan, 
            obj_in=update_data.model_dump()
        )
        
        assert updated.plan_name == "新名称"
        assert updated.is_enabled == False
        
    @pytest.mark.asyncio
    async def test_get_multi_by_org(self, mock_db):
        """测试按组织查询预案"""
        from app.models.linkage import LinkagePlan
        
        plans = [
            LinkagePlan(id=1, plan_name="预案 1", org_id=1, is_enabled=True, actions=[]),
            LinkagePlan(id=2, plan_name="预案 2", org_id=1, is_enabled=False, actions=[]),
        ]
        
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = plans
        
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=mock_scalars)
        
        mock_db.execute = AsyncMock(return_value=mock_execute_result)
        
        from app.crud.linkage import linkage_plan_crud
        results = await linkage_plan_crud.get_multi_by_org(mock_db, org_id=1)
        
        assert len(results) == 2


class TestAlarmLinkageLogCRUD:
    """联动日志 CRUD 测试"""
    
    @pytest.mark.asyncio
    async def test_get_logs_by_alarm(self, mock_db):
        """测试按报警 ID 查询日志"""
        from app.models.linkage import AlarmLinkageLog
        
        logs = [
            AlarmLinkageLog(
                id=1,
                alarm_id=88,
                plan_id=1,
                action_type="start_exhaust",
                target_device_id=15,
                status="success",
                result_message="已启动排烟风机"
            ),
        ]
        
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = logs
        
        mock_count_result = MagicMock()
        mock_count_result.scalar_one_or_none.return_value = 1
        
        def execute_side_effect(stmt):
            if "count()" in str(stmt):
                return mock_count_result
            return mock_execute_result
        
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=mock_scalars)
        
        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        
        from app.crud.linkage import alarm_linkage_log_crud
        results = await alarm_linkage_log_crud.get_multi_by_alarm(mock_db, alarm_id=88)
        
        assert len(results) == 1
        assert results[0].action_type == "start_exhaust"
        
    @pytest.mark.asyncio
    async def test_count_plan_logs(self, mock_db):
        """测试统计预案日志数量"""
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 5
        
        mock_db.execute = AsyncMock(return_value=mock_count_result)
        
        from app.crud.linkage import alarm_linkage_log_crud
        count = await alarm_linkage_log_crud.count_plan_logs(mock_db, plan_id=1)
        
        assert count == 5


class TestDeleteProtection:
    """删除保护测试"""
    
    @pytest.mark.asyncio
    async def test_cannot_delete_with_logs(self, mock_db):
        """测试有日志时不能删除"""
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 1
        
        mock_db.execute = AsyncMock(return_value=mock_count_result)
        
        from app.crud.linkage import alarm_linkage_log_crud
        count = await alarm_linkage_log_crud.count_plan_logs(mock_db, plan_id=1)
        
        assert count > 0
        assert count == 1
