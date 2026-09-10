"""add inspection tables

Revision ID: add_inspection
Revises: 54d02fd0cebb
Create Date: 2026-09-10 09:00:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_inspection'
down_revision: Union[str, None] = '54d02fd0cebb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建巡检计划表
    op.create_table('inspection_plans',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('plan_name', sa.String(length=100), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=True),
    sa.Column('device_type_id', sa.Integer(), nullable=True),
    sa.Column('responsible_user_id', sa.Integer(), nullable=True),
    sa.Column('cycle_type', sa.String(length=20), nullable=False),
    sa.Column('cycle_days', sa.Integer(), nullable=True),
    sa.Column('start_date', sa.DATE(), nullable=True),
    sa.Column('end_date', sa.DATE(), nullable=True),
    sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    sa.PrimaryKeyConstraint('id'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['device_type_id'], ['device_types.id'], ),
    sa.ForeignKeyConstraint(['responsible_user_id'], ['users.id'], )
    )
    
    # 创建巡检任务表
    op.create_table('inspection_tasks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=False),
    sa.Column('responsible_user_id', sa.Integer(), nullable=True),
    sa.Column('task_date', sa.DATE(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    sa.PrimaryKeyConstraint('id'),
    sa.ForeignKeyConstraint(['plan_id'], ['inspection_plans.id'], ),
    sa.ForeignKeyConstraint(['responsible_user_id'], ['users.id'], )
    )
    
    # 创建巡检记录表
    op.create_table('inspection_records',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('inspected_by', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('result', sa.String(length=20), nullable=False),
    sa.Column('abnormal_desc', sa.Text(), nullable=True),
    sa.Column('photos', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    sa.Column('inspected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    sa.PrimaryKeyConstraint('id'),
    sa.ForeignKeyConstraint(['task_id'], ['inspection_tasks.id'], ),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
    sa.ForeignKeyConstraint(['inspected_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], )
    )
    
    # 创建索引
    op.create_index('idx_inspection_plans_org_id', 'inspection_plans', ['org_id'])
    op.create_index('idx_inspection_plans_device_type_id', 'inspection_plans', ['device_type_id'])
    op.create_index('idx_inspection_plans_responsible_user_id', 'inspection_plans', ['responsible_user_id'])
    op.create_index('idx_inspection_tasks_plan_id', 'inspection_tasks', ['plan_id'])
    op.create_index('idx_inspection_tasks_responsible_user_id', 'inspection_tasks', ['responsible_user_id'])
    op.create_index('idx_inspection_tasks_task_date', 'inspection_tasks', ['task_date'])
    op.create_index('idx_inspection_records_task_id', 'inspection_records', ['task_id'])
    op.create_index('idx_inspection_records_device_id', 'inspection_records', ['device_id'])
    op.create_index('idx_inspection_records_created_by', 'inspection_records', ['created_by'])


def downgrade() -> None:
    # 删除索引
    op.drop_index('idx_inspection_records_created_by', table_name='inspection_records')
    op.drop_index('idx_inspection_records_device_id', table_name='inspection_records')
    op.drop_index('idx_inspection_records_task_id', table_name='inspection_records')
    op.drop_index('idx_inspection_tasks_task_date', table_name='inspection_tasks')
    op.drop_index('idx_inspection_tasks_responsible_user_id', table_name='inspection_tasks')
    op.drop_index('idx_inspection_tasks_plan_id', table_name='inspection_tasks')
    op.drop_index('idx_inspection_plans_responsible_user_id', table_name='inspection_plans')
    op.drop_index('idx_inspection_plans_device_type_id', table_name='inspection_plans')
    op.drop_index('idx_inspection_plans_org_id', table_name='inspection_plans')
    
    # 删除表
    op.drop_table('inspection_records')
    op.drop_table('inspection_tasks')
    op.drop_table('inspection_plans')
