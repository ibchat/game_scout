"""add intel tables

Revision ID: 009_intel_tables
Revises: 008_voy_methodology
Create Date: 2026-02-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '009_intel_tables'
down_revision = '008_voy_methodology'  # Last migration before Intel
branch_labels = None
depends_on = None


def upgrade():
    # intel_sources - source configuration
    op.create_table(
        'intel_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('language_hint', sa.String(length=10), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_intel_sources_type', 'intel_sources', ['type'])
    op.create_index('idx_intel_sources_is_enabled', 'intel_sources', ['is_enabled'])

    # intel_raw_items - raw items collected from sources
    op.create_table(
        'intel_raw_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('fetched_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('snippet', sa.Text(), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(), nullable=True),
        sa.Column('raw_html', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['intel_sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url', name='uq_intel_raw_items_url')
    )
    op.create_index('idx_intel_raw_items_url', 'intel_raw_items', ['url'])
    op.create_index('idx_intel_raw_items_source_id', 'intel_raw_items', ['source_id'])
    op.create_index('idx_intel_raw_items_fetched_at', 'intel_raw_items', ['fetched_at'])

    # intel_extracted_items - extracted and normalized items
    op.create_table(
        'intel_extracted_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('raw_item_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('published_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('lang', sa.String(length=10), nullable=False),
        sa.Column('title_norm', sa.Text(), nullable=False),
        sa.Column('url_norm', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('meta', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['raw_item_id'], ['intel_raw_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('raw_item_id', name='uq_intel_extracted_items_raw_item_id')
    )
    op.create_index('idx_intel_extracted_items_url_norm', 'intel_extracted_items', ['url_norm'])
    op.create_index('idx_intel_extracted_items_raw_item_id', 'intel_extracted_items', ['raw_item_id'])

    # intel_clusters - clusters of duplicate/similar items
    op.create_table(
        'intel_clusters',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('representative_extracted_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('member_extracted_ids', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.ForeignKeyConstraint(['representative_extracted_id'], ['intel_extracted_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_intel_clusters_representative', 'intel_clusters', ['representative_extracted_id'])
    op.create_index('idx_intel_clusters_created_at', 'intel_clusters', ['created_at'])

    # intel_entities - resolved entities (steam_appid mappings)
    op.create_table(
        'intel_entities',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('extracted_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('steam_appid', sa.BigInteger(), nullable=True),
        sa.Column('canonical_name', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('method', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['extracted_id'], ['intel_extracted_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_intel_entities_extracted_id', 'intel_entities', ['extracted_id'])
    op.create_index('idx_intel_entities_steam_appid', 'intel_entities', ['steam_appid'])
    op.create_index('idx_intel_entities_confidence', 'intel_entities', ['confidence'])

    # intel_events - processed events ready for publication
    op.create_table(
        'intel_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('cluster_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('steam_appid', sa.BigInteger(), nullable=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='new'),
        sa.Column('title_ru', sa.Text(), nullable=False),
        sa.Column('what_happened_ru', sa.Text(), nullable=False),
        sa.Column('why_it_matters_ru', sa.Text(), nullable=True),
        sa.Column('facts_ru', postgresql.JSONB(), nullable=True),
        sa.Column('risks_ru', postgresql.JSONB(), nullable=True),
        sa.Column('tags', postgresql.JSONB(), nullable=True),
        sa.Column('sources', postgresql.JSONB(), nullable=True),
        sa.Column('llm_meta', postgresql.JSONB(), nullable=True),
        sa.Column('policy_decision', sa.Text(), nullable=True),
        sa.Column('policy_reason', sa.Text(), nullable=True),
        sa.Column('published_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('telegram_message_id', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['cluster_id'], ['intel_clusters.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    # Composite index for status + created_at (as per spec)
    op.create_index('idx_intel_events_status_created_at', 'intel_events', ['status', 'created_at'])
    op.create_index('idx_intel_events_steam_appid', 'intel_events', ['steam_appid'])
    op.create_index('idx_intel_events_score', 'intel_events', ['score'])
    op.create_index('idx_intel_events_event_type', 'intel_events', ['event_type'])
    op.create_index('idx_intel_events_cluster_id', 'intel_events', ['cluster_id'])

    # intel_publish_log - log of published events
    op.create_table(
        'intel_publish_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('published_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('channel_id', sa.Text(), nullable=False),
        sa.Column('telegram_message_id', sa.Text(), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['intel_events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_intel_publish_log_event_id', 'intel_publish_log', ['event_id'])
    op.create_index('idx_intel_publish_log_published_at', 'intel_publish_log', ['published_at'])

    # intel_audit_log - audit log for policy checks
    op.create_table(
        'intel_audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_intel_audit_log_created_at', 'intel_audit_log', ['created_at'])
    op.create_index('idx_intel_audit_log_status', 'intel_audit_log', ['status'])


def downgrade():
    op.drop_index('idx_intel_audit_log_status', table_name='intel_audit_log')
    op.drop_index('idx_intel_audit_log_created_at', table_name='intel_audit_log')
    op.drop_table('intel_audit_log')
    
    op.drop_index('idx_intel_publish_log_published_at', table_name='intel_publish_log')
    op.drop_index('idx_intel_publish_log_event_id', table_name='intel_publish_log')
    op.drop_table('intel_publish_log')
    
    op.drop_index('idx_intel_events_cluster_id', table_name='intel_events')
    op.drop_index('idx_intel_events_event_type', table_name='intel_events')
    op.drop_index('idx_intel_events_score', table_name='intel_events')
    op.drop_index('idx_intel_events_steam_appid', table_name='intel_events')
    op.drop_index('idx_intel_events_status_created_at', table_name='intel_events')
    op.drop_table('intel_events')
    
    op.drop_index('idx_intel_entities_confidence', table_name='intel_entities')
    op.drop_index('idx_intel_entities_steam_appid', table_name='intel_entities')
    op.drop_index('idx_intel_entities_extracted_id', table_name='intel_entities')
    op.drop_table('intel_entities')
    
    op.drop_index('idx_intel_clusters_created_at', table_name='intel_clusters')
    op.drop_index('idx_intel_clusters_representative', table_name='intel_clusters')
    op.drop_table('intel_clusters')
    
    op.drop_index('idx_intel_extracted_items_raw_item_id', table_name='intel_extracted_items')
    op.drop_index('idx_intel_extracted_items_url_norm', table_name='intel_extracted_items')
    op.drop_table('intel_extracted_items')
    
    op.drop_index('idx_intel_raw_items_fetched_at', table_name='intel_raw_items')
    op.drop_index('idx_intel_raw_items_source_id', table_name='intel_raw_items')
    op.drop_index('idx_intel_raw_items_url', table_name='intel_raw_items')
    op.drop_table('intel_raw_items')
    
    op.drop_index('idx_intel_sources_is_enabled', table_name='intel_sources')
    op.drop_index('idx_intel_sources_type', table_name='intel_sources')
    op.drop_table('intel_sources')
