"""add intel sources extended

Revision ID: 014_add_intel_sources_extended
Revises: 013_intel_event_significance
Create Date: 2026-02-17 22:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '014_add_intel_sources_extended'
down_revision = '013_intel_event_significance'
branch_labels = None
depends_on = None


def upgrade():
    # Add new sources via INSERT (additive-only)
    op.execute("""
        INSERT INTO intel_sources (id, name, type, url, is_enabled, created_at, updated_at)
        VALUES 
        (gen_random_uuid(), 'Steam Community Announcements', 'rss', 'https://steamcommunity.com/games/steam/rss/', true, now(), now()),
        (gen_random_uuid(), 'SteamDB News', 'rss', 'https://steamdb.info/feeds/news/', true, now(), now()),
        (gen_random_uuid(), 'Reddit r/Steam', 'rss', 'https://www.reddit.com/r/Steam/.rss', true, now(), now()),
        (gen_random_uuid(), 'Reddit r/pcgaming', 'rss', 'https://www.reddit.com/r/pcgaming/.rss', true, now(), now()),
        (gen_random_uuid(), 'Reddit r/gaming', 'rss', 'https://www.reddit.com/r/gaming/.rss', true, now(), now()),
        (gen_random_uuid(), 'Reddit r/indiegames', 'rss', 'https://www.reddit.com/r/indiegames/.rss', true, now(), now()),
        (gen_random_uuid(), 'Google News Steam Release', 'rss', 'https://news.google.com/rss/search?q=Steam+game+release&hl=en-US&gl=US&ceid=US:en', true, now(), now()),
        (gen_random_uuid(), 'Google News Steam Update', 'rss', 'https://news.google.com/rss/search?q=Steam+game+update&hl=en-US&gl=US&ceid=US:en', true, now(), now()),
        (gen_random_uuid(), 'Google News Steam Discount', 'rss', 'https://news.google.com/rss/search?q=Steam+discount&hl=en-US&gl=US&ceid=US:en', true, now(), now()),
        (gen_random_uuid(), 'Google News Steam Publisher', 'rss', 'https://news.google.com/rss/search?q=Steam+publisher+deal&hl=en-US&gl=US&ceid=US:en', true, now(), now())
        ON CONFLICT (name) DO NOTHING;
    """)


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
