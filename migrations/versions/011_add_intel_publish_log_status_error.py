"""add intel publish log status and error fields

Revision ID: 011_intel_publish_log_status
Revises: 010_intel_event_business
Create Date: 2026-02-17 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '011_intel_publish_log_status'
down_revision = '010_intel_event_business'
branch_labels = None
depends_on = None


def upgrade():
    # Add status and error fields to intel_publish_log
    op.add_column('intel_publish_log', sa.Column('status', sa.String(length=50), nullable=True))
    op.add_column('intel_publish_log', sa.Column('error', sa.Text(), nullable=True))
    
    # Set default status for existing records
    op.execute("UPDATE intel_publish_log SET status = 'published' WHERE status IS NULL")
    
    # Create index for status filtering
    op.create_index('idx_intel_publish_log_status', 'intel_publish_log', ['status'])


def downgrade():
    op.drop_index('idx_intel_publish_log_status', table_name='intel_publish_log')
    op.drop_column('intel_publish_log', 'error')
    op.drop_column('intel_publish_log', 'status')
