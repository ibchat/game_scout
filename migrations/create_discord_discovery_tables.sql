-- Discord Discovery Tables
-- Part A: Data model for invite discovery, guild tracking, and channel management

-- 1. discord_invite_candidate: Stores discovered invite links (leads)
CREATE TABLE IF NOT EXISTS discord_invite_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invite_code TEXT UNIQUE NOT NULL,
    invite_url TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('disboard', 'topgg', 'discordme', 'reddit', 'twitter', 'website', 'manual')),
    source_url TEXT,
    found_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_resolved_at TIMESTAMPTZ,
    resolve_status TEXT NOT NULL DEFAULT 'new' CHECK (resolve_status IN ('new', 'ok', 'invalid', 'expired', 'rate_limited', 'forbidden', 'error')),
    resolve_http_status INT,
    guild_id TEXT,
    guild_name TEXT,
    guild_icon_url TEXT,
    approx_member_count INT,
    approx_online_count INT,
    channel_id TEXT,
    channel_name TEXT,
    expires_at TIMESTAMPTZ,
    raw_invite_json JSONB,
    quality_score FLOAT DEFAULT 0,
    notes TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_discord_invite_candidate_code ON discord_invite_candidate(invite_code);
CREATE INDEX IF NOT EXISTS idx_discord_invite_candidate_status_found ON discord_invite_candidate(resolve_status, found_at DESC);
CREATE INDEX IF NOT EXISTS idx_discord_invite_candidate_quality ON discord_invite_candidate(quality_score DESC);

-- 2. discord_guild: Stores confirmed servers we work with
CREATE TABLE IF NOT EXISTS discord_guild (
    guild_id TEXT PRIMARY KEY,
    guild_name TEXT NOT NULL,
    discovered_via_invite_code TEXT REFERENCES discord_invite_candidate(invite_code),
    added_bot BOOLEAN DEFAULT false,
    bot_joined_at TIMESTAMPTZ,
    last_channels_sync_at TIMESTAMPTZ,
    guild_score FLOAT DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    tags TEXT[] DEFAULT '{}',
    raw_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discord_guild_score ON discord_guild(guild_score DESC);
CREATE INDEX IF NOT EXISTS idx_discord_guild_active ON discord_guild(is_active, guild_score DESC);

-- 3. discord_channel: Channels within guilds
CREATE TABLE IF NOT EXISTS discord_channel (
    channel_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL REFERENCES discord_guild(guild_id) ON DELETE CASCADE,
    channel_name TEXT NOT NULL,
    channel_type TEXT DEFAULT 'text' CHECK (channel_type IN ('text', 'forum', 'announcement', 'voice', 'unknown')),
    is_visible_to_bot BOOLEAN DEFAULT false,
    scan_enabled BOOLEAN DEFAULT false,
    priority INT DEFAULT 0,
    last_scanned_message_id TEXT,
    last_scanned_at TIMESTAMPTZ,
    activity_score FLOAT DEFAULT 0,
    raw_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discord_channel_guild_scan ON discord_channel(guild_id, scan_enabled);
CREATE INDEX IF NOT EXISTS idx_discord_channel_activity ON discord_channel(activity_score DESC);

-- Add updated_at trigger for discord_guild
CREATE OR REPLACE FUNCTION update_discord_guild_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_discord_guild_updated_at
    BEFORE UPDATE ON discord_guild
    FOR EACH ROW
    EXECUTE FUNCTION update_discord_guild_updated_at();

-- Add updated_at trigger for discord_channel
CREATE OR REPLACE FUNCTION update_discord_channel_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_discord_channel_updated_at
    BEFORE UPDATE ON discord_channel
    FOR EACH ROW
    EXECUTE FUNCTION update_discord_channel_updated_at();
