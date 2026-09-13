"""add unique constraint (plan_id, task_date) to inspection_tasks

3.6 FR-033 需要「同一计划同一天只生成一条任务」这条不变量真正落到库上。

此前它只存在于注释里：`app/models/inspection.py` 顶部的「注意事项」和
`InspectionTask` 的类注释都声称有这个唯一约束，但既没有 `__table_args__`，
也没有本迁移。去重完全依赖 `generate_tasks_for_plan()` 里的 check-then-act
（先 select 再 insert），在多 worker（docker-compose 的 WORKERS>1）同时启动、
同时补跑时，两个进程都能通过检查并各自插入一条。

升级前先查重：有重复数据时中止**本次迁移**并把冲突行列出来，而不是硬建约束
失败在半路。

注意一个容易误判的点：`main.py:_ensure_database_schema()` 会把迁移异常记成
`[WARN] Database setup failed` 后**继续启动**（这是它「存量脏库自愈」的既定行为），
所以这里抛错的实际效果是「日志里一条 WARN + 约束没建上」，而不是「服务起不来」。
又因为该函数随后用 `create_all(checkfirst=True)` 兜底，而它**不会给已存在的表补
约束**，那条路径下约束会静默缺失。因此本约束属于**纵深防御**而非唯一防线：
`generate_tasks_for_plan()` 里的 check-then-act 与 `IntegrityError` 捕获始终在位。
建完后请用 `\d inspection_tasks` 确认约束真的落地（见 3.6 测试报告）。

Revision ID: add_inspection_task_plan_date_uq
Revises: make_linkage_log_alarm_nullable
Create Date: 2026-09-13 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_inspection_task_plan_date_uq'
down_revision: Union[str, None] = 'make_linkage_log_alarm_nullable'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT_NAME = 'uq_inspection_tasks_plan_date'


def upgrade() -> None:
    conn = op.get_bind()

    duplicates = conn.execute(
        sa.text(
            "SELECT plan_id, task_date, COUNT(*) AS n "
            "FROM inspection_tasks "
            "GROUP BY plan_id, task_date "
            "HAVING COUNT(*) > 1"
        )
    ).fetchall()

    if duplicates:
        detail = ", ".join(
            f"(plan_id={row.plan_id}, task_date={row.task_date}, n={row.n})"
            for row in duplicates[:10]
        )
        raise RuntimeError(
            "inspection_tasks 存在重复的 (plan_id, task_date)，无法建立唯一约束。"
            f"共 {len(duplicates)} 组，前 10 组：{detail}。"
            "请先人工确认并删除重复任务后重新执行迁移。"
        )

    op.create_unique_constraint(
        CONSTRAINT_NAME, 'inspection_tasks', ['plan_id', 'task_date']
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, 'inspection_tasks', type_='unique')
