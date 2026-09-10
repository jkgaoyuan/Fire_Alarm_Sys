"""
完整初始化联动预案菜单和权限
确保：
1. linkage:plan 菜单存在
2. linkage:view 等按钮权限存在
3. 所有权限绑定到 admin/chief 角色
"""
import asyncio
import sys
sys.path.append('.')

from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.models.permission import Permission


async def init_linkage_menu_and_permissions():
    """初始化联动预案菜单和权限"""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("Initializing Linkage Menu & Permissions")
        print("=" * 80)
        
        # 1. 确保 linkage:plan 菜单存在
        result = await session.execute(
            text("SELECT id FROM permissions WHERE perm_code = 'linkage:plan'")
        )
        plan_menu = result.fetchone()
        
        if not plan_menu:
            print("[1/6] Creating linkage:plan menu...")
            menu = Permission(
                perm_code="linkage:plan",
                perm_name="联动预案",
                perm_type="menu",
                route_path="/linkage/plan",
                component="views/linkage/Plan.vue",
                icon="Link",
                sort_order=4
            )
            session.add(menu)
            await session.flush()
            print(f"    Created menu (ID: {menu.id})")
            plan_menu_id = menu.id
        else:
            print(f"[1/6] linkage:plan menu exists (ID: {plan_menu.id})")
            plan_menu_id = plan_menu.id
        
        # 2. 确保按钮权限存在
        button_permissions = [
            ("linkage:view", "查看预案", 1),
            ("linkage:create", "新增预案", 2),
            ("linkage:update", "编辑预案", 3),
            ("linkage:delete", "删除预案", 4),
            ("linkage:execute", "执行联动", 5),
            ("linkage:simulate", "模拟测试", 6),
        ]
        
        print("\n[2/6] Checking button permissions...")
        perm_ids = []
        for code, name, order in button_permissions:
            result = await session.execute(
                text("SELECT id FROM permissions WHERE perm_code = :code"),
                {"code": code}
            )
            perm = result.fetchone()
            
            if not perm:
                print(f"    Creating {code}...")
                new_perm = Permission(
                    perm_code=code,
                    perm_name=name,
                    perm_type="button",
                    parent_id=plan_menu_id,
                    sort_order=order
                )
                session.add(new_perm)
                await session.flush()
                perm_ids.append(new_perm.id)
                print(f"    Created (ID: {new_perm.id})")
            else:
                perm_ids.append(perm.id)
                print(f"    {code} exists (ID: {perm.id})")
        
        # 3. 绑定所有权限到 chief role
        print("\n[3/6] Binding permissions to chief role...")
        role_result = await session.execute(
            text("SELECT id FROM roles WHERE role_code = 'chief'")
        )
        chief_role = role_result.fetchone()
        
        if not chief_role:
            print("    [WARNING] Chief role not found!")
        else:
            print(f"    Found chief role (ID: {chief_role.id})")
            
            all_perm_ids = [plan_menu_id] + perm_ids
            bound_count = 0
            
            for perm_id in all_perm_ids:
                bind_result = await session.execute(
                    text("""
                        INSERT INTO role_permissions (role_id, perm_id)
                        VALUES (:role_id, :perm_id)
                        ON CONFLICT DO NOTHING
                    """),
                    {"role_id": chief_role.id, "perm_id": perm_id}
                )
                
                if bind_result.rowcount > 0:
                    bound_count += 1
            
            print(f"    Bound {bound_count} new permissions")
        
        # 4. 同样绑定到 admin role（如果存在）
        print("\n[4/6] Binding permissions to admin role...")
        admin_result = await session.execute(
            text("SELECT id FROM roles WHERE role_code = 'admin'")
        )
        admin_role = admin_result.fetchone()
        
        if admin_role:
            print(f"    Found admin role (ID: {admin_role.id})")
            
            bound_count = 0
            for perm_id in all_perm_ids:
                bind_result = await session.execute(
                    text("""
                        INSERT INTO role_permissions (role_id, perm_id)
                        VALUES (:role_id, :perm_id)
                        ON CONFLICT DO NOTHING
                    """),
                    {"role_id": admin_role.id, "perm_id": perm_id}
                )
                
                if bind_result.rowcount > 0:
                    bound_count += 1
            
            print(f"    Bound {bound_count} new permissions")
        else:
            print("    Admin role not found (skipped)")
        
        await session.commit()
        
        print("\n" + "=" * 80)
        print("[SUCCESS] Linkage menu and permissions initialized!")
        print("=" * 80)
        print("\nNext steps:")
        print("1. Clear browser cache (Ctrl + Shift + Delete)")
        print("2. Logout and login again with admin account")
        print("3. Access: http://localhost:5173/linkage")


if __name__ == "__main__":
    asyncio.run(init_linkage_menu_and_permissions())
