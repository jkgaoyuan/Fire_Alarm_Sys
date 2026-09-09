"""
FastAPI 应用入口
消防监控管理系统 - 后端服务
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import router as api_v1_router
from app.api.ws_devices import router as ws_router
from app.core.config import get_settings
from app.core.exceptions import AuthError, NotFoundError
from app.db.redis import close_redis_pool, get_redis_pool
from app.services import ws_broadcaster
from app.services.map_image_service import map_image_dir
from app.tasks import offline_monitor
from app.ws.connection_manager import manager

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} started")
    offline_monitor.start()
    # P2-008：eager 启动 WS 扇出消费者，确保多 worker 下每个进程都消费全量消息
    try:
        redis = await get_redis_pool()
        await ws_broadcaster.ensure_running(redis)
        print(f"[START] ws broadcaster started (group={ws_broadcaster.group_name()})")
    except Exception as exc:
        print(f"[WARN] ws broadcaster failed to start: {exc}")
    yield
    # 关闭时执行：先停推送扇出与心跳，再释放连接与 Redis
    await offline_monitor.stop()
    await ws_broadcaster.shutdown()
    await manager.stop_heartbeat()
    await manager.close_all()
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

# WebSocket 路由不带 /api/v1 前缀（PRD FR-013 固定地址 /ws/devices）
app.include_router(ws_router)

# 平面图静态目录（计划 六.6：仅匿名读，图片不含敏感数据）
app.mount("/static/maps", StaticFiles(directory=str(map_image_dir())), name="map-images")


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


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError):
    """业务 404：HTTP 保持 200，由统一响应体 code 表达（与 3.2 接口口径一致）"""
    return JSONResponse(status_code=200, content=exc.to_dict())


@app.get("/health", tags=["健康检查"])
async def health_check():
    """健康检查接口"""
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "ws_connections": manager.count,
        "ws_broadcaster": "running" if ws_broadcaster.is_running() else "stopped",
    }
