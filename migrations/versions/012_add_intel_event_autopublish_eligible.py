"""add intel event autopublish_eligible field

Revision ID: 012_intel_event_autopublish
Revises: 011_intel_publish_log_status
Create Date: 2026-02-17 21:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '012_intel_event_autopublish'
down_revision = '011_intel_publish_log_status'
branch_labels = None
depends_on = None


def upgrade():
    # Add autopublish_eligible field to intel_events
    op.add_column('intel_events', sa.Column('autopublish_eligible', sa.Boolean(), nullable=False, server_default='false'))
    
    # Create index for filtering
    op.create_index('idx_intel_events_autopublish_eligible', 'intel_events', ['autopublish_eligible'])


def downgrade():
    op.drop_index('idx_intel_events_autopublish_eligible', table_name='intel_events')
    op.drop_column('intel_events', 'autopublish_eligible')
