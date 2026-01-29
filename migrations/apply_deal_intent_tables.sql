-- Apply deal_intent tables migration manually
-- This is a direct SQL version of 003_create_deal_intent_tables.py

-- deal_intent_game - snapshot по игре
CREATE TABLE IF NOT EXISTS deal_intent_game (
    app_id INTEGER PRIMARY KEY,
    steam_name TEXT,
    steam_url TEXT,
    developer_name TEXT,
    publisher_name TEXT,
    release_date DATE,
    stage TEXT,  -- coming_soon | demo | early_access | released
    has_demo BOOLEAN DEFAULT FALSE,
    price_eur NUMERIC(10, 2),
    tags JSONB,
    external_links JSONB,
    intent_score INTEGER DEFAULT 0,
    quality_score INTEGER DEFAULT 0,
    intent_reasons JSONB,
    quality_reasons JSONB,
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_deal_intent_game_intent_score ON deal_intent_game(intent_score);
CREATE INDEX IF NOT EXISTS idx_deal_intent_game_quality_score ON deal_intent_game(quality_score);
CREATE INDEX IF NOT EXISTS idx_deal_intent_game_stage ON deal_intent_game(stage);
CREATE INDEX IF NOT EXISTS idx_deal_intent_game_updated_at ON deal_intent_game(updated_at);

-- deal_intent_signal - внешние сигналы
CREATE TABLE IF NOT EXISTS deal_intent_signal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id INTEGER,
    source TEXT,  -- steam, twitter, linkedin, etc
    url TEXT,
    text TEXT,
    signal_type TEXT,  -- intent_keyword, external_link, etc
    confidence FLOAT DEFAULT 0.0,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_deal_intent_signal_app_id ON deal_intent_signal(app_id);
CREATE INDEX IF NOT EXISTS idx_deal_intent_signal_source ON deal_intent_signal(source);
CREATE INDEX IF NOT EXISTS idx_deal_intent_signal_type ON deal_intent_signal(signal_type);
CREATE INDEX IF NOT EXISTS idx_deal_intent_signal_created_at ON deal_intent_signal(created_at);

-- deal_intent_action_log - логи действий
CREATE TABLE IF NOT EXISTS deal_intent_action_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id INTEGER,
    action_type TEXT,  -- request_pitch_deck, request_steamworks, send_offer, book_call, watchlist
    payload JSONB,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_deal_intent_action_log_app_id ON deal_intent_action_log(app_id);
CREATE INDEX IF NOT EXISTS idx_deal_intent_action_log_action_type ON deal_intent_action_log(action_type);
CREATE INDEX IF NOT EXISTS idx_deal_intent_action_log_created_at ON deal_intent_action_log(created_at);

-- Update alembic_version if needed
-- INSERT INTO alembic_version (version_num) VALUES ('003_deal_intent') ON CONFLICT DO NOTHING;
