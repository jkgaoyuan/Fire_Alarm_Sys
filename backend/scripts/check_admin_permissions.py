"""
快速检查用户权限和菜单访问情况
"""
from sqlalchemy import text
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

from app.db.session import AsyncSessionLocal


async def check_admin_user():
    """检查 admin 用户的角色和权限"""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("Admin User Permissions Check")
        print("=" * 80)
        
        # 1. 查找 admin 用户
        result = await session.execute(
            text("""
                SELECT u.id, u.username, u.real_name 
                FROM users u 
                WHERE u.username IN ('admin', 'administrator')
                ORDER BY u.created_at DESC LIMIT 1
            """)
        )
        user = result.fetchone()
        
        if not user:
            print("[!] No admin user found!")
            return
        
        print(f"\n[1] User Info:")
        print(f"    ID: {user.id}")
        print(f"    Username: {user.username}")
        print(f"    Real Name: {user.real_name}")
        
        # 2. 获取用户所有角色
        result = await session.execute(
            text("""
                SELECT r.id, r.role_code, r.role_name, r.is_builtin
                FROM roles r
                JOIN user_roles ur ON r.id = ur.role_id
                WHERE ur.user_id = :user_id
                ORDER BY r.sort_order
            """),
            {"user_id": user.id}
        )
        roles = result.fetchall()
        
        print(f"\n[2] User's Roles ({len(roles)} role(s)):")
        for role in roles:
            builtin_str = "✓" if role.is_builtin else " "
            print(f"    [{builtin_str}] {role.role_code}: {role.role_name}")
        
        # 3. 获取每个角色的联动预案权限
        print(f"\n[3] Linkage Plan Permissions by Role:")
        
        all_perm_codes = []
        for role in roles:
            result = await session.execute(
                text("""
                    SELECT DISTINCT p.perm_code, p.perm_name
                    FROM permissions p
                    JOIN role_permissions rp ON p.id = rp.perm_id
                    WHERE rp.role_id = :role_id AND p.perm_code LIKE '%linkage%'
                    ORDER BY p.perm_code
                """),
                {"role_id": role.id}
            )
            perms = result.fetchall()
            
            if perms:
                print(f"\n    [{role.role_code}] has these linkage permissions:")
                for perm in perms:
                    print(f"       • {perm.perm_code}: {perm.perm_name}")
                    all_perm_codes.append(perm.perm_code)
            else:
                print(f"\n    [{role.role_code}] has NO linkage permissions!")
        
        # 4. 总结
        print("\n" + "=" * 80)
        if 'linkage:view' in all_perm_codes or 'linkage:plan' in all_perm_codes:
            print("✓ SUCCESS! Admin user can access linkage page")
            print("\nTo verify:")
            print("1. Logout and login again")
            print("2. Visit http://localhost:5173/linkage")
        else:
            print("✗ FAILURE! Admin user cannot access linkage page")
            print("\nSolution:")
            print("Run: python scripts/init_linkage_menu_complete.py")
            print("Then logout and login again")
        
        print("=" * 80)


if __name__ == "__main__":
    import asyncio
    asyncio.run(check_admin_user())
