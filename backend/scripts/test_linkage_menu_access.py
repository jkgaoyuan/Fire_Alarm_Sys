"""
测试当前用户能否获取联动预案菜单
模拟 /api/v1/users/me/menus 接口的调用
"""
import asyncio
import sys
sys.path.append('.')

from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.services.permission_service import build_menu_tree
from app.models.user import User


async def test_linkage_menu_access():
    """测试联动预案菜单访问权限"""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("Testing Linkage Menu Access")
        print("=" * 80)
        
        # 1. 查找 admin 或 chief 用户
        result = await session.execute(
            text("""
                SELECT id, username, role_ids 
                FROM users 
                WHERE username IN ('admin', 'administrator')
                ORDER BY created_at DESC LIMIT 1
            """)
        )
        user_row = result.fetchone()
        
        if not user_row:
            print("[!] No admin/user found in database!")
            return
        
        print(f"\n[1] Found user: {user_row.username} (ID: {user_row.id})")
        print(f"    Role IDs: {user_row.role_ids}")
        
        # 2. 加载完整用户对象（包含 roles）
        user_result = await session.execute(
            text("SELECT * FROM users WHERE id = :id"),
            {"id": user_row.id}
        )
        user = user_result.scalar()
        
        print(f"\n[2] Loaded user with roles:")
        for role in user.roles:
            print(f"    - {role.role_code}: {role.role_name}")
        
        # 3. 获取菜单树
        print(f"\n[3] Building menu tree...")
        menus = await build_menu_tree(user, session)
        
        print(f"    Total menus: {len(menus)}")
        for i, menu in enumerate(menus, 1):
            route_path = menu.get('path', '')
            icon = menu.get('meta', {}).get('icon', '')
            title = menu.get('meta', {}).get('title', '')
            children_count = len(menu.get('children', []))
            
            print(f"    {i}. [{route_path}] {icon} {title} ({children_count} children)")
            
            # 检查是否是联动预案
            if 'linkage' in route_path or '联动' in title:
                print(f"       [✓] FOUND! This is the linkage menu!")
        
        # 4. 检查是否有 linkage 菜单
        has_linkage = any(
            'linkage' in menu.get('path', '') or '联动' in menu.get('meta', {}).get('title', '')
            for menu in menus
        )
        
        print("\n" + "=" * 80)
        if has_linkage:
            print("[SUCCESS] Linkage menu is accessible by this user!")
            print("\nTo access the page:")
            print("1. Clear browser cache (Ctrl + Shift + Delete)")
            print("2. Logout and login again")
            print("3. Visit http://localhost:5173/linkage")
        else:
            print("[FAIL] Linkage menu NOT found in user's permissions!")
            print("\nPossible reasons:")
            print("1. User doesn't have the right role assigned")
            print("2. Role doesn't have linkage:plan permission bound")
            print("3. Need to run init_linkage_menu_complete.py script")
        
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_linkage_menu_access())
