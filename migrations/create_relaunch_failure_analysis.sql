-- Создание таблицы relaunch_failure_analysis для диагностики провала
-- Выполнить: psql -U postgres -d game_scout -f migrations/create_relaunch_failure_analysis.sql

CREATE TABLE IF NOT EXISTS relaunch_failure_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id UUID NOT NULL REFERENCES relaunch_apps(id) ON DELETE CASCADE,
    failure_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence_map JSONB NOT NULL DEFAULT '{}'::jsonb,
    suggested_angles JSONB NOT NULL DEFAULT '[]'::jsonb,
    signals JSONB NOT NULL DEFAULT '{}'::jsonb,
    computed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(app_id, computed_at)
);

CREATE INDEX IF NOT EXISTS idx_relaunch_failure_analysis_app_id ON relaunch_failure_analysis(app_id);
CREATE INDEX IF NOT EXISTS idx_relaunch_failure_analysis_computed_at ON relaunch_failure_analysis(computed_at DESC);
