"""add voy learning config and log tables

Revision ID: 007_voy_learning
Revises: 006_add_voy_tables
Create Date: 2026-02-03 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '007_voy_learning'
down_revision = '006_voy_tables'
branch_labels = None
depends_on = None


def upgrade():
    # voy_learning_config - learning configuration
    op.create_table(
        'voy_learning_config',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('learning_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('learning_rate', sa.Float(), nullable=False, server_default='0.05'),
        sa.Column('max_weight_delta', sa.Float(), nullable=False, server_default='0.05'),
        sa.Column('min_skill_weight', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('max_skill_weight', sa.Float(), nullable=False, server_default='2.0'),
        sa.Column('min_feedback_count', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('frozen_skills', postgresql.JSONB(), nullable=True, server_default='[]'),
        sa.Column('allow_gpt_advice', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    # Create single default config row
    op.execute("""
        INSERT INTO voy_learning_config (id, learning_enabled, learning_rate, max_weight_delta, 
                                         min_skill_weight, max_skill_weight, min_feedback_count, 
                                         frozen_skills, allow_gpt_advice)
        VALUES (gen_random_uuid(), true, 0.05, 0.05, 0.5, 2.0, 3, '[]'::jsonb, true)
        ON CONFLICT DO NOTHING;
    """)

    # voy_learning_log - log of all weight changes
    op.create_table(
        'voy_learning_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_item_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('skill_key', sa.Text(), nullable=False),
        sa.Column('old_weight', sa.Float(), nullable=False),
        sa.Column('new_weight', sa.Float(), nullable=False),
        sa.Column('delta', sa.Float(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('source', sa.Text(), nullable=False),  # 'feedback' or 'gpt_advice'
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_voy_learning_log_run_item_id', 'voy_learning_log', ['run_item_id'])
    op.create_index('idx_voy_learning_log_skill_key', 'voy_learning_log', ['skill_key'])
    op.create_index('idx_voy_learning_log_source', 'voy_learning_log', ['source'])
    op.create_index('idx_voy_learning_log_created_at', 'voy_learning_log', ['created_at'])
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_voy_learning_log_run_item',
        'voy_learning_log', 'voy_run_item',
        ['run_item_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade():
    op.drop_constraint('fk_voy_learning_log_run_item', 'voy_learning_log', type_='foreignkey')
    op.drop_index('idx_voy_learning_log_created_at', table_name='voy_learning_log')
    op.drop_index('idx_voy_learning_log_source', table_name='voy_learning_log')
    op.drop_index('idx_voy_learning_log_skill_key', table_name='voy_learning_log')
    op.drop_index('idx_voy_learning_log_run_item_id', table_name='voy_learning_log')
    op.drop_table('voy_learning_log')
    op.drop_table('voy_learning_config')
