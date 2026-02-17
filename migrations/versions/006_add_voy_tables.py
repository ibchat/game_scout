"""add voy tables

Revision ID: 006_voy_tables
Revises: 005_discord_publisher_hunt
Create Date: 2026-02-03 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '006_voy_tables'
down_revision = '005_discord_publisher_hunt'
branch_labels = None
depends_on = None


def upgrade():
    # voy_skill - skills with weights for scoring
    op.create_table(
        'voy_skill',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('weight', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('goal', sa.Text(), nullable=True),  # Optional: goal this skill is optimized for
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'goal', name='uq_voy_skill_name_goal')
    )
    op.create_index('idx_voy_skill_name', 'voy_skill', ['name'])
    op.create_index('idx_voy_skill_goal', 'voy_skill', ['goal'])
    op.create_index('idx_voy_skill_weight', 'voy_skill', ['weight'])

    # voy_run - a single VOY execution run
    op.create_table(
        'voy_run',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('goal', sa.Text(), nullable=False),  # Goal description for this run
        sa.Column('status', sa.Text(), nullable=False, server_default='running'),  # running, completed, cancelled
        sa.Column('total_candidates', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('shortlist_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_voy_run_goal', 'voy_run', ['goal'])
    op.create_index('idx_voy_run_status', 'voy_run', ['status'])
    op.create_index('idx_voy_run_created_at', 'voy_run', ['created_at'])

    # voy_run_item - games in a run's shortlist
    op.create_table(
        'voy_run_item',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('game_id', postgresql.UUID(as_uuid=True), nullable=False),  # Primary key for VOY logic
        sa.Column('app_id', sa.Integer(), nullable=True),  # Optional: Steam app_id if available
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('total_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('explanation', sa.Text(), nullable=True),  # Human-readable explanation of score
        sa.Column('features_json', postgresql.JSONB(), nullable=True),  # Computed features
        sa.Column('skill_scores_json', postgresql.JSONB(), nullable=True),  # Individual skill scores
        sa.Column('rank', sa.Integer(), nullable=True),  # Rank in shortlist (1 = best)
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['run_id'], ['voy_run.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_voy_run_item_run_id', 'voy_run_item', ['run_id'])
    op.create_index('idx_voy_run_item_game_id', 'voy_run_item', ['game_id'])
    op.create_index('idx_voy_run_item_app_id', 'voy_run_item', ['app_id'])
    op.create_index('idx_voy_run_item_total_score', 'voy_run_item', ['total_score'])
    op.create_index('idx_voy_run_item_rank', 'voy_run_item', ['rank'])

    # voy_feedback - human feedback on run items
    op.create_table(
        'voy_feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_item_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('feedback_type', sa.Text(), nullable=False),  # good, bad
        sa.Column('notes', sa.Text(), nullable=True),  # Optional human notes
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['run_item_id'], ['voy_run_item.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_voy_feedback_run_item_id', 'voy_feedback', ['run_item_id'])
    op.create_index('idx_voy_feedback_type', 'voy_feedback', ['feedback_type'])
    op.create_index('idx_voy_feedback_created_at', 'voy_feedback', ['created_at'])


def downgrade():
    op.drop_index('idx_voy_feedback_created_at', table_name='voy_feedback')
    op.drop_index('idx_voy_feedback_type', table_name='voy_feedback')
    op.drop_index('idx_voy_feedback_run_item_id', table_name='voy_feedback')
    op.drop_table('voy_feedback')
    
    op.drop_index('idx_voy_run_item_rank', table_name='voy_run_item')
    op.drop_index('idx_voy_run_item_total_score', table_name='voy_run_item')
    op.drop_index('idx_voy_run_item_app_id', table_name='voy_run_item')
    op.drop_index('idx_voy_run_item_game_id', table_name='voy_run_item')
    op.drop_index('idx_voy_run_item_run_id', table_name='voy_run_item')
    op.drop_table('voy_run_item')
    
    op.drop_index('idx_voy_run_created_at', table_name='voy_run')
    op.drop_index('idx_voy_run_status', table_name='voy_run')
    op.drop_index('idx_voy_run_goal', table_name='voy_run')
    op.drop_table('voy_run')
    
    op.drop_index('idx_voy_skill_weight', table_name='voy_skill')
    op.drop_index('idx_voy_skill_goal', table_name='voy_skill')
    op.drop_index('idx_voy_skill_name', table_name='voy_skill')
    op.drop_table('voy_skill')
