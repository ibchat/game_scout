-- Data Truth Check for Deals / Intent
-- Run: docker exec -i postgres psql -U postgres -d game_scout < scripts/check_deals_data.sql

\echo '=== Step 1: deal_intent_game table ==='
SELECT 
    COUNT(*) as total_rows,
    COUNT(*) FILTER (WHERE steam_name IS NOT NULL AND steam_name != '') as with_name,
    COUNT(*) FILTER (WHERE release_date IS NOT NULL) as with_release_date,
    COUNT(*) FILTER (WHERE steam_name LIKE 'App %' OR steam_name LIKE 'App #%') as app_format_names
FROM deal_intent_game;

\echo ''
\echo '=== Step 2: steam_app_cache coverage ==='
SELECT 
    COUNT(DISTINCT d.app_id) as total_deals,
    COUNT(DISTINCT d.app_id) FILTER (WHERE c.steam_app_id IS NOT NULL) as with_cache,
    COUNT(DISTINCT d.app_id) FILTER (WHERE c.name IS NOT NULL AND c.name != '') as cache_with_name,
    COUNT(DISTINCT d.app_id) FILTER (WHERE c.release_date IS NOT NULL) as cache_with_release
FROM deal_intent_game d
LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint;

\echo ''
\echo '=== Step 3: steam_app_facts coverage ==='
SELECT 
    COUNT(DISTINCT d.app_id) as total_deals,
    COUNT(DISTINCT d.app_id) FILTER (WHERE f.steam_app_id IS NOT NULL) as with_facts,
    COUNT(DISTINCT d.app_id) FILTER (WHERE f.name IS NOT NULL AND f.name != '') as facts_with_name,
    COUNT(DISTINCT d.app_id) FILTER (WHERE f.release_date IS NOT NULL) as facts_with_release
FROM deal_intent_game d
LEFT JOIN steam_app_facts f ON f.steam_app_id = d.app_id;

\echo ''
\echo '=== Step 4: Sample problematic rows (App #### format) ==='
SELECT 
    d.app_id,
    d.steam_name as deal_name,
    c.name as cache_name,
    f.name as facts_name,
    CASE 
        WHEN c.name IS NOT NULL THEN 'cache'
        WHEN f.name IS NOT NULL THEN 'facts'
        ELSE 'no source'
    END as source
FROM deal_intent_game d
LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
LEFT JOIN steam_app_facts f ON f.steam_app_id = d.app_id
WHERE d.steam_name LIKE 'App %' OR d.steam_name LIKE 'App #%'
LIMIT 10;

\echo ''
\echo '=== Step 5: Old games (>4 years) ==='
SELECT 
    COUNT(*) as old_games_count,
    COUNT(*) FILTER (WHERE COALESCE(c.release_date, f.release_date, d.release_date) < CURRENT_DATE - INTERVAL '4 years') as older_than_4_years
FROM deal_intent_game d
LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
LEFT JOIN steam_app_facts f ON f.steam_app_id = d.app_id;

\echo ''
\echo '=== Step 6: Games without release_date ==='
SELECT 
    COUNT(*) as no_release_date,
    COUNT(*) FILTER (WHERE c.release_date IS NULL AND f.release_date IS NULL AND d.release_date IS NULL) as completely_missing
FROM deal_intent_game d
LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
LEFT JOIN steam_app_facts f ON f.steam_app_id = d.app_id;

\echo ''
\echo '=== Step 7: Example of what API should return ==='
SELECT 
    d.app_id,
    COALESCE(
        NULLIF(c.name, ''),
        NULLIF(f.name, ''),
        NULLIF(d.steam_name, ''),
        'App ' || d.app_id::text
    ) as title,
    COALESCE(c.release_date, f.release_date, d.release_date) as release_date,
    d.intent_score,
    d.quality_score
FROM deal_intent_game d
LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
LEFT JOIN steam_app_facts f ON f.steam_app_id = d.app_id
WHERE d.intent_score > 0
ORDER BY d.intent_score DESC
LIMIT 10;
