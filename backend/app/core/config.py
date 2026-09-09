"""
应用配置管理
使用 Pydantic Settings 从环境变量读取配置
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类"""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用基础配置
    APP_NAME: str = "消防监控管理系统"
    APP_VERSION: str = "1.0.0"
    ENV: str = "development"
    DEBUG: bool = True

    # 数据库配置
    DATABASE_URL: str = "postgresql+asyncpg://fire:fire@localhost:5432/fire_alarm_sys"

    # Redis 配置
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT 配置
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 安全配置
    MAX_LOGIN_FAILS: int = 5
    LOCK_DURATION_MINUTES: int = 30

    # 实时监控与报警（3.3）
    OFFLINE_THRESHOLD_SECONDS: int = 180  # 超过该时长未上报即判定 offline
    OFFLINE_SCAN_INTERVAL_SECONDS: int = 60
    OFFLINE_SCAN_ENABLED: bool = True  # 关闭后仅按需手动调用 scan_once()
    ALLOW_DEVICE_REPORT: bool = False  # 设备上报端点开关，生产默认关闭
    DEVICE_REPORT_KEY: str = ""  # X-Device-Key 预共享凭据
    WS_STREAM_KEY: str = "ws:devices:stream"
    WS_STREAM_MAXLEN: int = 100000
    WS_STREAM_GROUP: str = "ws-fanout"
    WS_TICKET_TTL_SECONDS: int = 60
    WS_HEARTBEAT_SECONDS: int = 30  # PRD FR-013 心跳间隔
    WS_REPLAY_LIMIT: int = 500  # 补发条数上限，超出则要求前端全量刷新
    ALARM_DEDUP_WINDOW_SECONDS: int = 0  # 0 表示按「同设备同类型未收敛」去重，不限时窗

    # 平面图与文件存储（3.3 FR-015，MinIO 接入前的本地卷方案）
    STORAGE_DIR: str = "storage"
    MAP_IMAGE_MAX_WIDTH: int = 2000  # 超宽等比压缩阈值
    MAP_IMAGE_JPEG_QUALITY: int = 80
    MAX_UPLOAD_SIZE_MB: int = 10

    # CORS 配置（开发环境）
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    @property
    def database_url_async(self) -> str:
        """确保使用异步驱动"""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
