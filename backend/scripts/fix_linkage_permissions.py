"""
紧急修复脚本 - 将 linkage:view 等权限添加到 admin/chief 角色
"""
import asyncio
import sys
sys.path.append('.')

from sqlalchemy import text
from app.db.session import AsyncSessionLocal


async def fix_permissions():
    """修复权限问题"""
    async with AsyncSessionLocal() as session:
        # 查询 chief role ID
        role_result = await session.execute(
            text("SELECT id FROM roles WHERE role_code = 'chief'")
        )
        chief_role = role_result.fetchone()
        
        if not chief_role:
            print("Chief role not found!")
            return
        
        print(f"Found chief role ID: {chief_role.id}")
        
        # 查询需要绑定的权限 IDs
        perm_result = await session.execute(
            text("""
                SELECT id, perm_code 
                FROM permissions 
                WHERE perm_code IN (
                    'linkage:view', 'linkage:create', 'linkage:update', 
                    'linkage:delete', 'linkage:simulate', 'execute:manual'
                )
            """)
        )
        permissions = perm_result.fetchall()
        
        print(f"\nFound {len(permissions)} permissions:")
        for perm in permissions:
            print(f"  - {perm.perm_code} (ID: {perm.id})")
        
        # 批量绑定权限到角色
        for perm in permissions:
            result = await session.execute(
                text("""
                    INSERT INTO role_permissions (role_id, perm_id)
                    VALUES (:role_id, :perm_id)
                    ON CONFLICT DO NOTHING
                """),
                {"role_id": chief_role.id, "perm_id": perm.id}
            )
            
            if result.rowcount > 0:
                print(f"[✓] Bound {perm.perm_code} to chief role")
            else:
                print(f"[!] {perm.perm_code} already bound")
        
        await session.commit()
        print("\n[SUCCESS] Permissions updated successfully!")


if __name__ == "__main__":
    asyncio.run(fix_permissions())
