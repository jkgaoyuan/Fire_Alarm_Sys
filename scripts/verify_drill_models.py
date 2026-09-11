"""
验证 3.8 Drill 模型更新是否正确 - 简化版
运行方式：python scripts/verify_drill_models.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


def test_model_import():
    """测试模型导入"""
    print("=" * 60)
    print("测试 1: 模型导入")
    print("=" * 60)
    
    try:
        from app.models import DrillEvent, DrillEvaluation
        print("[OK] DrillEvent 导入成功")
        print("[OK] DrillEvaluation 导入成功")
        return True
    except ImportError as e:
        print(f"[FAIL] 导入失败：{e}")
        return False


def test_drill_event_structure():
    """测试 DrillEvent 结构"""
    print("\n" + "=" * 60)
    print("测试 2: DrillEvent 结构")
    print("=" * 60)
    
    from app.models import DrillEvent
    
    required_fields = [
        'id', 'drill_name', 'drill_type', 'planned_at', 
        'actual_start_at', 'actual_end_at', 'location', 
        'participants', 'status', 'summary', 'photos', 'videos',
        'created_by', 'created_at', 'updated_at'
    ]
    
    missing_fields = []
    for field in required_fields:
        if not hasattr(DrillEvent, field):
            missing_fields.append(field)
    
    if missing_fields:
        print(f"[FAIL] 缺失字段：{missing_fields}")
        return False
    else:
        print("[OK] 所有必要字段存在")
    
    # 检查冗余字段是否被移除
    if hasattr(DrillEvent, 'is_drill_data'):
        print("[FAIL] is_drill_data 字段应被移除但仍然存在")
        return False
    else:
        print("[OK] is_drill_data 字段已成功移除")
    
    return True


def test_drill_evaluation_structure():
    """测试 DrillEvaluation 结构"""
    print("\n" + "=" * 60)
    print("测试 3: DrillEvaluation 结构")
    print("=" * 60)
    
    from app.models import DrillEvaluation
    
    required_fields = [
        'id', 'drill_id', 'evaluator_id', 'evaluated_at',
        'items', 'total_score', 'problems', 'improvements',
        'evaluation_summary', 'created_at', 'updated_at'
    ]
    
    missing_fields = []
    for field in required_fields:
        if not hasattr(DrillEvaluation, field):
            missing_fields.append(field)
    
    if missing_fields:
        print(f"[FAIL] 缺失字段：{missing_fields}")
        return False
    else:
        print("[OK] 所有必要字段存在")
    
    # 检查新增的 evaluation_summary 字段
    if hasattr(DrillEvaluation, 'evaluation_summary'):
        print("[OK] evaluation_summary 字段已正确添加（OQ-4 决策）")
    else:
        print("[FAIL] evaluation_summary 字段缺失")
        return False
    
    return True


def test_relationship():
    """测试模型关联关系"""
    print("\n" + "=" * 60)
    print("测试 4: 模型关联关系")
    print("=" * 60)
    
    from app.models import DrillEvent, DrillEvaluation
    
    if hasattr(DrillEvent, 'evaluation') and hasattr(DrillEvaluation, 'drill_event'):
        print("[OK] 双向关联配置正确")
        
        drill_event_rel = DrillEvent.evaluation.property
        if drill_event_rel.cascade:
            print(f"   [OK] 级联策略：{drill_event_rel.cascade}")
        
        return True
    else:
        print("[FAIL] 关联关系配置不完整")
        return False


def test_alembic_migration():
    """检查 Alembic 迁移文件"""
    print("\n" + "=" * 60)
    print("测试 5: Alembic 建表迁移")
    print("=" * 60)
    
    migration_file = Path(__file__).parent.parent / "backend" / "alembic" / "versions" / \
                     "2026_09_11_0000-create_drill_tables.py"
    
    if not migration_file.exists():
        print(f"[FAIL] 迁移文件不存在：{migration_file}")
        return False
    
    print(f"[OK] 迁移文件存在：{migration_file.name}")
    
    content = migration_file.read_text(encoding='utf-8')
    
    checks = [
        ("建表 drill_events", "op.create_table(\n        'drill_events'"),
        ("建表 drill_evaluations", "op.create_table(\n        'drill_evaluations'"),
        ("evaluation_summary 列", "'evaluation_summary'"),
        ("不含 is_drill_data 列", "is_drill_data"),
        ("挂接迁移链 add_inspection_audit", "down_revision: Union[str, None] = 'add_inspection_audit'"),
        ("OQ-4 注释", "OQ-4"),
        ("OQ-6 注释", "OQ-6"),
    ]
    
    all_passed = True
    for name, pattern in checks:
        if name == "不含 is_drill_data 列":
            if pattern in content.replace("no is_drill_data", "").replace("(no is_drill_data column ever existed in any deployed database)", ""):
                print(f"   [FAIL] {name}（迁移中不应出现该列）")
                all_passed = False
            else:
                print(f"   [OK] {name}")
        elif pattern in content:
            print(f"   [OK] {name}")
        else:
            print(f"   [FAIL] {name} 未找到")
            all_passed = False
    
    return all_passed


def main():
    """主测试函数"""
    print("\n开始验证 3.8 Drill 模型更新\n")
    print("版本：v1.0")
    print("目的：验证 OQ-4/OQ-5/OQ-6 补充工作完成质量")
    print("-" * 60)
    
    results = {
        "模型导入": test_model_import(),
        "DrillEvent 结构": test_drill_event_structure(),
        "DrillEvaluation 结构": test_drill_evaluation_structure(),
        "关联关系": test_relationship(),
        "Alembic 迁移": test_alembic_migration(),
    }
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{test_name}: {status}")
    
    print(f"\n总分：{passed}/{total}")
    
    if passed == total:
        print("\n所有测试通过！更新质量符合要求。")
        print("\n建议下一步操作：")
        print("1. cd backend && alembic upgrade head")
        print("2. 在前端 EvaluationForm.vue 中添加 evaluation_summary 字段")
        return 0
    else:
        print("\n部分测试失败，请检查相关问题后重新验证。")
        return 1


if __name__ == "__main__":
    exit(main())
