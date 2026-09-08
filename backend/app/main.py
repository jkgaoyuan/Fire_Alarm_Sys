"""
FastAPI 应用入口
消防监控管理系统 - 后端服务
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import router as api_v1_router
from app.core.config import get_settings
from app.core.exceptions import AuthError
from app.db.redis import close_redis_pool

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} started")
    yield
    # 关闭时执行
    await close_redis_pool()
    print("[STOP] Application shutdown")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="消防监控管理系统 RESTful API",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# CORS 中间件（允许前端开发服务器 localhost:5173）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(api_v1_router, prefix="/api/v1")


@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError):
    """统一认证异常响应格式"""
    if exc.code == 403:
        status_code = 403
    elif exc.code in (400, 4001, 4003, 4004):
        status_code = 400
    else:
        status_code = 401
    return JSONResponse(
        status_code=status_code,
        content=exc.to_dict(),
    )


@app.get("/health", tags=["健康检查"])
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "version": settings.APP_VERSION}
