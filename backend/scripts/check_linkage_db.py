"""
后端数据库检查脚本 - 验证联动预案菜单是否存在
"""
import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal


async def check_linkage_menu():
    """检查联动预案菜单和权限"""
    async with AsyncSessionLocal() as session:
        # 1. 查询菜单权限
        result = await session.execute(
            text("SELECT perm_code, perm_name, route_path FROM permissions WHERE perm_code LIKE 'linkage:%' ORDER BY perm_code")
        )
        menus = result.fetchall()
        
        print("=" * 80)
        print("Linkage Menu & Permissions in Database:")
        print("=" * 80)
        
        for menu in menus:
            print(f"Code: {menu.perm_code}")
            print(f"Name: {menu.perm_name}")
            print(f"Path: {menu.route_path}")
            print("-" * 40)
        
        if not menus:
            print("No linkage permissions found!")
        
        print("\n" + "=" * 80)
        
        # 2. 查询角色权限绑定情况（消防主管）
        role_result = await session.execute(
            text("""
                SELECT r.role_name, p.perm_code, rp.bound_at
                FROM roles r
                LEFT JOIN role_permissions rp ON r.id = rp.role_id
                LEFT JOIN permissions p ON rp.perm_id = p.id AND p.perm_code LIKE 'linkage:%'
                WHERE r.role_code = 'chief'
                ORDER BY rp.bound_at DESC
            """)
        )
        bindings = role_result.fetchall()
        
        print("\nRole Permission Bindings (Chief/Admin):")
        print("=" * 80)
        for binding in bindings:
            print(f"{binding.role_name} -> {binding.perm_code or 'N/A'}")
        
        if not bindings:
            print("No bindings found for chief role.")
        
        print("\n" + "=" * 80)
        print("Query completed successfully!")


if __name__ == "__main__":
    asyncio.run(check_linkage_menu())
