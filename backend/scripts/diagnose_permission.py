"""
诊断：直接测试 API 权限验证逻辑
"""
import asyncio
import sys
sys.path.append('.')

from sqlalchemy import text
from app.db.session import AsyncSessionLocal


async def diagnose_permission_issue():
    """诊断权限问题"""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("Permission Verification Test")
        print("=" * 80)
        
        # 1. 获取 admin 用户的角色 ID
        user_result = await session.execute(
            text("""
                SELECT u.id, u.username 
                FROM users u 
                WHERE u.username IN ('admin', 'administrator')
                ORDER BY u.created_at DESC LIMIT 1
            """)
        )
        user = user_result.fetchone()
        
        if not user:
            print("[!] No admin user found!")
            return
        
        print(f"\n[1] User: {user.username} (ID: {user.id})")
        
        # 2. 获取角色的权限代码列表
        result = await session.execute(
            text("""
                SELECT DISTINCT p.perm_code
                FROM roles r
                JOIN role_permissions rp ON r.id = rp.role_id
                JOIN permissions p ON rp.perm_id = p.id
                JOIN user_roles ur ON r.id = ur.role_id
                WHERE ur.user_id = :user_id AND p.perm_code LIKE '%linkage%'
                ORDER BY p.perm_code
            """),
            {"user_id": user.id}
        )
        
        perms = [row.perm_code for row in result.fetchall()]
        
        print(f"\n[2] Admin has {len(perms)} linkage permissions:")
        for perm in sorted(perms):
            print(f"   ✓ {perm}")
        
        # 3. 特别检查 linkage:view
        if 'linkage:view' in perms:
            print("\n[✓] SUCCESS! linkage:view permission exists!")
            print("\nConclusion:")
            print("- Database is configured correctly")
            print("- API should work without requiring emergency:view")
            print("- The error might be from a different code path")
        else:
            print("\n[✗] FAILURE! linkage:view missing!")
            print("\nFix needed:")
            print("Run: python scripts/init_linkage_menu_complete.py")
        
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(diagnose_permission_issue())
