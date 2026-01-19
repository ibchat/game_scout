-- Создание таблицы relaunch_scan_runs для логирования сканов
-- Выполнить: psql -U postgres -d game_scout -f migrations/create_relaunch_scan_runs.sql

CREATE TABLE IF NOT EXISTS relaunch_scan_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMP WITH TIME ZONE,
    params JSONB,
    seed_found INTEGER DEFAULT 0,
    details_fetched INTEGER DEFAULT 0,
    eligible INTEGER DEFAULT 0,
    added INTEGER DEFAULT 0,
    excluded JSONB,
    status TEXT NOT NULL DEFAULT 'running',
    error_text TEXT,
    scanner_version TEXT,
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_relaunch_scan_runs_started_at ON relaunch_scan_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_relaunch_scan_runs_status ON relaunch_scan_runs(status);
CREATE INDEX IF NOT EXISTS idx_relaunch_scan_runs_scanner_version ON relaunch_scan_runs(scanner_version);
