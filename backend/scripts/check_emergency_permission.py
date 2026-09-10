"""
检查 emergency:view 权限是否存在以及用户是否有这个权限
"""
from sqlalchemy import text
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

from app.db.session import AsyncSessionLocal


async def check_emergency_permission():
    """检查 emergency:view 权限"""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("Emergency Permission Check")
        print("=" * 80)
        
        # 1. 查询所有 emergency 权限
        result = await session.execute(
            text("""
                SELECT perm_code, perm_name, perm_type 
                FROM permissions 
                WHERE perm_code LIKE 'emergency:%'
                ORDER BY perm_code
            """)
        )
        perms = result.fetchall()
        
        print(f"\n[1] Emergency Permissions ({len(perms)} found):")
        for p in perms:
            print(f"   • {p.perm_code}: {p.perm_name} [{p.perm_type}]")
        
        if not perms:
            print("\n   [!] No emergency permissions found!")
        
        # 2. 检查 admin 用户是否有 emergency:view
        user_result = await session.execute(
            text("""
                SELECT u.id, u.username 
                FROM users u 
                WHERE u.username IN ('admin', 'administrator')
                ORDER BY u.created_at DESC LIMIT 1
            """)
        )
        user = user_result.fetchone()
        
        if user:
            print(f"\n[2] User Info:")
            print(f"   Username: {user.username} (ID: {user.id})")
            
            result = await session.execute(
                text("""
                    SELECT COUNT(*) FROM permissions p
                    JOIN role_permissions rp ON p.id = rp.perm_id
                    JOIN user_roles ur ON rp.role_id = ur.role_id
                    WHERE ur.user_id = :user_id AND p.perm_code = 'emergency:view'
                """),
                {"user_id": user.id}
            )
            count = result.scalar()
            
            print(f"\n[3] Does user have emergency:view? {'✓ YES' if count > 0 else '✗ NO'}")
            
            if count == 0:
                print("\n   Solution: Run init_linkage_menu_complete.py script again")
                print("   It will add all missing permissions to the user's roles.")
        
        print("\n" + "=" * 80)


if __name__ == "__main__":
    import asyncio
    asyncio.run(check_emergency_permission())
