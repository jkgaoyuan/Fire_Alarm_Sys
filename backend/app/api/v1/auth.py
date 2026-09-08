"""
认证 API 路由
POST /auth/login    登录
POST /auth/refresh  刷新 Access Token（从 Cookie 读取 Refresh Token）
POST /auth/logout   登出
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.core.exceptions import AuthError
from app.core.security import decode_token
from app.db.redis import get_redis_pool
from app.db.session import get_db
from app.schemas.auth import LoginRequest
from app.services.auth_service import login_user, logout_user, refresh_access_token

router = APIRouter()
security = HTTPBearer(auto_error=False)


def _get_client_ip(request: Request) -> str | None:
    """获取客户端真实 IP（优先 X-Forwarded-For）"""
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis_pool),
):
    """用户登录：返回 TokenResponse，并通过 Set-Cookie 下发 Refresh Token"""
    try:
        tokens = await login_user(
            db=db,
            redis=redis,
            username=payload.username,
            password=payload.password,
            ip=_get_client_ip(request),
            ua_string=request.headers.get("User-Agent"),
        )
    except AuthError:
        raise

    # 设置 httpOnly Cookie（Refresh Token）
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=604800,  # 7 天
        path="/",
    )

    return {
        "code": 200,
        "message": "登录成功",
        "data": {
            "access_token": tokens["access_token"],
            "token_type": "bearer",
            "expires_in": 3600,
            "user": tokens["user"],
        },
    }


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis_pool),
):
    """
    刷新 Access Token
    前端不携带任何 Token 请求头，由浏览器自动通过 httpOnly Cookie 发送 refresh_token
    """
    if not refresh_token:
        raise AuthError(
            401,
            "缺少 Refresh Token",
        )

    try:
        result = await refresh_access_token(db, redis, refresh_token)
    except AuthError:
        raise

    return {
        "code": 200,
        "message": "刷新成功",
        "data": result,
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    redis: aioredis.Redis = Depends(get_redis_pool),
):
    """
    用户登出
    - Access Token 通过 Authorization: Bearer 头传递
    - 后端清除 Refresh Token Cookie
    """
    if not credentials:
        raise AuthError(401, "未提供 Access Token")

    access_token = credentials.credentials
    payload = decode_token(access_token)
    if not payload:
        raise AuthError(401, "Access Token 无效")

    user_id_str = payload.get("sub")
    jti = payload.get("jti")
    if not user_id_str or not jti:
        raise AuthError(401, "Token 格式错误")

    await logout_user(redis, jti, int(user_id_str))

    # 清除 Refresh Token Cookie
    response.set_cookie(
        key="refresh_token",
        value="",
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=0,
        path="/",
    )

    return {
        "code": 200,
        "message": "登出成功",
        "data": None,
    }
