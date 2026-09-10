"""merge linkage and repair branches

Revision ID: merge_branches
Revises: add_repair_orders, xxx_linkage_tables
Create Date: 2026-09-10 10:30:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'merge_branches'
down_revision: Union[str, Sequence[str]] = ('add_repair_orders', 'xxx_linkage_tables')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
