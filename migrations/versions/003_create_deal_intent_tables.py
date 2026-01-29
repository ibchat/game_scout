"""create deal intent tables

Revision ID: 003_deal_intent
Revises: 002_create_trends_raw_events
Create Date: 2026-01-26 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_deal_intent'
down_revision = '002_create_trends_raw_events'
branch_labels = None
depends_on = None


def upgrade():
    # deal_intent_game - snapshot по игре
    op.create_table(
        'deal_intent_game',
        sa.Column('app_id', sa.Integer(), nullable=False),
        sa.Column('steam_name', sa.Text(), nullable=True),
        sa.Column('steam_url', sa.Text(), nullable=True),
        sa.Column('developer_name', sa.Text(), nullable=True),
        sa.Column('publisher_name', sa.Text(), nullable=True),
        sa.Column('release_date', sa.Date(), nullable=True),
        sa.Column('stage', sa.Text(), nullable=True),  # coming_soon | demo | early_access | released
        sa.Column('has_demo', sa.Boolean(), nullable=True, default=False),
        sa.Column('price_eur', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('tags', postgresql.JSONB(), nullable=True),
        sa.Column('external_links', postgresql.JSONB(), nullable=True),
        sa.Column('intent_score', sa.Integer(), nullable=True, default=0),
        sa.Column('quality_score', sa.Integer(), nullable=True, default=0),
        sa.Column('intent_reasons', postgresql.JSONB(), nullable=True),
        sa.Column('quality_reasons', postgresql.JSONB(), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('app_id')
    )
    op.create_index('idx_deal_intent_game_intent_score', 'deal_intent_game', ['intent_score'])
    op.create_index('idx_deal_intent_game_quality_score', 'deal_intent_game', ['quality_score'])
    op.create_index('idx_deal_intent_game_stage', 'deal_intent_game', ['stage'])
    op.create_index('idx_deal_intent_game_updated_at', 'deal_intent_game', ['updated_at'])

    # deal_intent_signal - внешние сигналы
    op.create_table(
        'deal_intent_signal',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('app_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.Text(), nullable=True),  # steam, twitter, linkedin, etc
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('signal_type', sa.Text(), nullable=True),  # intent_keyword, external_link, etc
        sa.Column('confidence', sa.Float(), nullable=True, default=0.0),
        sa.Column('published_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_deal_intent_signal_app_id', 'deal_intent_signal', ['app_id'])
    op.create_index('idx_deal_intent_signal_source', 'deal_intent_signal', ['source'])
    op.create_index('idx_deal_intent_signal_type', 'deal_intent_signal', ['signal_type'])
    op.create_index('idx_deal_intent_signal_created_at', 'deal_intent_signal', ['created_at'])

    # deal_intent_action_log - логи действий
    op.create_table(
        'deal_intent_action_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('app_id', sa.Integer(), nullable=True),
        sa.Column('action_type', sa.Text(), nullable=True),  # request_pitch_deck, request_steamworks, send_offer, book_call, watchlist
        sa.Column('payload', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_deal_intent_action_log_app_id', 'deal_intent_action_log', ['app_id'])
    op.create_index('idx_deal_intent_action_log_action_type', 'deal_intent_action_log', ['action_type'])
    op.create_index('idx_deal_intent_action_log_created_at', 'deal_intent_action_log', ['created_at'])


def downgrade():
    op.drop_table('deal_intent_action_log')
    op.drop_table('deal_intent_signal')
    op.drop_table('deal_intent_game')
