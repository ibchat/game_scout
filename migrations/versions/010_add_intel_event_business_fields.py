"""add intel event business fields

Revision ID: 010_intel_event_business
Revises: 009_intel_tables
Create Date: 2026-02-17 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '010_intel_event_business'
down_revision = '009_intel_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Add business brief fields to intel_events
    op.add_column('intel_events', sa.Column('business_brief_json', postgresql.JSONB(), nullable=True))
    op.add_column('intel_events', sa.Column('business_brief_generated_at', sa.TIMESTAMP(timezone=True), nullable=True))
    
    # Add publish status enum and field
    # Using String instead of Enum for flexibility
    op.add_column('intel_events', sa.Column('publish_status', sa.String(length=50), nullable=True, server_default='draft'))
    op.add_column('intel_events', sa.Column('publish_channel', sa.String(length=100), nullable=True))
    op.add_column('intel_events', sa.Column('is_premium', sa.Boolean(), nullable=False, server_default='false'))
    
    # Create index for publish_status filtering
    op.create_index('idx_intel_events_publish_status', 'intel_events', ['publish_status'])
    op.create_index('idx_intel_events_is_premium', 'intel_events', ['is_premium'])


def downgrade():
    op.drop_index('idx_intel_events_is_premium', table_name='intel_events')
    op.drop_index('idx_intel_events_publish_status', table_name='intel_events')
    op.drop_column('intel_events', 'is_premium')
    op.drop_column('intel_events', 'publish_channel')
    op.drop_column('intel_events', 'publish_status')
    op.drop_column('intel_events', 'business_brief_generated_at')
    op.drop_column('intel_events', 'business_brief_json')
