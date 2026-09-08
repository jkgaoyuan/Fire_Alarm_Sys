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
