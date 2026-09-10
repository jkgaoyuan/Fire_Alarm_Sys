"""
pytest 全局 fixtures
"""

import fakeredis
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.redis import get_redis_pool
from app.db.session import get_db
from app.main import app
from app.models.base import Base
from app.models import *  # noqa: F401,F403 确保模型注册

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, future=True)
TestingSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@pytest_asyncio.fixture
async def db_engine():
    """每个测试函数独立的数据库引擎（自动建表/删表）"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(db_engine):
    """数据库会话 - 简单模式（不处理异步 close）"""
    session = TestingSessionLocal()
    # 直接 yield，让 pytest/事件循环管理生命周期
    yield session


@pytest_asyncio.fixture
async def fake_redis():
    """
    内存 Redis（计划 10.1 前置）。

    3.3 的推送与补发依赖 XADD/XRANGE/XREADGROUP/GETDEL 的真实命令语义，
    手写桩无法覆盖，统一改用 fakeredis 的异步实现。
    """
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def client(db_session, fake_redis):
    """HTTP 测试客户端（依赖注入覆盖）"""
    async def override_get_db():
        yield db_session

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_pool] = override_get_redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

from app.core.security import create_access_token, get_password_hash
from app.models.permission import Permission
from app.models.user import Role, User


@pytest_asyncio.fixture
async def test_user(db_session):
    """预置测试用户（含角色关联 + 巡检权限）"""
    # 创建测试角色
    role = Role(
        role_code="test_role",
        role_name="测试角色",
        is_builtin=False,
    )
    db_session.add(role)
    await db_session.flush()

    # 创建巡检相关权限
    permissions = []
    for perm_code in ["inspection:view", "inspection:create", "inspection:update", "inspection:execute", "inspection:stat"]:
        perm = Permission(
            perm_code=perm_code,
            perm_name=perm_code.split(":")[1].title(),  # view -> View, create -> Create
            perm_type="api",
            parent_id=None,
        )
        permissions.append(perm)
        db_session.add(perm)
    
    await db_session.flush()

    # 将权限关联到角色
    role.permissions.extend(permissions)

    # 创建测试用户
    user = User(
        username="testuser",
        password_hash=get_password_hash("Test1234"),
        real_name="测试用户",
        status="active",
        data_scope="all",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_client_with_user(client, test_user, fake_redis):
    """已登录的 client（携带有效 Access Token）"""
    token = create_access_token(
        data={"sub": str(test_user.id), "jti": "test-jti-fixture"}
    )

    # 保存原始请求方法
    original_request = client.request

    async def _authenticated_request(method, url, **kwargs):
        # 确保 kwargs['headers'] 是一个 dict
        current_headers = kwargs.get("headers") or {}
        current_headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = current_headers
        return await original_request(method, url, **kwargs)

    # 替换请求方法（自动携带 Token）
    client.request = _authenticated_request
    yield client
    client.request = original_request
