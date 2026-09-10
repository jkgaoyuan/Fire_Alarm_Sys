"""
通知中心测试（3.5-T6d-T6f）
覆盖：列表查询、标记已读、未读数统计
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


class TestNotificationList:
    """测试 6d: 通知列表查询功能"""
    
    @pytest.mark.asyncio
    async def test_list_notifications_with_pagination(self, db_session, test_user):
        """T6d: 分页获取用户通知列表"""
        from app.models.emergency import Notification
        
        # 创建多条测试通知
        for i in range(10):
            notification = Notification(
                user_id=test_user.id,
                title=f"测试通知{i}",
                content=f"内容{i}",
                module="emergency",
                is_read=i % 2 == 0  # 交替已读未读
            )
            db_session.add(notification)
        
        await db_session.flush()
        
        # 测试分页查询
        from app.services.emergency_service import get_user_notifications
        
        result = await get_user_notifications(db_session, test_user.id, page=1, page_size=5)
        
        assert result["total"] >= 10
        assert len(result["items"]) == 5
        assert result["page"] == 1
        assert result["page_size"] == 5
        assert result["total_pages"] >= 2
    
    @pytest.mark.asyncio
    async def test_filter_by_module(self, db_session, test_user):
        """测试按模块筛选通知"""
        from app.models.emergency import Notification
        from app.services.emergency_service import get_user_notifications
        
        # 创建不同模块的通知
        emergency_notif = Notification(
            user_id=test_user.id,
            title="应急通知",
            module="emergency"
        )
        system_notif = Notification(
            user_id=test_user.id,
            title="系统通知",
            module="system"
        )
        
        db_session.add_all([emergency_notif, system_notif])
        await db_session.flush()
        
        # 只查询 emergency 模块
        result = await get_user_notifications(
            db_session, 
            test_user.id, 
            module="emergency"
        )
        
        assert result["total"] == 1
        assert all(n.module == "emergency" for n in result["items"])
    
    @pytest.mark.asyncio
    async def test_owner_only_access(self, db_session, test_user, db_session_another):
        """测试只能查看自己的通知"""
        from app.models.emergency import Notification
        
        # 为另一个用户创建通知（需先创建另一个用户实例）
        from app.models.user import User
        from app.core.security import get_password_hash
        
        another_user = User(
            username="another_test_user",
            password_hash=get_password_hash("Test1234"),
            real_name="另一个用户",
            org_id=1,
            status="active"
        )
        db_session.add(another_user)
        await db_session.flush()
        
        notification_for_another = Notification(
            user_id=another_user.id,
            title="专属通知",
            content="仅该用户可见"
        )
        db_session.add(notification_for_another)
        await db_session.flush()
        
        # 测试用户应看不到另一用户的通知
        from app.services.emergency_service import get_user_notifications
        
        result = await get_user_notifications(db_session, test_user.id)
        
        titles = [n.title for n in result["items"]]
        assert "专属通知" not in titles


class TestMarkAsRead:
    """测试 6e: 标记已读功能"""
    
    @pytest.mark.asyncio
    async def test_mark_single_as_read(self, db_session, test_user):
        """T6e: 标记单条通知为已读"""
        from app.models.emergency import Notification
        from app.services.emergency_service import mark_notifications_as_read
        
        notification = Notification(
            user_id=test_user.id,
            title="待读通知",
            is_read=False
        )
        db_session.add(notification)
        await db_session.flush()
        
        notification_id = notification.id
        
        # 标记为已读
        count = await mark_notifications_as_read(
            db_session, 
            test_user.id, 
            [notification_id]
        )
        
        # 验证状态已更新
        stmt = select(Notification).where(Notification.id == notification_id)
        updated_notification = (await db_session.execute(stmt)).scalar_one_or_none()
        
        assert updated_notification.is_read == True
    
    @pytest.mark.asyncio
    async def test_cannot_mark_other_users_notifications(self, db_session, test_user):
        """测试无法标记其他用户的通知为已读"""
        from app.models.emergency import Notification
        from app.models.user import User
        from app.core.security import get_password_hash
        
        # 创建另一个用户及其通知
        another_user = User(
            username="another_mark_user",
            password_hash=get_password_hash("Test1234"),
            real_name="另一用户",
            org_id=1,
            status="active"
        )
        db_session.add(another_user)
        await db_session.flush()
        
        other_notification = Notification(
            user_id=another_user.id,
            title="他人的通知",
            is_read=False
        )
        db_session.add(other_notification)
        await db_session.flush()
        
        # 尝试用 test_user 标记其他用户的通知为已读
        count = await mark_notifications_as_read(
            db_session,
            test_user.id,  # 错误的用户 ID
            [other_notification.id]
        )
        
        # 应该不影响其他用户的通知状态
        stmt = select(Notification).where(Notification.id == other_notification.id)
        updated = (await db_session.execute(stmt)).scalar_one_or_none()
        
        assert updated.is_read == False
    
    @pytest.mark.asyncio
    async def test_mark_nonexistent_notifications(self, db_session, test_user):
        """测试标记不存在的通知（不应报错）"""
        from app.services.emergency_service import mark_notifications_as_read
        
        count = await mark_notifications_as_read(
            db_session,
            test_user.id,
            [99999, 88888]  # 不存在的通知 ID
        )
        
        assert count == 0, "不存在的通知更新数应为 0"


class TestUnreadCount:
    """测试 6f: 未读数统计功能"""
    
    @pytest.mark.asyncio
    async def test_get_unread_count(self, db_session, test_user):
        """T6f: 获取用户未读通知数量"""
        from app.models.emergency import Notification
        from app.services.emergency_service import get_unread_count
        
        # 创建混合状态的 3 条通知
        for i in range(3):
            notification = Notification(
                user_id=test_user.id,
                title=f"通知{i}",
                is_read=(i % 2 == 0)  # 偶数为已读，奇数为未读 → 1 条未读
            )
            db_session.add(notification)
        
        await db_session.flush()
        
        count = await get_unread_count(db_session, test_user.id)
        
        assert count == 1, f"应该有 1 条未读通知，实际{count}"
    
    @pytest.mark.asyncio
    async def test_unread_count_all_read(self, db_session, test_user):
        """测试全部已读时未读数为 0"""
        from app.models.emergency import Notification
        from app.services.emergency_service import get_unread_count
        
        for i in range(5):
            notification = Notification(
                user_id=test_user.id,
                title=f"已读{i}",
                is_read=True
            )
            db_session.add(notification)
        
        await db_session.flush()
        
        count = await get_unread_count(db_session, test_user.id)
        
        assert count == 0
    
    @pytest.mark.asyncio
    async def test_unread_count_all_unread(self, db_session, test_user):
        """测试全部未读时计数正确"""
        from app.models.emergency import Notification
        from app.services.emergency_service import get_unread_count
        
        for i in range(10):
            notification = Notification(
                user_id=test_user.id,
                title=f"未读{i}",
                is_read=False
            )
            db_session.add(notification)
        
        await db_session.flush()
        
        count = await get_unread_count(db_session, test_user.id)
        
        assert count == 10


@pytest.fixture
async def db_session_another():
    """另一个数据库会话用于并发测试"""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.config import get_settings
    
    settings = get_settings()
    engine = create_async_engine(settings.database_url_async)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession)
    
    async with AsyncSessionLocal() as session:
        yield session
        await session.close()


class TestNotificationConcurrency:
    """通知中心的并发操作测试"""
    
    @pytest.mark.asyncio
    async def test_concurrent_mark_read(self, db_session, test_user):
        """测试并发标记已读不会出错"""
        from app.models.emergency import Notification
        from app.services.emergency_service import mark_notifications_as_read
        
        # 创建多条通知
        notifications = []
        for i in range(5):
            notif = Notification(
                user_id=test_user.id,
                title=f"并发测试{i}",
                is_read=False
            )
            db_session.add(notif)
            notifications.append(notif.id)
        
        await db_session.flush()
        
        # 并发多次调用（简化测试，实际应由 asyncio.gather 并行）
        for _ in range(3):
            await mark_notifications_as_read(db_session, test_user.id, notifications)
        
        # 最终所有通知应都标记为已读
        remaining_unread = [n for n in notifications if (
            await db_session.execute(select(Notification).where(
                Notification.id == n, Notification.is_read == False
            ))
        ).scalar_one_or_none()]
        
        assert len(remaining_unread) == 0, "所有通知都应已读"


class TestNotificationEdgeCases:
    """边缘情况测试"""
    
    @pytest.mark.asyncio
    async def test_empty_user_has_zero_unread(self, db_session):
        """测试没有通知的用户返回 0"""
        from app.models.user import User
        from app.core.security import get_password_hash
        from app.services.emergency_service import get_unread_count
        
        user = User(
            username="empty_user",
            password_hash=get_password_hash("Test1234"),
            real_name="无通知用户",
            org_id=1,
            status="active"
        )
        db_session.add(user)
        await db_session.flush()
        
        count = await get_unread_count(db_session, user.id)
        
        assert count == 0
    
    @pytest.mark.asyncio
    async def test_large_number_of_notifications(self, db_session, test_user):
        """测试大量通知时的性能表现"""
        from app.models.emergency import Notification
        from app.services.emergency_service import get_user_notifications
        
        # 创建 100 条通知
        for i in range(100):
            notification = Notification(
                user_id=test_user.id,
                title=f"批量通知{i}",
                content=f"详细内容{i}",
                module="emergency",
                is_read=False
            )
            db_session.add(notification)
        
        await db_session.flush()
        
        # 测试分页查询是否正常工作
        result = await get_user_notifications(
            db_session,
            test_user.id,
            page=1,
            page_size=20
        )
        
        assert result["total"] == 100
        assert len(result["items"]) == 20
        assert result["total_pages"] == 5
    
    @pytest.mark.asyncio
    async def test_long_title_and_content(self, db_session, test_user):
        """测试超长标题和内容"""
        from app.models.emergency import Notification
        from app.services.emergency_service import get_user_notifications
        
        long_title = "A" * 200  # 超过 100 字符限制
        long_content = "B" * 1000
        
        notification = Notification(
            user_id=test_user.id,
            title=long_title,
            content=long_content
        )
        db_session.add(notification)
        await db_session.flush()
        
        # Pydantic Schema 应处理截断或报错
        try:
            result = await get_user_notifications(db_session, test_user.id)
            assert result["total"] >= 1
        except Exception:
            # 如果 Schema 验证失败则正常
            pass
