"""add intel event significance fields

Revision ID: 013_intel_event_significance
Revises: 012_intel_event_autopublish
Create Date: 2026-02-17 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '013_intel_event_significance'
down_revision = '012_intel_event_autopublish'
branch_labels = None
depends_on = None


def upgrade():
    # Add significance fields to intel_events
    op.add_column('intel_events', sa.Column('significance_score', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('intel_events', sa.Column('significance_reason', sa.Text(), nullable=True))
    
    # Create index for filtering by score
    op.create_index('idx_intel_events_significance_score', 'intel_events', ['significance_score'])


def downgrade():
    op.drop_index('idx_intel_events_significance_score', table_name='intel_events')
    op.drop_column('intel_events', 'significance_reason')
    op.drop_column('intel_events', 'significance_score')
