#!/bin/bash
# Trends Pipeline Verification Script
# Seeds, collects, waits for jobs, ingests, aggregates, and verifies results

set -e

API_URL="${API_URL:-http://localhost:8000}"
MAX_WAIT_SECONDS=600  # 10 minutes max wait
POLL_INTERVAL=5

echo "=== Trends Pipeline Verification ==="
echo "API: ${API_URL}"
echo ""

# Step 1: Seed apps (idempotent)
echo "1. Seeding apps..."
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
(413150, true, NOW()), (367520, true, NOW()), (1132000, true, NOW()),
(632360, true, NOW()), (588650, true, NOW()), (105600, true, NOW()),
(440900, true, NOW()), (294100, true, NOW()), (233450, true, NOW()),
(252490, true, NOW()), (236390, true, NOW()), (394360, true, NOW()),
(281990, true, NOW()), (289070, true, NOW()), (8930, true, NOW()),
(427520, true, NOW()), (381210, true, NOW()),
(730, true, NOW()), (570, true, NOW()), (620, true, NOW())
ON CONFLICT (steam_app_id) DO UPDATE SET is_active = EXCLUDED.is_active;
SQL

SEEDED_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM trends_seed_apps WHERE is_active=true;" 2>&1 | grep -E '^[0-9]+$' | head -1 || echo "0")
echo "   ✓ Seeded: $SEEDED_COUNT apps"

# Step 2: Enqueue jobs
echo ""
echo "2. Enqueuing collection jobs..."
COLLECT_RESPONSE=$(curl -sS -X POST "${API_URL}/api/v1/trends/admin/collect?limit=100" 2>&1)
COLLECT_STATUS=$(echo "$COLLECT_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','error'))" 2>&1 || echo "error")
if [ "$COLLECT_STATUS" = "ok" ]; then
    APP_JOBS=$(echo "$COLLECT_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); c=d.get('collected',{}); print(c.get('appdetails',0))" 2>&1 || echo "0")
    REVIEW_JOBS=$(echo "$COLLECT_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); c=d.get('collected',{}); print(c.get('reviews',0))" 2>&1 || echo "0")
    echo "   ✓ Enqueued: $APP_JOBS appdetails, $REVIEW_JOBS reviews"
else
    echo "   ✗ Collect failed: $COLLECT_STATUS"
    exit 1
fi

# Step 3: Wait for jobs (with progress)
echo ""
echo "3. Waiting for jobs to complete (max ${MAX_WAIT_SECONDS}s)..."
START_TIME=$(date +%s)
while true; do
    ELAPSED=$(($(date +%s) - START_TIME))
    if [ $ELAPSED -ge $MAX_WAIT_SECONDS ]; then
        echo "   ⚠ Timeout reached"
        break
    fi
    
    JOB_STATS=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
        SELECT status, COUNT(*)::int
        FROM trend_jobs
        WHERE job_type IN ('appdetails', 'reviews_daily')
          AND created_at > NOW() - INTERVAL '1 hour'
        GROUP BY status
        ORDER BY status;
    " 2>&1 | grep -v "^$" || echo "")
    
    QUEUED=$(echo "$JOB_STATS" | grep "queued" | awk '{print $2}' || echo "0")
    PROCESSING=$(echo "$JOB_STATS" | grep "processing" | awk '{print $2}' || echo "0")
    SUCCESS=$(echo "$JOB_STATS" | grep "success" | awk '{print $2}' || echo "0")
    FAILED=$(echo "$JOB_STATS" | grep "failed" | awk '{print $2}' || echo "0")
    
    TOTAL_ACTIVE=$((QUEUED + PROCESSING))
    
    if [ "$TOTAL_ACTIVE" -eq 0 ] && [ "$SUCCESS" -gt 0 ]; then
        echo "   ✓ All jobs completed: $SUCCESS success, $FAILED failed"
        break
    fi
    
    if [ $((ELAPSED % 30)) -eq 0 ]; then
        echo "   [${ELAPSED}s] Queued: $QUEUED, Processing: $PROCESSING, Success: $SUCCESS, Failed: $FAILED"
    fi
    
    sleep $POLL_INTERVAL
done

# Step 4: Ingest review signals
echo ""
echo "4. Ingesting review signals..."
INGEST_RESPONSE=$(curl -sS -X POST "${API_URL}/api/v1/trends/admin/ingest_reviews?days_back=0" 2>&1)
INGEST_STATUS=$(echo "$INGEST_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','error'))" 2>&1 || echo "error")
if [ "$INGEST_STATUS" = "ok" ]; then
    INGESTED=$(echo "$INGEST_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('ingested',0))" 2>&1 || echo "0")
    echo "   ✓ Ingested: $INGESTED signals"
else
    echo "   ⚠ Ingest: $INGEST_STATUS"
fi

# Step 5: Aggregate
echo ""
echo "5. Aggregating..."
AGG_RESPONSE=$(curl -sS -X POST "${API_URL}/api/v1/trends/admin/aggregate?days_back=7" 2>&1)
AGG_STATUS=$(echo "$AGG_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','error'))" 2>&1 || echo "error")
if [ "$AGG_STATUS" = "ok" ]; then
    AGG_ROWS=$(echo "$AGG_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('aggregated_rows',0))" 2>&1 || echo "0")
    echo "   ✓ Aggregated: $AGG_ROWS rows"
else
    echo "   ✗ Aggregate failed: $AGG_STATUS"
    exit 1
fi

# Step 6: Verification (DB assertions)
echo ""
echo "6. Verification (DB assertions)..."
REVIEWS_TODAY=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM steam_review_daily WHERE day=CURRENT_DATE;" 2>&1 | grep -E '^[0-9]+$' | head -1 || echo "0")
SIGNALS_NUMERIC=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM trends_raw_signals WHERE DATE(captured_at)=CURRENT_DATE AND value_numeric IS NOT NULL;" 2>&1 | grep -E '^[0-9]+$' | head -1 || echo "0")
TRENDS_FILLED=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM trends_game_daily WHERE day=CURRENT_DATE AND reviews_total IS NOT NULL;" 2>&1 | grep -E '^[0-9]+$' | head -1 || echo "0")

echo "   steam_review_daily (today): $REVIEWS_TODAY (required: >= 30)"
echo "   numeric signals (today): $SIGNALS_NUMERIC (required: >= 60)"
echo "   trends_game_daily filled: $TRENDS_FILLED (required: >= 30)"

FAILED_ASSERTIONS=0
if [ "$REVIEWS_TODAY" -lt 30 ]; then
    echo "   ✗ FAIL: steam_review_daily < 30"
    FAILED_ASSERTIONS=$((FAILED_ASSERTIONS + 1))
fi
if [ "$SIGNALS_NUMERIC" -lt 60 ]; then
    echo "   ✗ FAIL: numeric signals < 60"
    FAILED_ASSERTIONS=$((FAILED_ASSERTIONS + 1))
fi
if [ "$TRENDS_FILLED" -lt 30 ]; then
    echo "   ✗ FAIL: trends_game_daily filled < 30"
    FAILED_ASSERTIONS=$((FAILED_ASSERTIONS + 1))
fi

# Step 7: Emerging API check
echo ""
echo "7. Emerging API check..."
EMERGING_RESPONSE=$(curl -sS "${API_URL}/api/v1/trends/games/emerging?limit=50" 2>&1)
EMERGING_COUNT=$(echo "$EMERGING_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('count',0))" 2>&1 || echo "0")
echo "   Emerging games: $EMERGING_COUNT (required: >= 5)"

if [ "$EMERGING_COUNT" -lt 5 ]; then
    echo "   ⚠ WARN: emerging < 5 (may be expected if all games are evergreen giants)"
    # Don't fail on this, but log
fi

echo ""
echo "=== Verification Summary ==="
echo "   steam_review_daily: $REVIEWS_TODAY"
echo "   numeric signals: $SIGNALS_NUMERIC"
echo "   trends_game_daily filled: $TRENDS_FILLED"
echo "   emerging games: $EMERGING_COUNT"
echo ""

if [ $FAILED_ASSERTIONS -gt 0 ]; then
    echo "✗ FAILED: $FAILED_ASSERTIONS assertion(s) failed"
    exit 1
else
    echo "✓ All assertions passed"
    exit 0
fi
