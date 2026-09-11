"""create drill tables (drill_events, drill_evaluations)

Revision ID: create_drill_tables
Revises: add_inspection_audit
Create Date: 2026-09-11 00:00:00.000000+08:00

Implements 3.8 drill module tables per development plan v1.1:
- drill_events: drill plan/execution record (no is_drill_data, per OQ-6)
- drill_evaluations: 1:1 evaluation with evaluation_summary (per OQ-4)

Note: tables are created here directly with the final v1.1 structure
(no is_drill_data column ever existed in any deployed database).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'create_drill_tables'
down_revision: Union[str, None] = 'add_inspection_audit'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create drill_events and drill_evaluations tables with indexes."""
    op.create_table(
        'drill_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('drill_name', sa.String(length=100), nullable=False),
        sa.Column('drill_type', sa.String(length=20), nullable=False),
        sa.Column('planned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_start_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_end_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('participants', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='planned', nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('photos', sa.JSON(), nullable=True),
        sa.Column('videos', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_drill_events_status', 'drill_events', ['status'])
    op.create_index('idx_drill_events_planned', 'drill_events', ['planned_at'])
    op.create_index('idx_drill_events_type', 'drill_events', ['drill_type'])
    op.create_index('idx_drill_events_created_by', 'drill_events', ['created_by'])

    op.create_table(
        'drill_evaluations',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('drill_id', sa.BigInteger(), nullable=False),
        sa.Column('evaluator_id', sa.BigInteger(), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('items', sa.JSON(), nullable=False),
        sa.Column('total_score', sa.Integer(), nullable=True),
        sa.Column('problems', sa.Text(), nullable=True),
        sa.Column('improvements', sa.Text(), nullable=True),
        sa.Column('evaluation_summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.ForeignKeyConstraint(['drill_id'], ['drill_events.id']),
        sa.ForeignKeyConstraint(['evaluator_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('drill_id', name='uq_drill_evaluations_drill_id'),
    )
    op.create_index('idx_drill_evaluations_drill', 'drill_evaluations', ['drill_id'])
    op.create_index('idx_drill_evaluations_evaluator', 'drill_evaluations', ['evaluator_id'])


def downgrade() -> None:
    """Drop drill tables."""
    op.drop_index('idx_drill_evaluations_evaluator', table_name='drill_evaluations')
    op.drop_index('idx_drill_evaluations_drill', table_name='drill_evaluations')
    op.drop_table('drill_evaluations')

    op.drop_index('idx_drill_events_created_by', table_name='drill_events')
    op.drop_index('idx_drill_events_type', table_name='drill_events')
    op.drop_index('idx_drill_events_planned', table_name='drill_events')
    op.drop_index('idx_drill_events_status', table_name='drill_events')
    op.drop_table('drill_events')
