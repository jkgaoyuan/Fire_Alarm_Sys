"""align drill tables with the ORM model / API code

Revision ID: align_drill_columns
Revises: add_inspection_task_plan_date_uq
Create Date: 2026-09-16 10:00:00.000000+08:00

## 为什么需要这个迁移

`drill_events` / `drill_evaluations` 存在**三方漂移**，且 `alembic_version`
在此并不可信（它显示 `create_drill_tables` 已应用，但线上库的形状并非该迁移
所创建 —— 实际是 `Base.metadata.create_all` 按 ORM 模型建的）：

| | drill_events | drill_evaluations |
|---|---|---|
| **线上库（= 旧 ORM 模型）** | `actual_at`、`updated_by`；**缺** actual_start_at / actual_end_at / summary / photos / videos | `evaluated_by`；**缺** total_score |
| **API 代码 / schemas / 前端** | 使用 actual_start_at / actual_end_at / summary / photos / videos | 使用 evaluator_id / total_score |
| **`create_drill_tables` 迁移** | 与「API 代码」一致 | 与「API 代码」一致 |

后果：`POST /drills` 在生产环境必然 500（`AttributeError: 'DrillEvent' object
has no attribute 'actual_start_at'`），「新增消防演练」整条链路不可用；
`GET /drills/statistics` 同样 500。

## 本迁移的形状

**代码是对的，库是旧的**，所以本迁移把库向代码看齐，并保留 PRD 要求的
现场总结 / 照片 / 视频 / 评估总分（FR-030）。

**必须对两种形态都幂等**：线上库是旧形状（需要 rename），而一台干净机器
跑完 `create_drill_tables` 之后已是目标形状（rename 必须跳过）。
所以全部用 `information_schema` 条件判断 + `ADD COLUMN IF NOT EXISTS`。

**不删 `updated_by`**：它已无任何 ORM/迁移引用，但删列不可逆且无功能收益，
留作遗留列。`actual_at` 是 **rename** 而非删建，以保住其中可能已有的数据。
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = 'align_drill_columns'
down_revision: Union[str, None] = 'add_inspection_task_plan_date_uq'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# `information_schema` 守卫：仅当旧列存在且新列不存在时才改名。
# 两个条件都要，否则在已是目标形状的库上会因「目标列已存在」而报错。
_RENAME_ACTUAL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = 'drill_events' AND column_name = 'actual_at')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_schema = current_schema()
                         AND table_name = 'drill_events' AND column_name = 'actual_start_at')
    THEN
        ALTER TABLE drill_events RENAME COLUMN actual_at TO actual_start_at;
    END IF;
END $$;
"""

_RENAME_EVALUATOR = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = 'drill_evaluations' AND column_name = 'evaluated_by')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_schema = current_schema()
                         AND table_name = 'drill_evaluations' AND column_name = 'evaluator_id')
    THEN
        ALTER TABLE drill_evaluations RENAME COLUMN evaluated_by TO evaluator_id;
    END IF;
END $$;
"""

_REVERT_ACTUAL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = 'drill_events' AND column_name = 'actual_start_at')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_schema = current_schema()
                         AND table_name = 'drill_events' AND column_name = 'actual_at')
    THEN
        ALTER TABLE drill_events RENAME COLUMN actual_start_at TO actual_at;
    END IF;
END $$;
"""

_REVERT_EVALUATOR = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = 'drill_evaluations' AND column_name = 'evaluator_id')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_schema = current_schema()
                         AND table_name = 'drill_evaluations' AND column_name = 'evaluated_by')
    THEN
        ALTER TABLE drill_evaluations RENAME COLUMN evaluator_id TO evaluated_by;
    END IF;
END $$;
"""


def upgrade() -> None:
    """把 drill 两表补齐到 ORM 模型 / API 代码使用的形状（幂等）。"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # 测试环境用 SQLite，schema 由 `Base.metadata.create_all` 从模型直接生成
        # （见 tests/conftest.py），迁移不参与构建，故此处无事可做。
        return

    # --- drill_events：把旧列改名，并补齐代码使用的 4 列 ---
    op.execute(_RENAME_ACTUAL)

    op.execute(
        "ALTER TABLE drill_events "
        "ADD COLUMN IF NOT EXISTS actual_end_at TIMESTAMP WITHOUT TIME ZONE"
    )
    op.execute("ALTER TABLE drill_events ADD COLUMN IF NOT EXISTS summary TEXT")
    op.execute("ALTER TABLE drill_events ADD COLUMN IF NOT EXISTS photos JSON")
    op.execute("ALTER TABLE drill_events ADD COLUMN IF NOT EXISTS videos JSON")

    # --- drill_evaluations：同样改名 + 补 total_score ---
    op.execute(_RENAME_EVALUATOR)
    op.execute(
        "ALTER TABLE drill_evaluations "
        "ADD COLUMN IF NOT EXISTS total_score INTEGER"
    )


def downgrade() -> None:
    """回退到旧形状。

    只回退本迁移引入的改动：改回列名、删掉新增列。
    `updated_by` 未被本迁移触碰，故不涉及。
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(_REVERT_ACTUAL)
    op.execute("ALTER TABLE drill_events DROP COLUMN IF EXISTS actual_end_at")
    op.execute("ALTER TABLE drill_events DROP COLUMN IF EXISTS summary")
    op.execute("ALTER TABLE drill_events DROP COLUMN IF EXISTS photos")
    op.execute("ALTER TABLE drill_events DROP COLUMN IF EXISTS videos")

    op.execute(_REVERT_EVALUATOR)
    op.execute("ALTER TABLE drill_evaluations DROP COLUMN IF EXISTS total_score")
