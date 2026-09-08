"""
认证服务层单元测试
覆盖：账户锁定、Token 生成、登录日志、刷新 Token、登出
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.core.exceptions import AccountLocked, AuthError
from app.core.security import create_access_token, decode_token, get_password_hash
from app.models.user import User
from app.services.auth_service import (
    authenticate_user,
    create_token_pair,
    is_account_locked,
    login_user,
    logout_user,
    record_login_log,
    refresh_access_token,
    save_token_whitelist,
    _parse_user_agent,
)


# ---------------------------------------------------------------------------
# _parse_user_agent
# ---------------------------------------------------------------------------
def test_parse_user_agent_desktop():
    """解析桌面浏览器 User-Agent"""
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    device_type, device_os, browser = _parse_user_agent(ua)
    assert device_type == "desktop"
    assert device_os != "Unknown"


def test_parse_user_agent_mobile():
    """解析移动端 User-Agent"""
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
    device_type, device_os, browser = _parse_user_agent(ua)
    assert device_type == "mobile"


def test_parse_user_agent_none():
    """空 User-Agent 应返回 Unknown"""
    device_type, device_os, browser = _parse_user_agent(None)
    assert device_type == "Unknown"
    assert device_os == "Unknown"
    assert browser == "Unknown"


# ---------------------------------------------------------------------------
# is_account_locked
# ---------------------------------------------------------------------------
def test_is_account_locked_active():
    """正常用户不应被锁定"""
    user = User(username="u", status="active")
    assert is_account_locked(user) is False


def test_is_account_locked_still_locked():
    """锁定期内的用户应被锁定"""
    user = User(
        username="u",
        status="locked",
        locked_until=datetime.now(timezone.utc) + timedelta(minutes=30),
        login_fail_count=5,
    )
    assert is_account_locked(user) is True


def test_is_account_locked_auto_unlock():
    """锁定期已过应自动解锁"""
    user = User(
        username="u",
        status="locked",
        locked_until=datetime.now(timezone.utc) - timedelta(minutes=1),
        login_fail_count=5,
    )
    assert is_account_locked(user) is False
    assert user.status == "active"
    assert user.locked_until is None
    assert user.login_fail_count == 0


# ---------------------------------------------------------------------------
# create_token_pair
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_token_pair(client):
    """应生成 access_token / refresh_token / jti / refresh_jti"""
    user = User(id=1, username="u")
    tokens = await create_token_pair(user)

    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert "jti" in tokens
    assert "refresh_jti" in tokens
    assert len(tokens["jti"]) == 36  # UUID
    assert len(tokens["refresh_jti"]) == 36


# ---------------------------------------------------------------------------
# save_token_whitelist
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_token_whitelist(client, fake_redis):
    """应写入 Redis 白名单"""
    await save_token_whitelist(fake_redis, user_id=1, refresh_jti="abc-123")
    key = "token_whitelist:1:abc-123"
    assert await fake_redis.exists(key) == 1


# ---------------------------------------------------------------------------
# authenticate_user
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_authenticate_success(client, db_session):
    """正确密码应返回 User"""
    user = User(
        username="auth_ok",
        password_hash=get_password_hash("Right1234"),
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    result = await authenticate_user(db_session, "auth_ok", "Right1234")
    assert result is not None
    assert result.username == "auth_ok"


@pytest.mark.asyncio
async def test_authenticate_wrong_password(client, db_session):
    """错误密码应返回 None"""
    user = User(
        username="auth_fail",
        password_hash=get_password_hash("Right1234"),
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    result = await authenticate_user(db_session, "auth_fail", "Wrong1234")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_user_not_found(client, db_session):
    """用户不存在应返回 None"""
    result = await authenticate_user(db_session, "notexist", "pw")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_disabled(client, db_session):
    """禁用账户应抛 AuthError"""
    user = User(
        username="disabled",
        password_hash=get_password_hash("Pw1234"),
        status="disabled",
    )
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(AuthError) as exc:
        await authenticate_user(db_session, "disabled", "Pw1234")
    assert exc.value.code == 4004


@pytest.mark.asyncio
async def test_authenticate_locked(client, db_session):
    """锁定账户应抛 AccountLocked"""
    user = User(
        username="locked",
        password_hash=get_password_hash("Pw1234"),
        status="locked",
        locked_until=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(AccountLocked):
        await authenticate_user(db_session, "locked", "Pw1234")


# ---------------------------------------------------------------------------
# login_user
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_login_user_success(client, db_session, fake_redis):
    """完整登录流程：成功返回 Token 并清零失败计数"""
    user = User(
        username="login_ok",
        password_hash=get_password_hash("Pass1234"),
        status="active",
        login_fail_count=2,
    )
    db_session.add(user)
    await db_session.commit()

    result = await login_user(
        db_session, fake_redis, "login_ok", "Pass1234", "127.0.0.1", None
    )

    assert "access_token" in result
    assert result["user"]["username"] == "login_ok"
    # 失败计数应清零
    assert user.login_fail_count == 0
    assert user.status == "active"


@pytest.mark.asyncio
async def test_login_user_wrong_password(client, db_session, fake_redis):
    """密码错误应递增失败计数并抛 AuthError"""
    user = User(
        username="login_fail",
        password_hash=get_password_hash("Pass1234"),
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(AuthError) as exc:
        await login_user(
            db_session, fake_redis, "login_fail", "Wrong1234", None, None
        )
    assert exc.value.code == 4001
    assert user.login_fail_count == 1


@pytest.mark.asyncio
async def test_login_user_locked(client, db_session, fake_redis):
    """锁定期间登录应抛 AccountLocked"""
    user = User(
        username="login_locked",
        password_hash=get_password_hash("Pass1234"),
        status="locked",
        locked_until=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(AccountLocked):
        await login_user(
            db_session, fake_redis, "login_locked", "Pass1234", None, None
        )


# ---------------------------------------------------------------------------
# refresh_access_token
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_refresh_access_token_success(client, db_session, fake_redis):
    """有效 Refresh Token 应返回新 Access Token"""
    user = User(id=99, username="refresh", password_hash="hash", status="active")
    db_session.add(user)
    await db_session.commit()

    tokens = await create_token_pair(user)
    await save_token_whitelist(fake_redis, user.id, tokens["refresh_jti"])

    result = await refresh_access_token(
        db_session, fake_redis, tokens["refresh_token"]
    )
    assert "access_token" in result
    assert result["expires_in"] == 3600


@pytest.mark.asyncio
async def test_refresh_access_token_invalid_type(client, db_session, fake_redis):
    """非 refresh 类型的 token 应抛 AuthError"""
    access_token = create_access_token(data={"sub": "1", "jti": "abc"})
    with pytest.raises(AuthError) as exc:
        await refresh_access_token(db_session, fake_redis, access_token)
    assert exc.value.code == 401


@pytest.mark.asyncio
async def test_refresh_access_token_not_in_whitelist(client, db_session, fake_redis):
    """白名单不存在的 Refresh Token 应抛 AuthError"""
    user = User(id=100, username="refresh2", password_hash="hash", status="active")
    db_session.add(user)
    await db_session.commit()

    tokens = await create_token_pair(user)
    # 不写入白名单

    with pytest.raises(AuthError) as exc:
        await refresh_access_token(db_session, fake_redis, tokens["refresh_token"])
    assert "已失效" in exc.value.message


# ---------------------------------------------------------------------------
# logout_user
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_logout_user(client, fake_redis):
    """登出应写入黑名单并清除白名单"""
    await save_token_whitelist(fake_redis, 1, "jti-a")
    await save_token_whitelist(fake_redis, 1, "jti-b")

    await logout_user(fake_redis, "access-jti", 1)

    # 黑名单
    assert await fake_redis.exists("token_blacklist:access-jti") == 1
    # 白名单应被清除
    assert await fake_redis.exists("token_whitelist:1:jti-a") == 0
    assert await fake_redis.exists("token_whitelist:1:jti-b") == 0


# ---------------------------------------------------------------------------
# record_login_log
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_record_login_log(client, db_session):
    """应创建登录日志记录"""
    await record_login_log(
        db_session,
        user_id=1,
        username="testuser",
        login_type="password",
        ip="192.168.1.1",
        ua_string="Mozilla/5.0 (Windows NT 10.0)",
        status="success",
    )
    from app.models.user import LoginLog
    from sqlalchemy import select

    result = await db_session.execute(select(LoginLog))
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].username == "testuser"
    assert logs[0].status == "success"
    assert logs[0].ip_address == "192.168.1.1"
