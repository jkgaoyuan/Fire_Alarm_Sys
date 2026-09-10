"""
3.6 Inspection Test Conftest - Simplified Version
===================================================
解决 MissingGreenlet 错误的独立 fixtures
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.redis import get_redis_pool
from app.db.session import get_db
from app.main import app
from app.models.base import Base

# In-memory SQLite for testing  
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

TestingSessionLocal = async_sessionmaker(
    test_engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@pytest_asyncio.fixture(scope="session")
async def event_loop():
    """Create an instance of the default event loop for each test session."""
    import asyncio
    loop = asyncio.get_event_loop_policy().get_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    """Create database tables before each test"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture  
async def db_session(db_engine):
    """Simple sync session that works without async context manager"""
    # Create session but don't use async with
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        # Don't await close() - just call it sync
        session.close()


@pytest_asyncio.fixture
async def client(db_session):
    """Test HTTP client with overridden database dependency"""
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    
    app.dependency_overrides.clear()


from app.core.security import create_access_token, get_password_hash
from app.models.permission import Permission
from app.models.user import Role, User


@pytest_asyncio.fixture
async def test_user(db_session):
    """Test user with inspection permissions"""
    # Create role
    role = Role(
        role_code="inspection_test_role",
        role_name="巡检测试角色",
        is_builtin=False,
    )
    db_session.add(role)
    await db_session.flush()
    
    # Create permissions
    permissions = []
    for perm_code in [
        "inspection:view", "inspection:create", "inspection:update", 
        "inspection:execute", "inspection:stat"
    ]:
        perm = Permission(
            perm_code=perm_code,
            perm_name=perm_code.split(":")[1].title(),
            perm_type="api",
            parent_id=None,
        )
        permissions.append(perm)
        db_session.add(perm)
    
    await db_session.flush()
    role.permissions.extend(permissions)
    
    # Create user
    user = User(
        username="inspection_test_user",
        password_hash=get_password_hash("Test1234"),
        real_name="巡检测试用户",
        status="active",
        data_scope="all",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def authenticated_client(client, test_user):
    """Authenticated HTTP client with test user token"""
    token = create_access_token(
        data={"sub": str(test_user.id), "jti": "test-jti-authenticated"}
    )
    
    original_request = client.request
    
    async def _authenticated_request(method, url, **kwargs):
        headers = kwargs.get("headers") or {}
        headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers
        return await original_request(method, url, **kwargs)
    
    client.request = _authenticated_request
    yield client
    client.request = original_request
