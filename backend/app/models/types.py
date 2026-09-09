"""
跨数据库兼容列类型

生产环境为 PostgreSQL，测试环境为 SQLite（见 tests/conftest.py 的 sqlite+aiosqlite:///:memory:）。
JSONB 在 SQLite 上不可用，需 with_variant 降级。
"""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB


def json_type() -> JSON:
    """PostgreSQL 使用 JSONB（支持索引与 GIN），SQLite 降级为 JSON"""
    return JSONB().with_variant(JSON(), "sqlite")
