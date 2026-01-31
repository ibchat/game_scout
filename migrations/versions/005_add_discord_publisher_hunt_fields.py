"""add discord publisher hunt fields

Revision ID: 005_discord_publisher_hunt
Revises: 004_extend_signal
Create Date: 2026-01-31 05:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005_discord_publisher_hunt'
down_revision = '004_extend_signal'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем новые поля в deal_intent_signal для Discord Publisher Hunt
    # Примечание: confidence уже существует как FLOAT, добавляем confidence_jsonb для JSONB данных
    op.add_column('deal_intent_signal', sa.Column('source_subtype', sa.Text(), nullable=True))
    op.add_column('deal_intent_signal', sa.Column('channel_name', sa.Text(), nullable=True))
    op.add_column('deal_intent_signal', sa.Column('server_name', sa.Text(), nullable=True))
    op.add_column('deal_intent_signal', sa.Column('publisher_intent_score', sa.Float(), nullable=True))
    op.add_column('deal_intent_signal', sa.Column('publisher_phrase', sa.Text(), nullable=True))
    # confidence уже существует как FLOAT, не добавляем повторно
    
    # Индексы для быстрого поиска
    op.create_index('idx_deal_intent_signal_source_subtype', 'deal_intent_signal', ['source_subtype'])
    op.create_index('idx_deal_intent_signal_publisher_intent_score', 'deal_intent_signal', ['publisher_intent_score'])


def downgrade():
    op.drop_index('idx_deal_intent_signal_publisher_intent_score', 'deal_intent_signal')
    op.drop_index('idx_deal_intent_signal_source_subtype', 'deal_intent_signal')
    op.drop_column('deal_intent_signal', 'publisher_phrase')
    op.drop_column('deal_intent_signal', 'publisher_intent_score')
    op.drop_column('deal_intent_signal', 'server_name')
    op.drop_column('deal_intent_signal', 'channel_name')
    op.drop_column('deal_intent_signal', 'source_subtype')
