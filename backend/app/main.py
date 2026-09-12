"""
FastAPI 应用入口
消防监控管理系统 - 后端服务
"""

from contextlib import asynccontextmanager
from typing import Optional
import os
import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import router as api_v1_router
from app.api.v1.emergency_events import router as emergency_router
from app.api.v1.notifications import router as notification_router
from app.api.ws_devices import router as ws_router
from app.core.config import get_settings
from app.core.exceptions import AuthError, NotFoundError
import traceback
import time
from app.db.redis import close_redis_pool, get_redis_pool
from app.services import ws_broadcaster
from app.services.emergency_service import EmergencyEscalationTask
from app.services.map_image_service import map_image_dir
from app.tasks import offline_monitor
from app.ws.connection_manager import manager

settings = get_settings()
escalation_task: Optional[EmergencyEscalationTask] = None  # 超时升级后台任务


from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


def _try_alembic_upgrade() -> bool:
    """在线程中执行 Alembic upgrade。
    返回 True=成功，False=因表已存在失败（可安全降级处理）。
    """
    from alembic.config import Config
    from alembic import command
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_ini = os.path.join(backend_dir, "alembic.ini")
    alembic_cfg = Config(alembic_ini)
    command.upgrade(alembic_cfg, "head")
    print("[START] Database migrations applied successfully")
    return True


def _try_alembic_stamp_head() -> None:
    """在线程中执行 Alembic stamp head，跳过所有迁移脚本。"""
    from alembic.config import Config
    from alembic import command
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_ini = os.path.join(backend_dir, "alembic.ini")
    alembic_cfg = Config(alembic_ini)
    command.stamp(alembic_cfg, "head")


async def _ensure_database_schema() -> None:
    """应用启动时确保数据库表结构完整。
    - 全新空库：Alembic upgrade head 正常创建所有表
    - 存量脏库（表已存在但 alembic_version 缺失）：stamp head + SQLAlchemy create_all 补齐
    """
    import traceback
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.models.base import Base
    import app.models  # noqa: F401 — 确保所有模型注册到 Base.metadata

    engine = create_async_engine(settings.database_url_async)

    try:
        # 1. 先尝试标准 Alembic upgrade（在线程中执行，避免与 lifespan 事件循环冲突）
        alembic_ok = False
        try:
            alembic_ok = await asyncio.to_thread(_try_alembic_upgrade)
        except Exception as upgrade_exc:
            if "already exists" in str(upgrade_exc) or "DuplicateTableError" in str(upgrade_exc):
                alembic_ok = False
            else:
                raise

        if not alembic_ok:
            # 2. 存量库场景：直接 stamp head 跳过全部迁移脚本
            print("[WARN] Existing tables block Alembic. Stamping head + SQLAlchemy create_all...")
            await asyncio.to_thread(_try_alembic_stamp_head)

            # 3. 用 SQLAlchemy 幂等地补齐缺失表（checkfirst=True 会跳过已存在的表）
            async with engine.begin() as conn:
                def _create_all(sync_conn):
                    Base.metadata.create_all(sync_conn, checkfirst=True)
                await conn.run_sync(_create_all)
            print("[START] Database schema ensured (stamp head + create_all)")
    except Exception as exc:
        traceback_str = traceback.format_exc()
        print(f"[WARN] Database setup failed: {exc}\n{traceback_str}")
    finally:
        await engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} started")

    # 自动确保数据库表结构完整（首次启动或存量脏库都能自愈）
    await _ensure_database_schema()

    offline_monitor.start()
    
    # P2-008：eager 启动 WS 扇出消费者，确保多 worker 下每个进程都消费全量消息
    try:
        redis = await get_redis_pool()
        await ws_broadcaster.ensure_running(redis)
        print(f"[START] ws broadcaster started (group={ws_broadcaster.group_name()})")
    except Exception as exc:
        print(f"[WARN] ws broadcaster failed to start: {exc}")
    
    # 3.5-B3: 启动 5 分钟超时升级扫描任务（每 60 秒一次）
    global escalation_task
    engine = create_async_engine(settings.database_url_async)
    escalation_task = EmergencyEscalationTask(interval_seconds=60)
    await escalation_task.start(engine)
    print("[START] Emergency escalation scan task started (60s interval)")
    
    yield
    
    # 关闭时执行：先停推送扇出与心跳，再释放连接与 Redis
    await offline_monitor.stop()
    if escalation_task:
        await escalation_task.stop()
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
app.include_router(emergency_router, prefix="/api/v1")
app.include_router(notification_router, prefix="/api/v1")

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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局兜底异常处理：捕获所有未处理异常，确保返回 JSON 并携带 CORS 头"""
    traceback_str = traceback.format_exc()
    print(f"[ERROR] Unhandled exception: {exc}\n{traceback_str}")
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": f"服务器内部错误: {str(exc)}",
            "data": None,
            "timestamp": int(time.time()),
        },
    )


@app.get("/health", tags=["健康检查"])
async def health_check():
    """健康检查接口"""
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "ws_connections": manager.count,
        "ws_broadcaster": "running" if ws_broadcaster.is_running() else "stopped",
    }
