"""create trends_raw_events and steam_app_aliases

Revision ID: 002_events_aliases
Revises: 40f382a72f21
Create Date: 2026-01-26 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_events_aliases'
down_revision = '40f382a72f21'
branch_labels = None
depends_on = None


def upgrade():
    # Create trends_raw_events table
    op.create_table(
        'trends_raw_events',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('external_id', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('metrics_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('matched_steam_app_id', sa.BigInteger(), nullable=True),
        sa.Column('match_confidence', sa.Float(), nullable=True),
        sa.Column('match_reason', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_trends_raw_events_source_external_id', 'trends_raw_events', ['source', 'external_id'], unique=True)
    op.create_index('ix_trends_raw_events_captured_at', 'trends_raw_events', ['captured_at'], postgresql_ops={'captured_at': 'DESC'})
    op.create_index('ix_trends_raw_events_matched_app', 'trends_raw_events', ['matched_steam_app_id', 'published_at'], postgresql_ops={'published_at': 'DESC'})
    
    # Create steam_app_aliases table
    op.create_table(
        'steam_app_aliases',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('steam_app_id', sa.BigInteger(), nullable=False),
        sa.Column('alias', sa.Text(), nullable=False),
        sa.Column('alias_type', sa.Text(), nullable=False, server_default='common'),
        sa.Column('weight', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_steam_app_aliases_app_alias', 'steam_app_aliases', ['steam_app_id', 'alias'], unique=True)
    op.create_index('ix_steam_app_aliases_alias', 'steam_app_aliases', ['alias'])


def downgrade():
    op.drop_index('ix_steam_app_aliases_alias', table_name='steam_app_aliases')
    op.drop_index('ix_steam_app_aliases_app_alias', table_name='steam_app_aliases')
    op.drop_table('steam_app_aliases')
    
    op.drop_index('ix_trends_raw_events_matched_app', table_name='trends_raw_events')
    op.drop_index('ix_trends_raw_events_captured_at', table_name='trends_raw_events')
    op.drop_index('ix_trends_raw_events_source_external_id', table_name='trends_raw_events')
    op.drop_table('trends_raw_events')
