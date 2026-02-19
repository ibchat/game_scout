"""add extracted_at to intel_extracted_items

Revision ID: 016_extracted_at
Revises: 015_intel_source_health
Create Date: 2026-02-18 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '016_extracted_at'
down_revision = '015_intel_source_health'
branch_labels = None
depends_on = None


def upgrade():
    # Add extracted_at field to intel_extracted_items (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('intel_extracted_items')]
    
    if 'extracted_at' not in existing_columns:
        # Add column as nullable first
        op.add_column('intel_extracted_items', sa.Column('extracted_at', sa.TIMESTAMP(timezone=True), nullable=True, server_default=sa.text('now()')))
        
        # Update existing rows to use now() as extracted_at (backfill)
        op.execute("""
            UPDATE intel_extracted_items
            SET extracted_at = now()
            WHERE extracted_at IS NULL;
        """)
        
        # Make extracted_at NOT NULL after backfilling
        op.alter_column('intel_extracted_items', 'extracted_at', nullable=False, server_default=sa.text('now()'))
        
        # Create index for filtering by extracted_at
        existing_indexes = [idx['name'] for idx in inspector.get_indexes('intel_extracted_items')]
        if 'idx_intel_extracted_items_extracted_at' not in existing_indexes:
            op.create_index('idx_intel_extracted_items_extracted_at', 'intel_extracted_items', ['extracted_at'])


def downgrade():
    op.drop_index('idx_intel_extracted_items_extracted_at', table_name='intel_extracted_items')
    op.drop_column('intel_extracted_items', 'extracted_at')
