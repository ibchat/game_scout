"""add intel source health fields

Revision ID: 015_intel_source_health
Revises: 014_add_intel_sources_extended
Create Date: 2026-02-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '015_intel_source_health'
down_revision = '014_add_intel_sources_extended'
branch_labels = None
depends_on = None


def upgrade():
    # Add source health tracking fields to intel_sources (idempotent)
    # Check if columns exist before adding to avoid errors on re-run
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('intel_sources')]
    
    # Add columns only if they don't exist
    if 'country' not in existing_columns:
        op.add_column('intel_sources', sa.Column('country', sa.String(length=10), nullable=True))
    if 'locale' not in existing_columns:
        op.add_column('intel_sources', sa.Column('locale', sa.String(length=10), nullable=True))
    if 'category_hint' not in existing_columns:
        op.add_column('intel_sources', sa.Column('category_hint', sa.String(length=50), nullable=True))
    if 'weight' not in existing_columns:
        op.add_column('intel_sources', sa.Column('weight', sa.Integer(), nullable=False, server_default='10'))
    if 'last_error_code' not in existing_columns:
        op.add_column('intel_sources', sa.Column('last_error_code', sa.Integer(), nullable=True))
    if 'failure_streak' not in existing_columns:
        op.add_column('intel_sources', sa.Column('failure_streak', sa.Integer(), nullable=False, server_default='0'))
    if 'last_success_at' not in existing_columns:
        op.add_column('intel_sources', sa.Column('last_success_at', sa.TIMESTAMP(timezone=True), nullable=True))
    if 'disabled_reason' not in existing_columns:
        op.add_column('intel_sources', sa.Column('disabled_reason', sa.Text(), nullable=True))
    if 'disabled_at' not in existing_columns:
        op.add_column('intel_sources', sa.Column('disabled_at', sa.TIMESTAMP(timezone=True), nullable=True))
    if 'backoff_until' not in existing_columns:
        op.add_column('intel_sources', sa.Column('backoff_until', sa.TIMESTAMP(timezone=True), nullable=True))
    if 'blocked_reason' not in existing_columns:
        op.add_column('intel_sources', sa.Column('blocked_reason', sa.Text(), nullable=True))
    
    # Create indexes for health tracking (idempotent)
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('intel_sources')]
    
    if 'idx_intel_sources_failure_streak' not in existing_indexes:
        op.create_index('idx_intel_sources_failure_streak', 'intel_sources', ['failure_streak'])
    if 'idx_intel_sources_backoff_until' not in existing_indexes:
        op.create_index('idx_intel_sources_backoff_until', 'intel_sources', ['backoff_until'])
    if 'idx_intel_sources_last_success_at' not in existing_indexes:
        op.create_index('idx_intel_sources_last_success_at', 'intel_sources', ['last_success_at'])


def downgrade():
    op.drop_index('idx_intel_sources_last_success_at', table_name='intel_sources')
    op.drop_index('idx_intel_sources_backoff_until', table_name='intel_sources')
    op.drop_index('idx_intel_sources_failure_streak', table_name='intel_sources')
    
    op.drop_column('intel_sources', 'blocked_reason')
    op.drop_column('intel_sources', 'backoff_until')
    op.drop_column('intel_sources', 'disabled_at')
    op.drop_column('intel_sources', 'disabled_reason')
    op.drop_column('intel_sources', 'last_success_at')
    op.drop_column('intel_sources', 'failure_streak')
    op.drop_column('intel_sources', 'last_error_code')
    op.drop_column('intel_sources', 'weight')
    op.drop_column('intel_sources', 'category_hint')
    op.drop_column('intel_sources', 'locale')
    op.drop_column('intel_sources', 'country')
