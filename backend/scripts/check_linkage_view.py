"""
检查 linkage:view 权限是否存在
"""
import asyncio
import sys
sys.path.append('.')

from sqlalchemy import text
from app.db.session import AsyncSessionLocal


async def check_linkage_view_permission():
    """检查 linkage:view 权限"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, perm_code, perm_name 
                FROM permissions 
                WHERE perm_code LIKE 'linkage%'
                ORDER BY perm_code
            """)
        )
        permissions = result.fetchall()
        
        print("=" * 80)
        print("Linkage Permissions in Database:")
        print("=" * 80)
        
        for perm in permissions:
            print(f"{perm.id}: {perm.perm_code} - {perm.perm_name}")
            
        print("\nChecking if linkage:view exists...")
        result2 = await session.execute(
            text("""
                SELECT COUNT(*) FROM permissions WHERE perm_code = 'linkage:view'
            """)
        )
        count = result2.scalar()
        
        if count > 0:
            print("[✓] linkage:view EXISTS")
        else:
            print("[✗] linkage:view MISSING - Need to create it!")
            
            # Create linkage:view permission
            from app.models.permission import Permission
            new_perm = Permission(
                perm_name="查看预案",
                perm_code="linkage:view",
                sort_order=1
            )
            session.add(new_perm)
            await session.flush()
            await session.commit()
            
            print(f"[+] Created linkage:view with ID: {new_perm.id}")


if __name__ == "__main__":
    asyncio.run(check_linkage_view_permission())
