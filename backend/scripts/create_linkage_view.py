"""
创建 linkage:view 权限并绑定到 chief role
"""
import asyncio
import sys
sys.path.append('.')

from app.models.permission import Permission
from app.db.session import AsyncSessionLocal


async def create_linkage_view_permission():
    """创建 linkage:view 权限"""
    async with AsyncSessionLocal() as session:
        # 检查是否已存在
        from sqlalchemy import text
        result = await session.execute(
            text("SELECT id FROM permissions WHERE perm_code = 'linkage:view'")
        )
        existing = result.fetchone()
        
        if existing:
            print(f"[✓] linkage:view already exists (ID: {existing.id})")
        else:
            # 创建新权限
            new_perm = Permission(
                perm_name="查看预案",
                perm_code="linkage:view",
                sort_order=1,
                parent_id=4  # 作为 linkage:plan (ID:4) 的子权限
            )
            session.add(new_perm)
            await session.flush()
            print(f"[+] Created linkage:view permission (ID: {new_perm.id})")
            
            # 绑定到 chief role
            role_result = await session.execute(
                text("SELECT id FROM roles WHERE role_code = 'chief'")
            )
            chief_role = role_result.fetchone()
            
            if chief_role:
                from sqlalchemy import text
                bind_result = await session.execute(
                    text("""
                        INSERT INTO role_permissions (role_id, perm_id)
                        VALUES (:role_id, :perm_id)
                        ON CONFLICT DO NOTHING
                    """),
                    {"role_id": chief_role.id, "perm_id": new_perm.id}
                )
                
                if bind_result.rowcount > 0:
                    print(f"[✓] Bound to chief role")
                else:
                    print(f"[!] Already bound to chief role")
            
            await session.commit()
            print("[SUCCESS] linkage:view permission created and bound!")


if __name__ == "__main__":
    asyncio.run(create_linkage_view_permission())
