#!/bin/bash
# Trends Scout Pipeline Runner
# Seeds apps, enqueues jobs, processes, aggregates, and shows results

set -e

API_URL="${API_URL:-http://localhost:8000}"
MAX_WAIT_SECONDS=300  # 5 minutes max wait for jobs
POLL_INTERVAL=5       # Check every 5 seconds

echo "=== Trends Scout Pipeline ==="
echo "API: ${API_URL}"
echo ""

# Step 1: Seed apps
echo "1. Seeding apps..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/seed_trends_apps.sql" ]; then
    docker compose exec -T postgres psql -U postgres -d game_scout -f "${SCRIPT_DIR}/seed_trends_apps.sql" > /dev/null 2>&1
else
    # Fallback: inline SQL
    docker compose exec -T postgres psql -U postgres -d game_scout <<'SQL' > /dev/null 2>&1
INSERT INTO trends_seed_apps (steam_app_id, is_active, created_at)
SELECT DISTINCT steam_app_id, true, NOW()
FROM steam_app_cache
WHERE steam_app_id NOT IN (SELECT steam_app_id FROM trends_seed_apps)
  AND steam_app_id IS NOT NULL
LIMIT 200
ON CONFLICT (steam_app_id) DO UPDATE SET is_active = EXCLUDED.is_active;

INSERT INTO trends_seed_apps (steam_app_id, is_active, created_at)
VALUES
(413150, true, NOW()), (367520, true, NOW()), (239140, true, NOW()),
(252490, true, NOW()), (1132000, true, NOW()), (632360, true, NOW()),
(588650, true, NOW()), (105600, true, NOW()), (440900, true, NOW()),
(294100, true, NOW()), (233450, true, NOW()), (346110, true, NOW()),
(359550, true, NOW()), (236390, true, NOW()), (394360, true, NOW()),
(281990, true, NOW()), (289070, true, NOW()), (8930, true, NOW()),
(427520, true, NOW()), (381210, true, NOW()),
(730, true, NOW()), (570, true, NOW()), (620, true, NOW())
ON CONFLICT (steam_app_id) DO UPDATE SET is_active = EXCLUDED.is_active;
SQL
fi

SEEDED_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM trends_seed_apps WHERE is_active=true;" 2>&1 | tr -d ' \n' || echo "0")
echo "   ✓ Seeded apps: $SEEDED_COUNT active"

# Step 2: Enqueue jobs
echo ""
echo "2. Enqueuing collection jobs..."
COLLECT_RESPONSE=$(curl -sS -X POST "${API_URL}/api/v1/trends/admin/collect?limit=500" 2>&1)
COLLECT_STATUS=$(echo "$COLLECT_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','error'))" 2>&1 || echo "error")
if [ "$COLLECT_STATUS" = "ok" ]; then
    APP_JOBS=$(echo "$COLLECT_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); c=d.get('collected',{}); print(c.get('appdetails',0))" 2>&1 || echo "0")
    REVIEW_JOBS=$(echo "$COLLECT_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); c=d.get('collected',{}); print(c.get('reviews',0))" 2>&1 || echo "0")
    echo "   ✓ Enqueued: $APP_JOBS appdetails, $REVIEW_JOBS reviews jobs"
else
    echo "   ✗ Collect failed: $COLLECT_STATUS"
    exit 1
fi

# Step 3: Wait for jobs (with timeout)
echo ""
echo "3. Waiting for jobs to complete (max ${MAX_WAIT_SECONDS}s)..."
START_TIME=$(date +%s)
while true; do
    ELAPSED=$(($(date +%s) - START_TIME))
    if [ $ELAPSED -ge $MAX_WAIT_SECONDS ]; then
        echo "   ⚠ Timeout reached, proceeding anyway"
        break
    fi
    
    JOB_STATS=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
        SELECT 
            status,
            COUNT(*)::int
        FROM trend_jobs
        WHERE job_type IN ('appdetails', 'reviews_daily')
          AND created_at > NOW() - INTERVAL '1 hour'
        GROUP BY status
        ORDER BY status;
    " 2>&1 | grep -v "^$" || echo "")
    
    QUEUED=$(echo "$JOB_STATS" | grep "queued" | awk '{print $2}' || echo "0")
    RUNNING=$(echo "$JOB_STATS" | grep "running" | awk '{print $2}' || echo "0")
    SUCCESS=$(echo "$JOB_STATS" | grep "success" | awk '{print $2}' || echo "0")
    FAILED=$(echo "$JOB_STATS" | grep "failed" | awk '{print $2}' || echo "0")
    
    TOTAL_ACTIVE=$((QUEUED + RUNNING))
    
    if [ "$TOTAL_ACTIVE" -eq 0 ] && [ "$SUCCESS" -gt 0 ]; then
        echo "   ✓ All jobs completed: $SUCCESS success, $FAILED failed"
        break
    fi
    
    echo "   [${ELAPSED}s] Queued: $QUEUED, Running: $RUNNING, Success: $SUCCESS, Failed: $FAILED"
    sleep $POLL_INTERVAL
done

# Step 4: Ingest review signals
echo ""
echo "4. Ingesting review signals..."
INGEST_RESPONSE=$(curl -sS -X POST "${API_URL}/api/v1/trends/admin/ingest_reviews?days_back=0" 2>&1)
INGEST_STATUS=$(echo "$INGEST_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','error'))" 2>&1 || echo "error")
if [ "$INGEST_STATUS" = "ok" ]; then
    INGESTED=$(echo "$INGEST_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('ingested',0))" 2>&1 || echo "0")
    echo "   ✓ Ingested $INGESTED signals"
else
    echo "   ⚠ Ingest returned: $INGEST_STATUS"
fi

# Step 5: Aggregate
echo ""
echo "5. Aggregating daily trends..."
AGG_RESPONSE=$(curl -sS -X POST "${API_URL}/api/v1/trends/admin/aggregate?days_back=7" 2>&1)
AGG_STATUS=$(echo "$AGG_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','error'))" 2>&1 || echo "error")
if [ "$AGG_STATUS" = "ok" ]; then
    AGG_ROWS=$(echo "$AGG_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('aggregated_rows',0))" 2>&1 || echo "0")
    echo "   ✓ Aggregated $AGG_ROWS rows"
else
    echo "   ✗ Aggregate failed: $AGG_STATUS"
    exit 1
fi

# Step 6: Verification queries
echo ""
echo "6. Verification:"
echo "   - Seed apps:"
docker compose exec -T postgres psql -U postgres -d game_scout -c "SELECT COUNT(*)::int as total FROM trends_seed_apps WHERE is_active=true;" 2>&1 | grep -E "total|[0-9]+" | head -2

echo "   - Job status:"
docker compose exec -T postgres psql -U postgres -d game_scout -c "
    SELECT 
        job_type,
        status,
        COUNT(*)::int
    FROM trend_jobs
    WHERE created_at > NOW() - INTERVAL '1 hour'
    GROUP BY job_type, status
    ORDER BY job_type, status;
" 2>&1 | head -10

echo "   - trends_game_daily (today):"
docker compose exec -T postgres psql -U postgres -d game_scout -c "
    SELECT COUNT(*)::int as rows_today
    FROM trends_game_daily
    WHERE day = CURRENT_DATE;
" 2>&1 | grep -E "rows_today|[0-9]+" | head -2

echo "   - Numeric signals (today):"
docker compose exec -T postgres psql -U postgres -d game_scout -c "
    SELECT 
        signal_type,
        COUNT(*)::int as total,
        SUM(CASE WHEN value_numeric IS NOT NULL THEN 1 ELSE 0 END)::int as numeric_count
    FROM trends_raw_signals
    WHERE DATE(captured_at) = CURRENT_DATE
      AND source = 'steam_reviews'
    GROUP BY signal_type
    ORDER BY signal_type;
" 2>&1 | head -10

# Step 7: Emerging games
echo ""
echo "7. Emerging games (top 20):"
EMERGING_RESPONSE=$(curl -sS "${API_URL}/api/v1/trends/games/emerging?limit=20" 2>&1)
EMERGING_COUNT=$(echo "$EMERGING_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('count',0))" 2>&1 || echo "0")
echo "   Count: $EMERGING_COUNT"
echo ""
echo "$EMERGING_RESPONSE" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    games = d.get('games', [])[:20]
    for i, g in enumerate(games, 1):
        print(f\"   {i}. {g.get('steam_app_id')}: {g.get('name', 'N/A')} (score={g.get('trend_score', 0)}, why={g.get('why_flagged', 'N/A')})\")
except Exception as e:
    print(f\"   Error parsing: {e}\")
    print(sys.stdin.read()[:500])
" 2>&1

echo ""
echo "=== Pipeline Complete ==="
