"""add repair_orders table

Revision ID: add_repair_orders
Revises: 54d02fd0cebb
Create Date: 2026-09-10 10:00:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_repair_orders'
down_revision: Union[str, None] = 'add_inspection'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建维修工单表
    op.create_table('repair_orders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('order_no', sa.String(length=50), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('alarm_id', sa.Integer(), nullable=True),
    sa.Column('inspection_record_id', sa.Integer(), nullable=True),
    sa.Column('fault_desc', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
    sa.Column('reporter_id', sa.Integer(), nullable=True),
    sa.Column('repairer_id', sa.Integer(), nullable=True),
    sa.Column('acceptor_id', sa.Integer(), nullable=True),
    sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('repair_result', sa.Text(), nullable=True),
    sa.Column('return_reason', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('order_no'),
    sa.UniqueConstraint('inspection_record_id'),  # 防止巡检记录重复创建工单
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
    sa.ForeignKeyConstraint(['alarm_id'], ['alarms.id'], ),
    sa.ForeignKeyConstraint(['inspection_record_id'], ['inspection_records.id'], ),
    sa.ForeignKeyConstraint(['reporter_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['repairer_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['acceptor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], )
    )
    
    # 创建索引
    op.create_index('idx_repair_orders_device_id', 'repair_orders', ['device_id'])
    op.create_index('idx_repair_orders_alarm_id', 'repair_orders', ['alarm_id'])
    op.create_index('idx_repair_orders_inspection_record_id', 'repair_orders', ['inspection_record_id'])
    op.create_index('idx_repair_orders_status', 'repair_orders', ['status'])
    op.create_index('idx_repair_orders_reporter_id', 'repair_orders', ['reporter_id'])
    op.create_index('idx_repair_orders_repairer_id', 'repair_orders', ['repairer_id'])
    op.create_index('idx_repair_orders_created_by', 'repair_orders', ['created_by'])
    op.create_index('idx_repair_orders_device_status', 'repair_orders', ['device_id', 'status'])
    op.create_index('idx_repair_orders_repairer_status', 'repair_orders', ['repairer_id', 'status'])


def downgrade() -> None:
    # 删除索引
    op.drop_index('idx_repair_orders_repairer_status', table_name='repair_orders')
    op.drop_index('idx_repair_orders_device_status', table_name='repair_orders')
    op.drop_index('idx_repair_orders_created_by', table_name='repair_orders')
    op.drop_index('idx_repair_orders_repairer_id', table_name='repair_orders')
    op.drop_index('idx_repair_orders_reporter_id', table_name='repair_orders')
    op.drop_index('idx_repair_orders_status', table_name='repair_orders')
    op.drop_index('idx_repair_orders_inspection_record_id', table_name='repair_orders')
    op.drop_index('idx_repair_orders_alarm_id', table_name='repair_orders')
    op.drop_index('idx_repair_orders_device_id', table_name='repair_orders')
    
    # 删除表
    op.drop_table('repair_orders')
