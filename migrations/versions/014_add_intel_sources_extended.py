"""add intel sources extended

Revision ID: 014_add_intel_sources_extended
Revises: 013_intel_event_significance
Create Date: 2026-02-17 22:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '014_add_intel_sources_extended'
down_revision = '013_intel_event_significance'
branch_labels = None
depends_on = None


def upgrade():
    # Add new sources via INSERT (additive-only)
    # Check if source exists before inserting to avoid duplicates
    sources = [
        ('Steam Community Announcements', 'rss', 'https://steamcommunity.com/games/steam/rss/'),
        ('SteamDB News', 'rss', 'https://steamdb.info/feeds/news/'),
        ('Reddit r/Steam', 'rss', 'https://www.reddit.com/r/Steam/.rss'),
        ('Reddit r/pcgaming', 'rss', 'https://www.reddit.com/r/pcgaming/.rss'),
        ('Reddit r/gaming', 'rss', 'https://www.reddit.com/r/gaming/.rss'),
        ('Reddit r/indiegames', 'rss', 'https://www.reddit.com/r/indiegames/.rss'),
        ('Google News Steam Release', 'rss', 'https://news.google.com/rss/search?q=Steam+game+release&hl=en-US&gl=US&ceid=US:en'),
        ('Google News Steam Update', 'rss', 'https://news.google.com/rss/search?q=Steam+game+update&hl=en-US&gl=US&ceid=US:en'),
        ('Google News Steam Discount', 'rss', 'https://news.google.com/rss/search?q=Steam+discount&hl=en-US&gl=US&ceid=US:en'),
        ('Google News Steam Publisher', 'rss', 'https://news.google.com/rss/search?q=Steam+publisher+deal&hl=en-US&gl=US&ceid=US:en')
    ]
    
    for name, source_type, url in sources:
        # Check if source already exists
        check_query = sa.text("SELECT id FROM intel_sources WHERE name = :name")
        result = op.get_bind().execute(check_query, {"name": name})
        if result.fetchone() is None:
            # Insert new source
            insert_query = sa.text("""
                INSERT INTO intel_sources (id, name, type, url, is_enabled, created_at, updated_at)
                VALUES (gen_random_uuid(), :name, :type, :url, true, now(), now())
            """)
            op.get_bind().execute(insert_query, {"name": name, "type": source_type, "url": url})


def downgrade():
    # Remove added sources
    op.execute("""
        DELETE FROM intel_sources 
        WHERE name IN (
            'Steam Community Announcements',
            'SteamDB News',
            'Reddit r/Steam',
            'Reddit r/pcgaming',
            'Reddit r/gaming',
            'Reddit r/indiegames',
            'Google News Steam Release',
            'Google News Steam Update',
            'Google News Steam Discount',
            'Google News Steam Publisher'
        );
    """)
