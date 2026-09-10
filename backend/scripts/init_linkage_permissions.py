"""
快速权限初始化脚本 (3.4-报警联动)
专门用于初始化联动相关的 6 个权限代码
适用于 PowerShell + GBK 编码环境
"""

import asyncio
import sys
from pathlib import Path

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import and_, select
from app.core.config import get_settings

settings = get_settings()
from app.models import Permission, Role
from app.models.base import role_permissions


async def init_linkage_permissions():
    """初始化 3.4-报警联动功能的权限"""
    
    # 连接数据库
    engine = create_async_engine(
        settings.database_url_async,
        echo=False,
        future=True,
    )
    
    async with async_engine.begin() as conn:
        from app.models.base import Base
        await conn.run_sync(Base.metadata.create_all)
    
    print("=" * 60)
    print("开始初始化权限数据...")
    print("=" * 60)
    
    async with AsyncSessionLocal() as session:
        # 1. 查找消防主管角色
        chief_role_stmt = select(Role).filter_by(role_code="chief")
        chief_role = (await session.execute(chief_role_stmt)).scalar_one_or_none()
        
        if not chief_role:
            print("[ERROR] 未找到消防主管角色")
            return False
        
        # 2. 定义需要创建的 6 个权限
        linkage_permissions_data = [
            {
                "perm_name": "联动预案创建",
                "perm_code": "linkage:create",
                "sort_order": 10,
            },
            {
                "perm_name": "联动预案查看",
                "perm_code": "linkage:read",
                "sort_order": 11,
            },
            {
                "perm_name": "联动预案编辑",
                "perm_code": "linkage:update",
                "sort_order": 12,
            },
            {
                "perm_name": "联动预案删除",
                "perm_code": "linkage:delete",
                "sort_order": 13,
            },
            {
                "perm_name": "联动预案模拟",
                "perm_code": "linkage:simulate",
                "sort_order": 14,
            },
            {
                "perm_name": "手动执行联动",
                "perm_code": "execute:manual",
                "sort_order": 15,
            },
        ]
        
        created_count = 0
        existing_count = 0
        
        for perm_data in linkage_permissions_data:
            # 检查权限是否已存在
            stmt = select(Permission).filter_by(perm_code=perm_data["perm_code"])
            existing_perm = (await session.execute(stmt)).scalar_one_or_none()
            
            if existing_perm:
                print(f"[OK] 权限已存在：{perm_data['perm_code']}")
                existing_count += 1
                continue
            
            # 创建新权限
            new_perm = Permission(
                perm_name=perm_data["perm_name"],
                perm_code=perm_data["perm_code"],
                sort_order=perm_data["sort_order"],
            )
            
            session.add(new_perm)
            await session.flush()
            
            print(f"[OK] 创建新权限：{perm_data['perm_code']} (ID={new_perm.id})")
            created_count += 1
        
        # 3. 绑定到消防主管角色
        perm_codes = [p["perm_code"] for p in linkage_permissions_data]
        stmt = select(Permission).filter(and_(Permission.perm_code.in_(perm_codes)))
        permissions = (await session.execute(stmt)).scalars().all()
        
        # 使用原生 SQL 插入绑定关系
        for perm in permissions:
            from sqlalchemy import text
            bind_sql = text("INSERT INTO role_permissions (role_id, perm_id) VALUES (:role_id, :perm_id)")
            await session.execute(bind_sql, {"role_id": chief_role.id, "perm_id": perm.id})
            print(f"[OK] 绑定权限到消防主管：{perm.perm_code}")
        
        await session.commit()
        
        # 打印总结
        print("\n" + "=" * 60)
        print("初始化完成!")
        print(f"  - 新建权限：{created_count} 个")
        print(f"  - 已有权限：{existing_count} 个")
        print(f"  - 总权限数：{len(chief_role.permissions)} 个")
        print("=" * 60)
        
        # 验证消防主管的权限
        stmt = select(Role).options(joinedload(Role.permissions))
        updated_role = (await session.execute(stmt.filter(Role.id == chief_role.id))).scalar_one()
        
        print("\n消防主管当前所有权限:")
        for perm in sorted(updated_role.permissions, key=lambda x: x.perm_code):
            print(f"  [{perm.perm_code}] {perm.perm_name}")
        
        return True


# 导入 AsyncSessionLocal
from app.db.session import AsyncSessionLocal, async_engine
from sqlalchemy.orm import joinedload


if __name__ == "__main__":
    try:
        print(f"[*] 使用数据库：{settings.database_url_async}")
        
        success = asyncio.run(init_linkage_permissions())
        
        if success:
            print("\n成功！您可以开始使用联动功能了。")
        else:
            print("\n初始化失败，请检查错误信息。")
            exit(1)
            
    except Exception as e:
        print(f"\n[ERROR] 初始化失败：{e}")
        import traceback
        traceback.print_exc()
        exit(1)
