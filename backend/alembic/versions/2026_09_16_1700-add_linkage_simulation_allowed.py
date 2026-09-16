"""linkage_plans 补 is_simulation_allowed 列

Revision ID: add_linkage_simulation_allowed
Revises: drill_eval_constraints
Create Date: 2026-09-16 17:00:00.000000+08:00

## 为什么需要

`linkage_plans.is_simulation_allowed`（「允许模拟测试」）**在两条建表路径上
只有一条会产出它**，而线上走的是不产出的那条：

- `xxx_linkage_tables.py:34` 声明了该列（`Boolean, NOT NULL, DEFAULT 'true'`），
  但那条迁移在 docker-compose 的实际启动顺序里**根本不会执行**：
  `scripts/entrypoint.sh` 先跑 `init_data.py`，后者按 ORM 模型
  `Base.metadata.create_all()` 建表 —— 而模型里没有这个字段；
  随后 uvicorn 启动时 `main.py:_try_alembic_upgrade` 执行 `alembic upgrade head`
  撞上「表已存在」失败，被 `_try_alembic_stamp_head` **直接 stamp 到 head**，
  于是整条迁移链（含 `xxx_linkage_tables`）被跳过。
- `scripts/sql/init_post_baseline.sql:12` 也有该列，但那个文件全仓库无任何引用，
  是份手工快照。

结果：列在「迁移建库」的机器上存在、在「容器拉起」的机器上不存在，
而应用侧从模型/schema 读它——两边对不上。前端「允许模拟测试」开关因此
从落地起就是死的（存不进去也读不出来）。

## 本迁移的形状

按名字查 `information_schema`，**缺才加**。因为该列可能已经存在
（手工跑过 `xxx_linkage_tables` 或 `init_post_baseline.sql` 的库），
无条件 `ADD COLUMN` 会直接报「列已存在」而中断启动，
而迁移是在应用启动时自动执行的（`app/main.py:_try_alembic_upgrade`），
那种失败很难排查。
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = 'add_linkage_simulation_allowed'
down_revision: Union[str, None] = 'drill_eval_constraints'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 缺列才加：该列在部分库中已由 xxx_linkage_tables / init_post_baseline.sql 建出
_ADD_COLUMN_IF_MISSING = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'linkage_plans'
          AND column_name = 'is_simulation_allowed'
    ) THEN
        ALTER TABLE linkage_plans
            ADD COLUMN is_simulation_allowed BOOLEAN NOT NULL DEFAULT true;
    END IF;
END $$;
"""


def upgrade() -> None:
    """补 `is_simulation_allowed` 列（已存在则跳过）。"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # 测试环境用 SQLite，schema 由 `Base.metadata.create_all` 从模型生成
        # （见 tests/conftest.py），迁移不参与。
        return

    op.execute(_ADD_COLUMN_IF_MISSING)


def downgrade() -> None:
    """去掉该列。

    ⚠️ 会丢失「哪些预案禁用了模拟测试」的配置，且前端表单仍会提交该字段
    （被 Pydantic 静默丢弃），表现为开关失灵。
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE linkage_plans DROP COLUMN IF EXISTS is_simulation_allowed")
