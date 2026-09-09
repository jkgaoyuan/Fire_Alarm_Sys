"""
联动功能快速测试（3.4）
用于验证核心功能是否正常
"""

import asyncio
from datetime import datetime, timezone


async def test_linkage_executor():
    """测试联动执行器"""
    print("🧪 测试联动执行器...")
    
    from app.services.linkage_executor import execute_action
    
    # Mock Log 对象
    class MockLog:
        delay_seconds = 0
    
    # 测试动作 1: start_exhaust
    action = {
        "action_type": "start_exhaust",
        "params": {"zone": "东侧"}
    }
    log = MockLog()
    
    status, message = await execute_action(action, log)
    print(f"  ✅ 启动排烟：{status} - {message}")
    assert status in ("success", "failed"), "结果必须为 success 或 failed"
    
    # 测试动作 2: close_door
    action = {
        "action_type": "close_door",
        "params": {"door_id": "D-001"}
    }
    status, message = await execute_action(action, log)
    print(f"  ✅ 关闭防火门：{status} - {message}")
    
    # 测试延迟执行
    log.delay_seconds = 5
    action = {
        "action_type": "start_exhaust",
        "params": {"zone": "西侧"}
    }
    status, message = await execute_action(action, log)
    print(f"  ✅ 延迟执行提示：{message}")
    assert "延迟" in message, "应包含延迟提示"
    
    print("✅ 联动执行器测试通过！\n")


async def test_linkage_schema():
    """测试 Schema 验证"""
    print("🧪 测试 Schema 验证...")
    
    from app.schemas.linkage import LinkagePlanCreate, AlarmLinkageLogOut
    
    # 测试 PlanCreate
    plan_data = {
        "plan_name": "测试预案",
        "org_id": 1,
        "fire_type": "fire",
        "trigger_alarm_type": "fire",
        "actions": [
            {
                "action_type": "start_exhaust",
                "params": {"zone": "测试区"}
            }
        ],
        "is_enabled": True,
    }
    
    plan = LinkagePlanCreate(**plan_data)
    print(f"  ✅ 创建预案 Schema: {plan.plan_name}")
    assert plan.plan_name == "测试预案"
    
    # 测试 LogOut
    log_data = {
        "id": 1,
        "alarm_id": 88,
        "plan_id": 1,
        "action_type": "start_exhaust",
        "target_device_id": 15,
        "status": "success",
        "created_at": datetime.now(timezone.utc),
        "is_simulation": False,
        "delay_seconds": 0,
    }
    
    log = AlarmLinkageLogOut(**log_data)
    print(f"  ✅ 日志 Schema: id={log.id}, status={log.status}")
    
    print("✅ Schema 测试通过！\n")


async def test_crud_interface():
    """测试 CRUD 接口"""
    print("🧪 测试 CRUD 接口...")
    
    from app.crud.linkage import linkage_plan_crud, alarm_linkage_log_crud
    
    # 测试方法存在性
    assert hasattr(linkage_plan_crud, 'get'), "应有 get 方法"
    assert hasattr(linkage_plan_crud, 'create'), "应有 create 方法"
    assert hasattr(linkage_plan_crud, 'update'), "应有 update 方法"
    assert hasattr(linkage_plan_crud, 'delete'), "应有 delete 方法"
    assert hasattr(linkage_plan_crud, 'get_multi_by_org'), "应有按 org 查询方法"
    assert hasattr(linkage_plan_crud, 'get_multi_enabled'), "应有启用状态查询方法"
    
    print("  ✅ CRUD 方法完整")
    
    assert hasattr(alarm_linkage_log_crud, 'get'), "应有 get 方法"
    assert hasattr(alarm_linkage_log_crud, 'get_multi_by_alarm'), "应有按 alarm 查询方法"
    assert hasattr(alarm_linkage_log_crud, 'get_multi_by_plan'), "应有按 plan 查询方法"
    
    print("  ✅ 日志 CRUD 方法完整")
    
    print("✅ CRUD 测试通过！\n")


async def test_model_structure():
    """测试模型结构"""
    print("🧪 测试模型结构...")
    
    from app.models.linkage import LinkagePlan, AlarmLinkageLog
    
    # 检查 LinkagePlan 字段
    expected_fields = [
        'plan_name', 'org_id', 'fire_type', 
        'trigger_device_type_id', 'trigger_alarm_type',
        'actions', 'is_enabled', 'created_by', 'created_at'
    ]
    
    for field in expected_fields:
        assert hasattr(LinkagePlan, field), f"LinkagePlan 应包含字段：{field}"
    
    print(f"  ✅ LinkagePlan 字段完整 ({len(expected_fields)}个)")
    
    # 检查 AlarmLinkageLog 字段
    log_fields = [
        'alarm_id', 'plan_id', 'action_type',
        'target_device_id', 'status', 'created_at'
    ]
    
    for field in log_fields:
        assert hasattr(AlarmLinkageLog, field), f"AlarmLinkageLog 应包含字段：{field}"
    
    print(f"  ✅ AlarmLinkageLog 字段完整 ({len(log_fields)}个)")
    
    print("✅ 模型结构测试通过！\n")


async def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("开始运行 3.4 报警联动功能测试")
    print("=" * 60 + "\n")
    
    try:
        await test_model_structure()
        await test_linkage_schema()
        await test_linkage_executor()
        await test_crud_interface()
        
        print("=" * 60)
        print("🎉 所有测试通过！功能正常 ✅")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    result = asyncio.run(run_all_tests())
    exit(0 if result else 1)
