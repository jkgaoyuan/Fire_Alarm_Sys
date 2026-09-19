"""
跨数据库兼容列类型

生产环境为 PostgreSQL，测试环境为 SQLite（见 tests/conftest.py 的 sqlite+aiosqlite:///:memory:）。
JSONB 在 SQLite 上不可用，需 with_variant 降级。
"""

from sqlalchemy import JSON, BigInteger, Integer
from sqlalchemy.dialects.postgresql import JSONB


def json_type() -> JSON:
    """PostgreSQL 使用 JSONB（支持索引与 GIN），SQLite 降级为 JSON"""
    return JSONB().with_variant(JSON(), "sqlite")


def bigint_pk() -> BigInteger:
    """
    自增主键类型：PostgreSQL 用 BIGINT（BIGSERIAL + sequence），SQLite 降级为 INTEGER。

    SQLite 只对 `INTEGER PRIMARY KEY` 自增，`BIGINT PRIMARY KEY` **不自增**，
    插入即报 `NOT NULL constraint failed: <table>.id`；PG 则不受影响。
    降级只发生在测试环境，生产 schema 一字不变（无迁移）。
    """
    return BigInteger().with_variant(Integer, "sqlite")
