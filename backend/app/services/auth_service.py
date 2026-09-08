"""
认证服务层
登录逻辑 / Token 管理 / 锁定检测 / 登录日志
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from user_agents import parse

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.exceptions import AccountLocked, AuthError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import LoginLog, User

settings = get_settings()


def _now_utc() -> datetime:
    """获取当前 UTC 时间"""
    return datetime.now(timezone.utc)


def is_account_locked(user: User) -> bool:
    """检查账户是否处于锁定状态"""
    if user.status == "locked" and user.locked_until:
        if user.locked_until > _now_utc():
            return True
        # 锁定期已过，自动解锁
        user.status = "active"
        user.locked_until = None
        user.login_fail_count = 0
    return False


def _parse_user_agent(ua_string: str | None) -> tuple[str, str, str]:
    """解析 User-Agent，返回 (device_type, device_os, browser)"""
    if not ua_string:
        return "Unknown", "Unknown", "Unknown"
    try:
        ua = parse(ua_string)
        if ua.is_mobile:
            device_type = "mobile"
        elif ua.is_tablet:
            device_type = "tablet"
        else:
            device_type = "desktop"
        device_os = ua.os.family or "Unknown"
        browser = ua.browser.family or "Unknown"
        return device_type, device_os, browser
    except Exception:
        return "Unknown", "Unknown", "Unknown"


async def record_login_log(
    db: AsyncSession,
    user_id: int | None,
    username: str | None,
    login_type: str,
    ip: str | None,
    ua_string: str | None,
    status: str,
    fail_reason: str | None = None,
) -> None:
    """记录登录日志"""
    device_type, device_os, browser = _parse_user_agent(ua_string)
    log = LoginLog(
        user_id=user_id,
        username=username,
        login_type=login_type,
        ip_address=ip,
        user_agent=ua_string,
        device_type=device_type,
        device_os=device_os,
        browser=browser,
        status=status,
        fail_reason=fail_reason,
    )
    db.add(log)
    await db.commit()


async def _get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """根据用户名查询用户（预加载角色）"""
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.username == username)
    )
    return result.scalar_one_or_none()


async def authenticate_user(
    db: AsyncSession,
    username: str,
    password: str,
) -> User | None:
    """
    校验用户凭据
    - 成功返回 User 对象
    - 用户不存在 / 密码错误返回 None
    - 账户锁定 / 禁用抛出异常
    """
    user = await _get_user_by_username(db, username)
    if not user:
        return None

    # 检查禁用
    if user.status == "disabled":
        raise AuthError(4004, "账户已禁用")

    # 检查锁定
    if is_account_locked(user):
        raise AccountLocked(user.locked_until)

    # 密码校验
    if not verify_password(password, user.password_hash):
        return None

    return user


async def _handle_login_failure(
    db: AsyncSession,
    user: User,
) -> None:
    """处理登录失败：递增失败计数，必要时锁定账户"""
    user.login_fail_count += 1

    if user.login_fail_count >= settings.MAX_LOGIN_FAILS:
        locked_until = _now_utc() + timedelta(minutes=settings.LOCK_DURATION_MINUTES)
        user.locked_until = locked_until
        user.status = "locked"

    await db.commit()


async def create_token_pair(user: User) -> dict:
    """
    生成双 Token 对
    返回包含 access_token / refresh_token / jti / refresh_jti 的字典
    """
    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())

    access_token = create_access_token(
        data={"sub": str(user.id), "jti": access_jti},
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "jti": refresh_jti},
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "jti": access_jti,
        "refresh_jti": refresh_jti,
    }


async def save_token_whitelist(
    redis: aioredis.Redis,
    user_id: int,
    refresh_jti: str,
) -> None:
    """将 Refresh Token JTI 写入 Redis 白名单"""
    key = f"token_whitelist:{user_id}:{refresh_jti}"
    # 有效期与 Refresh Token 一致（7 天）
    expire_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await redis.set(key, "1", ex=expire_seconds)


async def login_user(
    db: AsyncSession,
    redis: aioredis.Redis,
    username: str,
    password: str,
    ip: str | None,
    ua_string: str | None,
) -> dict:
    """
    完整登录流程
    - 查用户 → 校验状态 → bcrypt 校验 → 失败计数/清零 → 生成双 Token → 写入 Redis 白名单 → 记录日志
    返回 Token 字典（含 access_token / refresh_token）
    """
    # 1. 认证
    try:
        user = await authenticate_user(db, username, password)
    except AccountLocked as exc:
        await record_login_log(
            db, None, username, "password", ip, ua_string,
            status="locked", fail_reason="account_locked",
        )
        raise exc
    except AuthError as exc:
        await record_login_log(
            db, None, username, "password", ip, ua_string,
            status="fail", fail_reason="account_disabled",
        )
        raise exc

    if user is None:
        # 密码错误：查用户并递增失败计数
        user_for_count = await _get_user_by_username(db, username)
        if user_for_count and user_for_count.status != "disabled":
            await _handle_login_failure(db, user_for_count)
            remaining = settings.MAX_LOGIN_FAILS - user_for_count.login_fail_count
            if remaining <= 0:
                raise AccountLocked(user_for_count.locked_until)
            raise AuthError(
                4001,
                "密码错误",
                {"remaining_attempts": remaining},
            )
        raise AuthError(4001, "密码错误", {"remaining_attempts": 0})

    # 2. 登录成功：清零失败计数、更新时间/IP
    user.login_fail_count = 0
    user.locked_until = None
    user.status = "active"
    user.last_login_at = _now_utc()
    user.last_login_ip = ip
    await db.commit()

    # 3. 生成 Token
    tokens = await create_token_pair(user)

    # 4. 写入 Redis 白名单
    await save_token_whitelist(redis, user.id, tokens["refresh_jti"])

    # 5. 记录登录日志
    await record_login_log(
        db, user.id, user.username, "password", ip, ua_string,
        status="success",
    )

    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "jti": tokens["jti"],
        "refresh_jti": tokens["refresh_jti"],
        "user": {
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "roles": [r.role_code for r in user.roles],
        },
    }


async def refresh_access_token(
    db: AsyncSession,
    redis: aioredis.Redis,
    refresh_token: str,
) -> dict:
    """
    刷新 Access Token
    - 校验 Refresh Token 签名
    - 校验 Redis 白名单
    - 生成新的 Access Token
    返回 {"access_token": ..., "expires_in": 3600}
    """
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AuthError(401, "Refresh Token 无效或已过期")

    user_id_str = payload.get("sub")
    refresh_jti = payload.get("jti")
    if not user_id_str or not refresh_jti:
        raise AuthError(401, "Refresh Token 格式错误")

    user_id = int(user_id_str)

    # 校验白名单
    whitelist_key = f"token_whitelist:{user_id}:{refresh_jti}"
    if not await redis.exists(whitelist_key):
        raise AuthError(401, "Refresh Token 已失效")

    # 查用户状态
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.status == "disabled":
        raise AuthError(401, "用户不存在或已禁用")

    # 生成新 Access Token（JTI 复用原 refresh_jti 关联，或新生成一个）
    new_access_jti = str(uuid.uuid4())
    access_token = create_access_token(
        data={"sub": str(user.id), "jti": new_access_jti},
    )

    return {
        "access_token": access_token,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


async def logout_user(
    redis: aioredis.Redis,
    access_token_jti: str,
    user_id: int,
) -> None:
    """
    用户登出
    - Access Token 加入黑名单（有效期与 Token 剩余时间一致，简化处理为 1 小时）
    - 删除该用户的所有 Redis 白名单记录
    """
    # Access Token 黑名单
    blacklist_key = f"token_blacklist:{access_token_jti}"
    await redis.set(blacklist_key, "1", ex=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    # 删除该用户的所有白名单
    pattern = f"token_whitelist:{user_id}:*"
    async for key in redis.scan_iter(match=pattern):
        await redis.delete(key)
