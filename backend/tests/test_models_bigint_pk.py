"""
跨库主键类型（P1-013）测试

emergency 域三张表用 `Column(BigInteger, primary_key=True, autoincrement=True)`，
而 SQLite **只对 `INTEGER PRIMARY KEY` 自增，`BIGINT PRIMARY KEY` 不自增** ——
测试环境（sqlite+aiosqlite，见 conftest）插任何一行都报
`NOT NULL constraint failed: <table>.id`，导致 notifications / emergency 两域
共 23 条用例恒红、实际零覆盖。

`bigint_pk()` 按方言降级：SQLite 见 `INTEGER` 即自增，PostgreSQL 仍是 `BIGINT`
（走 sequence，行为不变）——因此**只改测试环境 DDL，生产 schema 零变化、无需迁移**。

这与 `json_type()` 是同一类问题的同一个解法，两者同属 models/types.py。
"""

import pytest
from sqlalchemy import Column, MetaData, Table
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from app.models.emergency import EmergencyEvent, EmergencyTimeline, Notification
from app.models.types import bigint_pk


def _column_ddl(dialect) -> str:
    """把单列建表语句渲染成目标方言的 DDL 文本"""
    table = Table("t", MetaData(), Column("id", bigint_pk(), primary_key=True))
    return str(CreateTable(table).compile(dialect=dialect))


def test_bigint_pk_renders_integer_on_sqlite():
    """SQLite 下必须是 INTEGER —— 这是主键能自增的唯一前提"""
    ddl = _column_ddl(sqlite.dialect())
    assert "INTEGER" in ddl
    assert "BIGINT" not in ddl


def test_bigint_pk_stays_64bit_on_postgresql():
    """
    生产 PostgreSQL 仍是 64 位自增主键 —— 不得被降级成 32 位的 SERIAL。

    BigInteger 自增主键在 PG 上渲染为 BIGSERIAL（bigint + sequence），
    所以判 BIGSERIAL 而不是 BIGINT；若误降级为 Integer 则渲染成 SERIAL，
    这条断言会红。
    """
    ddl = _column_ddl(postgresql.dialect())
    assert "BIGSERIAL" in ddl


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(
            lambda: EmergencyEvent(alarm_id=1, event_no="EV-20260101-001", created_by=1),
            id="emergency_events",
        ),
        pytest.param(
            lambda: EmergencyTimeline(event_id=1, node_type="alarm"),
            id="emergency_timelines",
        ),
        pytest.param(
            lambda: Notification(user_id=1, title="火警待确认升级通知"),
            id="notifications",
        ),
    ],
)
async def test_emergency_domain_rows_persist_without_explicit_id(db_session, build):
    """
    P1-013 的行为面：三张表都要能在不给显式 id 的情况下落库。

    这条用例是整个 emergency / notifications 域的地基 —— 它红了，那两个域
    的任何断言都跑不到。
    """
    row = build()
    db_session.add(row)
    await db_session.commit()

    assert row.id is not None
