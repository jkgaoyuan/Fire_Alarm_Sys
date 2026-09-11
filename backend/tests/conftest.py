"""
pytest 全局 fixtures
"""

import fakeredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
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
    """数据库会话 - 简单 sync 模式"""
    session = TestingSessionLocal()
    # Just yield the session directly - use it in test functions
    try:
        yield session
    finally:
        await session.close()


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
from tests.statistics_helpers import auth_headers as statistics_auth_headers


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


# ==================== E2E 测试 Fixures ====================

@pytest_asyncio.fixture
async def auth_headers(db_session, test_user):
    """
    E2E 测试认证 headers（含 export 权限）
    用于 test_statistics_e2e_integration.py
    """
    # 确保 test_user 有 statistics:view 和 statistics:export 权限
    view_perm = (await db_session.execute(
        select(Permission).where(Permission.perm_code == "statistics:view")
    )).scalar_one_or_none()
    if not view_perm:
        view_perm = Permission(
            perm_code="statistics:view",
            perm_name="Statistical View",
            perm_type="button"
        )
        db_session.add(view_perm)
        await db_session.flush()
    
    export_perm = (await db_session.execute(
        select(Permission).where(Permission.perm_code == "statistics:export")
    )).scalar_one_or_none()
    if not export_perm:
        export_perm = Permission(
            perm_code="statistics:export",
            perm_name="Statistical Export",
            perm_type="button"
        )
        db_session.add(export_perm)
        await db_session.flush()
    
    # 将权限添加到 test_user 的角色中
    for role in test_user.roles:
        if view_perm not in role.permissions:
            role.permissions.append(view_perm)
        if export_perm not in role.permissions:
            role.permissions.append(export_perm)
    
    await db_session.commit()
    return statistics_auth_headers(test_user)


@pytest_asyncio.fixture
async def viewer_user(db_session):
    """
    E2E 测试用 viewer 用户（只有 statistics:view 权限）
    """
    from app.models.organization import Organization
    
    # 创建统计权限
    view_perm = (await db_session.execute(
        select(Permission).where(Permission.perm_code == "statistics:view")
    )).scalar_one_or_none()
    if not view_perm:
        view_perm = Permission(
            perm_code="statistics:view",
            perm_name="Statistical View",
            perm_type="button"
        )
        db_session.add(view_perm)
        await db_session.flush()
    
    export_perm = (await db_session.execute(
        select(Permission).where(Permission.perm_code == "statistics:export")
    )).scalar_one_or_none()
    if not export_perm:
        export_perm = Permission(
            perm_code="statistics:export",
            perm_name="Statistical Export",
            perm_type="button"
        )
        db_session.add(export_perm)
        await db_session.flush()
    
    # 创建角色
    role = Role(
        role_code="viewer_role",
        role_name="Viewer Role",
        is_builtin=False
    )
    db_session.add(role)
    await db_session.flush()
    
    # 只添加 view 权限
    role.permissions.append(view_perm)
    
    # 创建用户
    user = User(
        username="viewer_e2e",
        password_hash=get_password_hash("Test1234"),
        real_name="E2E Viewer",
        status="active",
        data_scope="all"
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def viewer_auth_headers(viewer_user):
    """
    E2E 测试认证 headers（只有 view 权限）
    用于 test_statistics_e2e.py
    """
    return statistics_auth_headers(viewer_user)
