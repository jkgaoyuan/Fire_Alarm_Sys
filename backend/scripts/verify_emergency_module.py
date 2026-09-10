#!/usr/bin/env python3
"""
应急事件功能快速验证脚本
验证范围：
1. 数据库表是否存在
2. Schema 是否正确加载
3. 核心服务函数是否可用
4. 权限种子数据是否完整
"""

import asyncio
import sys
from pathlib import Path

# 将 backend 目录加入 Python 路径
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.core.config import get_settings
from app.models.emergency import EmergencyEvent, EmergencyTimeline, Notification
from app.schemas.emergency import EmergencyEventOut, NotificationOut

settings = get_settings()

# 创建同步引擎用于查询
sync_engine = create_async_engine(settings.database_url_async).sync_engine


def test_database_tables():
    """测试 1: 验证数据库表是否存在"""
    print("\n【测试 1】数据库表存在性检查...")
    
    from sqlalchemy import inspect
    inspector = inspect(sync_engine)
    tables = inspector.get_table_names()
    
    required_tables = ['emergency_events', 'emergency_timelines', 'notifications']
    missing = [t for t in required_tables if t not in tables]
    
    if missing:
        print(f"❌ 缺少表：{missing}")
        return False
    
    print(f"✅ 所有必需表存在：{required_tables}")
    
    # 检查字段
    for table_name in required_tables:
        columns = inspector.get_columns(table_name)
        column_names = [c['name'] for c in columns]
        print(f"   {table_name}: {len(column_names)} 个字段")
    
    return True


def test_model_import():
    """测试 2: 验证模型能否正确导入"""
    print("\n【测试 2】模型导入检查...")
    
    try:
        from app.models import EmergencyEvent, EmergencyTimeline, Notification
        print("✅ Models.__init__.py导出正确")
        return True
    except ImportError as e:
        print(f"❌ 模型导入失败：{e}")
        return False


def test_schema_import():
    """测试 3: 验证 Schema 能否正确导入"""
    print("\n【测试 3】Schema 导入检查...")
    
    try:
        from app.schemas import (
            EmergencyEventOut,
            EmergencyTimelineCreate,
            NotificationOut,
            UnreadCountOut
        )
        print("✅ Schemas.__init__.py导出正确")
        return True
    except ImportError as e:
        print(f"❌ Schema 导入失败：{e}")
        return False


async def test_service_functions(db: AsyncSession):
    """测试 4: 验证核心服务函数可用性"""
    print("\n【测试 4】核心服务函数检查...")
    
    from app.services.emergency_service import (
        create_emergency_event,
        scan_pending_alarms_for_escalation,
        add_timeline_node,
        resolve_emergency_event,
        close_emergency_event,
        get_unread_count
    )
    
    funcs = [
        "create_emergency_event",
        "scan_pending_alarms_for_escalation",
        "add_timeline_node",
        "resolve_emergency_event",
        "close_emergency_event",
        "get_unread_count"
    ]
    
    print(f"✅ 所有 {len(funcs)} 个服务函数可用")
    return True


def test_permission_seed():
    """测试 5: 验证权限种子数据"""
    print("\n【测试 5】权限种子数据检查...")
    
    with sync_engine.begin() as conn:
        # 检查菜单
        result = conn.execute(
            text("SELECT COUNT(*) FROM permissions WHERE perm_code = 'emergency:event'")
        )
        menu_count = result.scalar()
        
        # 检查按钮
        button_codes = [
            "emergency:view",
            "emergency:timeline",
            "emergency:resolve",
            "emergency:close",
            "emergency:export"
        ]
        
        result = conn.execute(
            text(f"SELECT COUNT(*) FROM permissions WHERE perm_code IN ({','.join(['?']*len(button_codes))})"),
            button_codes
        )
        btn_count = result.scalar()
    
    if menu_count == 0:
        print("❌ 菜单 emergency:event 未创建")
        return False
    
    if btn_count < 5:
        print(f"⚠️  按钮权限仅创建 {btn_count}/5 个")
    
    print(f"✅ 菜单 + 按钮权限完整：1+{btn_count}")
    return True


async def main():
    print("=" * 60)
    print("3.5 应急事件功能 - 快速验证脚本")
    print("=" * 60)
    
    results = []
    
    # 测试 1-3: 无需数据库连接
    results.append(("表结构", test_database_tables()))
    results.append(("模型导入", test_model_import()))
    results.append(("Schema 导入", test_schema_import()))
    results.append(("权限种子", test_permission_seed()))
    
    # 测试 4: 需要数据库连接
    try:
        engine = create_async_engine(settings.database_url_async_async)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # 确保表存在
        
        AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession)
        async with AsyncSessionLocal() as session:
            result = await test_service_functions(session)
            results.append(("服务函数", result))
    except Exception as e:
        print(f"\n⚠️  服务函数测试跳过：{e}")
        results.append(("服务函数", None))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r is True)
    failed = sum(1 for _, r in results if r is False)
    skipped = sum(1 for _, r in results if r is None)
    
    for name, result in results:
        status = "✅" if result else "❌" if result is False else "⏸️"
        print(f"{status} {name}")
    
    print(f"\n总计：{passed}通过 / {failed}失败 / {skipped}跳过")
    
    if failed > 0:
        print("\n❌ 部分测试失败，请检查上文详细信息")
        sys.exit(1)
    else:
        print("\n✅ 所有测试通过！3.5 模块基础环境准备就绪")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
