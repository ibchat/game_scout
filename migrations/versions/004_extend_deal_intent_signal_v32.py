"""extend deal_intent_signal v3.2

Revision ID: 004_extend_signal
Revises: 003_deal_intent
Create Date: 2026-01-28 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_extend_signal'
down_revision = '003_deal_intent'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем новые поля в deal_intent_signal
    op.add_column('deal_intent_signal', sa.Column('title_guess', sa.Text(), nullable=True))
    op.add_column('deal_intent_signal', sa.Column('author', sa.Text(), nullable=True))
    op.add_column('deal_intent_signal', sa.Column('matched_keywords', postgresql.JSONB(), nullable=True))
    op.add_column('deal_intent_signal', sa.Column('intent_strength', sa.Integer(), nullable=True))
    op.add_column('deal_intent_signal', sa.Column('extracted_steam_app_ids', postgresql.ARRAY(sa.Integer()), nullable=True))
    op.add_column('deal_intent_signal', sa.Column('extracted_links', postgresql.JSONB(), nullable=True))
    op.add_column('deal_intent_signal', sa.Column('lang', sa.Text(), nullable=True, server_default='en'))
    
    # Добавляем ts (timestamp) - используем published_at если есть, иначе created_at
    op.add_column('deal_intent_signal', sa.Column('ts', sa.TIMESTAMP(), nullable=True))
    op.execute("""
        UPDATE deal_intent_signal 
        SET ts = COALESCE(published_at, created_at)
        WHERE ts IS NULL
    """)
    
    # Создаём индексы
    op.create_index('idx_deal_intent_signal_app_id_ts', 'deal_intent_signal', ['app_id', sa.text('ts DESC')])
    op.create_index('idx_deal_intent_signal_source_ts', 'deal_intent_signal', ['source', sa.text('ts DESC')])
    op.create_index('idx_deal_intent_signal_matched_keywords', 'deal_intent_signal', ['matched_keywords'], postgresql_using='gin')
    
    # Unique constraint на (source, url) для предотвращения дубликатов (только для не-NULL url)
    # Используем частичный индекс через raw SQL, так как Alembic не поддерживает partial unique index напрямую
    op.execute("""
        CREATE UNIQUE INDEX idx_deal_intent_signal_source_url 
        ON deal_intent_signal (source, url) 
        WHERE url IS NOT NULL
    """)


def downgrade():
    op.drop_index('idx_deal_intent_signal_source_url', 'deal_intent_signal')
    op.drop_index('idx_deal_intent_signal_matched_keywords', 'deal_intent_signal')
    op.drop_index('idx_deal_intent_signal_source_ts', 'deal_intent_signal')
    op.drop_index('idx_deal_intent_signal_app_id_ts', 'deal_intent_signal')
    op.drop_column('deal_intent_signal', 'ts')
    op.drop_column('deal_intent_signal', 'lang')
    op.drop_column('deal_intent_signal', 'extracted_links')
    op.drop_column('deal_intent_signal', 'extracted_steam_app_ids')
    op.drop_column('deal_intent_signal', 'intent_strength')
    op.drop_column('deal_intent_signal', 'matched_keywords')
    op.drop_column('deal_intent_signal', 'author')
    op.drop_column('deal_intent_signal', 'title_guess')
