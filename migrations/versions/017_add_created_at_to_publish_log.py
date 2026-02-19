"""add created_at to intel_publish_log

Revision ID: 017_created_at_publish_log
Revises: 016_extracted_at
Create Date: 2026-02-18 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '017_created_at_publish_log'
down_revision = '016_extracted_at'
branch_labels = None
depends_on = None


def upgrade():
    # Add created_at field to intel_publish_log (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('intel_publish_log')]
    
    if 'created_at' not in existing_columns:
        # Add column as NOT NULL with default
        op.add_column('intel_publish_log', sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=True, server_default=sa.text('now()')))
        
        # Backfill existing rows: use published_at if available, otherwise now()
        op.execute("""
            UPDATE intel_publish_log
            SET created_at = COALESCE(published_at, now())
            WHERE created_at IS NULL;
        """)
        
        # Make created_at NOT NULL after backfilling
        op.alter_column('intel_publish_log', 'created_at', nullable=False, server_default=sa.text('now()'))
        
        # Create index for filtering by created_at
        existing_indexes = [idx['name'] for idx in inspector.get_indexes('intel_publish_log')]
        if 'idx_intel_publish_log_created_at' not in existing_indexes:
            op.create_index('idx_intel_publish_log_created_at', 'intel_publish_log', ['created_at'])


def downgrade():
    op.drop_index('idx_intel_publish_log_created_at', table_name='intel_publish_log')
    op.drop_column('intel_publish_log', 'created_at')
