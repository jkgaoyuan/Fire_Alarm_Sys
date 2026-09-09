"""
认证模块单元测试
覆盖场景：登录成功、密码错误、账户锁定、Token 刷新、登出黑名单
"""

import pytest

from app.core.security import create_access_token, decode_token, get_password_hash
from app.models.user import User
from app.services.auth_service import create_token_pair, save_token_whitelist


@pytest.mark.asyncio
async def test_login_success(client, db_session):
    """登录成功：返回 Access Token + 用户信息，Cookie 携带 Refresh Token"""
    user = User(
        username="admin",
        password_hash=get_password_hash("Admin1234"),
        real_name="管理员",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin1234"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert "access_token" in data["data"]
    assert data["data"]["token_type"] == "bearer"
    assert data["data"]["user"]["username"] == "admin"
    assert data["data"]["user"]["real_name"] == "管理员"
    assert "refresh_token" in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_password_remaining_attempts(client, db_session):
    """密码错误：返回剩余尝试次数"""
    user = User(
        username="test",
        password_hash=get_password_hash("Test1234"),
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "test", "password": "WrongPassword1"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 4001
    assert data["message"] == "密码错误"
    assert data["data"]["remaining_attempts"] == 4


@pytest.mark.asyncio
async def test_login_fifth_failure_locks_account(client, db_session):
    """连续 5 次密码错误后账户被锁定"""
    user = User(
        username="locktest",
        password_hash=get_password_hash("Lock1234"),
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    # 前 4 次失败，每次检查剩余次数
    for i in range(4):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "locktest", "password": "WrongPassword1"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == 4001
        assert data["data"]["remaining_attempts"] == 4 - i

    # 第 5 次失败 -> 账户锁定
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "locktest", "password": "WrongPassword1"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 4003
    assert data["message"] == "账户已锁定"
    assert "locked_until" in data["data"]


@pytest.mark.asyncio
async def test_login_during_lock_rejected(client, db_session):
    """锁定期间即使密码正确也拒绝登录"""
    from datetime import datetime, timedelta, timezone

    locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
    user = User(
        username="locked",
        password_hash=get_password_hash("Locked1234"),
        status="locked",
        login_fail_count=5,
        locked_until=locked_until,
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "locked", "password": "Locked1234"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 4003
    assert "locked_until" in data["data"]


@pytest.mark.asyncio
async def test_refresh_token(client, db_session, fake_redis):
    """使用有效的 Refresh Token（Cookie）刷新 Access Token"""
    user = User(
        username="refresh",
        password_hash=get_password_hash("Refresh1234"),
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    tokens = await create_token_pair(user)
    await save_token_whitelist(fake_redis, user.id, tokens["refresh_jti"])

    client.cookies.set("refresh_token", tokens["refresh_token"])
    response = await client.post("/api/v1/auth/refresh")
    client.cookies.clear()
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert "access_token" in data["data"]
    assert data["data"]["expires_in"] == 3600


@pytest.mark.asyncio
async def test_logout_blacklist(client, db_session, fake_redis):
    """登出：Access Token 加入黑名单，Refresh Token 白名单被清除，Cookie 被清空"""
    user = User(
        username="logout",
        password_hash=get_password_hash("Logout1234"),
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    tokens = await create_token_pair(user)
    await save_token_whitelist(fake_redis, user.id, tokens["refresh_jti"])

    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["message"] == "登出成功"

    # 验证白名单已被删除
    whitelist_key = f"token_whitelist:{user.id}:{tokens['refresh_jti']}"
    assert await fake_redis.exists(whitelist_key) == 0

    # 验证黑名单已写入
    blacklist_key = f"token_blacklist:{tokens['jti']}"
    assert await fake_redis.exists(blacklist_key) == 1

    # 验证 Cookie 被清除（Max-Age=0）
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "Max-Age=0" in set_cookie
