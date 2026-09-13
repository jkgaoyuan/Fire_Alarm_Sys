"""make alarm_linkage_logs.alarm_id nullable

模拟触发（is_simulation=True）不产生真实告警，原 NOT NULL 约束会让
`AlarmLinkageLog(alarm_id=None)` 在 flush 时抛 IntegrityError（HTTP 500）。

Revision ID: make_linkage_log_alarm_nullable
Revises: 4767a93d67a0
Create Date: 2026-09-13 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'make_linkage_log_alarm_nullable'
down_revision: Union[str, None] = '4767a93d67a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'alarm_linkage_logs',
        'alarm_id',
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # 回滚前需先清掉模拟日志，否则 NOT NULL 约束无法建立
    op.execute("DELETE FROM alarm_linkage_logs WHERE alarm_id IS NULL")
    op.alter_column(
        'alarm_linkage_logs',
        'alarm_id',
        existing_type=sa.Integer(),
        nullable=False,
    )
