"""add inspection tables audit columns

Revision ID: add_inspection_audit
Revises: merge_branches
Create Date: 2026-09-10 10:00:00.000000+08:00

Fixes DEC-004 compliance: added missing created_at/updated_at columns 
that should be present in all Inspection tables for consistency with Base model.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'add_inspection_audit'
down_revision: Union[str, None] = 'merge_branches'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # inspection_plans: add created_at and updated_at
    op.add_column('inspection_plans', sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')))
    op.add_column('inspection_plans', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    
    # inspection_tasks: add updated_at (created_at already exists)
    op.add_column('inspection_tasks', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    
    # inspection_records: add created_at and updated_at
    op.add_column('inspection_records', sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')))
    op.add_column('inspection_records', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    
    # Create indexes for new columns
    op.create_index('idx_inspection_plans_created_at', 'inspection_plans', ['created_at'])
    op.create_index('idx_inspection_plans_updated_at', 'inspection_plans', ['updated_at'])
    op.create_index('idx_inspection_tasks_updated_at', 'inspection_tasks', ['updated_at'])
    op.create_index('idx_inspection_records_created_at', 'inspection_records', ['created_at'])
    op.create_index('idx_inspection_records_updated_at', 'inspection_records', ['updated_at'])


def downgrade() -> None:
    # Downgrade is risky due to data loss warning, but included for completeness
    op.drop_index('idx_inspection_records_updated_at')
    op.drop_index('idx_inspection_records_created_at')
    op.drop_index('idx_inspection_tasks_updated_at')
    op.drop_index('idx_inspection_plans_updated_at')
    op.drop_index('idx_inspection_plans_created_at')
    
    op.drop_column('inspection_records', 'updated_at')
    op.drop_column('inspection_records', 'created_at')
    op.drop_column('inspection_tasks', 'updated_at')
    op.drop_column('inspection_plans', 'updated_at')
    op.drop_column('inspection_plans', 'created_at')
