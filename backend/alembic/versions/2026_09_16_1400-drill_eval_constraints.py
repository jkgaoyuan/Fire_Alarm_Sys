"""add drill_evaluations constraints: unique drill_id + ON DELETE CASCADE FK

Revision ID: drill_eval_constraints
Revises: align_drill_columns
Create Date: 2026-09-16 14:00:00.000000+08:00

## 为什么需要

`drill_evaluations` 在线上库**只有主键**，`create_drill_tables` 里声明的唯一约束与
外键**一个都不存在**（表实际由 `Base.metadata.create_all` 按 ORM 模型建的，
该迁移并未真正建表 —— 见 `align_drill_columns` 的说明）。缺这两条各自导致：

**① 缺 `drill_id` 唯一约束 → 一条竞态窗口能把演练详情页永久打死。**
应用层有守卫（`drill_service.submit_evaluation` 先查后建 → 400），但那是
check-then-act、数据库没有兜底。而读侧 `eval_crud.get_by_drill_id` 用的是
`scalar_one_or_none()` —— 两行同 `drill_id` 会抛 `MultipleResultsFound`，于是
`GET /drills/{id}`、`GET /drills/{id}/evaluation`、连 `POST /drills/evaluation`
全部 500，而**界面上没有任何删除评估的入口**（`eval_crud.delete` 定义了但零调用方），
只能进库手动删行。

**② 缺 `ON DELETE CASCADE` 外键 → 删演练留下孤儿评估，污染统计。**
`drill_crud.delete` 的 docstring 声称「ORM 级联删除评估」，但模型里原本没有
relationship；而 `get_stats` 的 `avg(total_score)` **不 join 演练表**，
已删除演练的评分继续计入平均分。前端删演练的确认框还写着
「会级联删除评估数据」—— 对用户的承诺与实际不符。

## 本迁移的形状

**必须让两条来源收敛到同一个 schema**：线上库两条都没有（要新增），
而干净机器跑完 `create_drill_tables` 后**唯一约束已存在、外键存在但不带级联**
（要替换）。因此：

- 唯一约束：按名字判存在，缺则加
- 外键：按「`drill_id` 列上的外键」查出来，**缺失则加、存在但 `confdeltype <> 'c'`
  则先 DROP 再按级联版重建** —— 否则干净机器上外键不级联，两条路径结果不一致
- 外键名刻意用 `drill_evaluations_drill_id_fkey`（Postgres 对未命名外键的默认名），
  两条路径因此收敛到同一个名字
- 加外键前**显式检查孤儿行**并抛出可读错误。孤儿会让 `ALTER TABLE ADD FOREIGN KEY`
  失败，而应用启动时会自动 `alembic upgrade head`（`app/main.py:_try_alembic_upgrade`），
  一个隐晦的约束冲突在那里很难排查
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = 'drill_eval_constraints'
down_revision: Union[str, None] = 'align_drill_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 加外键前先确认没有孤儿：有的话报一个能看懂的错，而不是让 Postgres 抛约束名
_ORPHAN_CHECK = """
DO $$
DECLARE orphan_count int;
BEGIN
    SELECT count(*) INTO orphan_count
    FROM drill_evaluations e
    LEFT JOIN drill_events d ON d.id = e.drill_id
    WHERE d.id IS NULL;

    IF orphan_count > 0 THEN
        RAISE EXCEPTION
            'drill_evaluations 有 % 行 drill_id 指向不存在的演练，无法建立外键。'
            '请先清理这些孤儿行（它们来自「删除演练未级联删评估」的历史缺陷），再重跑本迁移。',
            orphan_count;
    END IF;
END $$;
"""

_ADD_UNIQUE = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'drill_evaluations'::regclass
          AND contype = 'u'
          AND conname = 'uq_drill_evaluations_drill_id'
    ) THEN
        ALTER TABLE drill_evaluations
            ADD CONSTRAINT uq_drill_evaluations_drill_id UNIQUE (drill_id);
    END IF;
END $$;
"""

# 收敛外键到「带 ON DELETE CASCADE」：缺失则加，存在但不级联则替换
_ADD_CASCADE_FK = """
DO $$
DECLARE
    cname text;
    deltype char;
BEGIN
    SELECT c.conname, c.confdeltype INTO cname, deltype
    FROM pg_constraint c
    JOIN pg_attribute a
      ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
    WHERE c.conrelid = 'drill_evaluations'::regclass
      AND c.contype = 'f'
      AND a.attname = 'drill_id'
    LIMIT 1;

    IF cname IS NULL THEN
        ALTER TABLE drill_evaluations
            ADD CONSTRAINT drill_evaluations_drill_id_fkey
            FOREIGN KEY (drill_id) REFERENCES drill_events (id) ON DELETE CASCADE;
    ELSIF deltype <> 'c' THEN
        -- 来自 create_drill_tables（未命名 → 默认名，且不带级联）
        EXECUTE format('ALTER TABLE drill_evaluations DROP CONSTRAINT %I', cname);
        ALTER TABLE drill_evaluations
            ADD CONSTRAINT drill_evaluations_drill_id_fkey
            FOREIGN KEY (drill_id) REFERENCES drill_events (id) ON DELETE CASCADE;
    END IF;
END $$;
"""

_DROP_CASCADE_FK_AND_RESTORE = """
DO $$
DECLARE cname text;
BEGIN
    SELECT c.conname INTO cname
    FROM pg_constraint c
    JOIN pg_attribute a
      ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
    WHERE c.conrelid = 'drill_evaluations'::regclass
      AND c.contype = 'f'
      AND a.attname = 'drill_id'
    LIMIT 1;

    IF cname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE drill_evaluations DROP CONSTRAINT %I', cname);
        -- 回到 create_drill_tables 的形状：外键存在但不带级联
        ALTER TABLE drill_evaluations
            ADD CONSTRAINT drill_evaluations_drill_id_fkey
            FOREIGN KEY (drill_id) REFERENCES drill_events (id);
    END IF;
END $$;
"""


def upgrade() -> None:
    """补 `drill_id` 唯一约束与带级联的外键（对两种来源都收敛）。"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # 测试环境用 SQLite，schema 由 `Base.metadata.create_all` 从模型生成
        # （见 tests/conftest.py），迁移不参与；且 SQLite 默认不强制外键。
        return

    op.execute(_ORPHAN_CHECK)
    op.execute(_ADD_UNIQUE)
    op.execute(_ADD_CASCADE_FK)


def downgrade() -> None:
    """去掉唯一约束，并把外键退回不带级联的形态。"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(_DROP_CASCADE_FK_AND_RESTORE)
    op.execute(
        "ALTER TABLE drill_evaluations "
        "DROP CONSTRAINT IF EXISTS uq_drill_evaluations_drill_id"
    )
