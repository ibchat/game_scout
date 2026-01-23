#!/bin/bash
# Verification script for Trends Scout emerging games
# Ensures numeric signals are used and evergreen giants are excluded

set -e

API_URL="${API_URL:-http://localhost:8000}"

echo "=== Trends Scout Emerging Verification ==="
echo "API: ${API_URL}"
echo ""

# 1) Seed apps
echo "1. Seeding apps..."
SEED_RESPONSE=$(curl -sS -X POST "${API_URL}/api/v1/trends/admin/seed_apps" \
  -H "Content-Type: application/json" \
  -d '{"steam_app_ids":[620,570,730]}' 2>&1)
SEED_STATUS=$(echo "$SEED_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','error'))" 2>&1 || echo "error")
if [ "$SEED_STATUS" = "ok" ]; then
    echo "   ✓ Seeded apps"
else
    echo "   ✗ Seed failed: $SEED_STATUS"
    exit 1
fi

# 2) Ingest review signals from steam_review_daily
echo ""
echo "2. Ingesting review signals from steam_review_daily..."
INGEST_RESPONSE=$(curl -sS -X POST "${API_URL}/api/v1/trends/admin/ingest_reviews?days_back=0" 2>&1)
INGEST_STATUS=$(echo "$INGEST_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','error'))" 2>&1 || echo "error")
if [ "$INGEST_STATUS" = "ok" ]; then
    INGESTED=$(echo "$INGEST_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('ingested',0))" 2>&1 || echo "0")
    echo "   ✓ Ingested $INGESTED signals"
else
    echo "   ⚠ Ingest returned: $INGEST_STATUS"
fi

# 3) Aggregate
echo ""
echo "3. Aggregating daily trends..."
AGG_RESPONSE=$(curl -sS -X POST "${API_URL}/api/v1/trends/admin/aggregate?days_back=7" 2>&1)
AGG_STATUS=$(echo "$AGG_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','error'))" 2>&1 || echo "error")
if [ "$AGG_STATUS" = "ok" ]; then
    echo "   ✓ Aggregation completed"
else
    echo "   ✗ Aggregate failed: $AGG_STATUS"
    exit 1
fi

# 4) Check DB for today rows
echo ""
echo "4. Checking trends_game_daily for today..."
DB_CHECK=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
SELECT 
    g.steam_app_id,
    g.reviews_total IS NOT NULL as has_reviews_total,
    g.positive_ratio IS NOT NULL as has_positive_ratio,
    g.reviews_delta_7d,
    g.discussions_delta_7d
FROM trends_game_daily g
WHERE g.day = CURRENT_DATE
  AND g.steam_app_id IN (570, 620, 730)
ORDER BY g.steam_app_id;
" 2>&1 | tr -d ' \n' || echo "")

if [ -n "$DB_CHECK" ]; then
    echo "   ✓ DB rows exist for today"
    docker compose exec -T postgres psql -U postgres -d game_scout -c "
SELECT 
    g.steam_app_id,
    g.reviews_total,
    g.positive_ratio,
    g.reviews_delta_7d,
    g.discussions_delta_7d
FROM trends_game_daily g
WHERE g.day = CURRENT_DATE
  AND g.steam_app_id IN (570, 620, 730)
ORDER BY g.steam_app_id;
" 2>&1 | tail -5
else
    echo "   ✗ No DB rows found for today"
    exit 1
fi

# 5) Check numeric signals in trends_raw_signals
echo ""
echo "5. Checking numeric signals in trends_raw_signals..."
SIGNALS_CHECK=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
SELECT signal_type, COUNT(*)::int
FROM trends_raw_signals
WHERE steam_app_id IN (570, 620, 730)
  AND DATE(captured_at) = CURRENT_DATE
  AND value_numeric IS NOT NULL
GROUP BY signal_type
ORDER BY signal_type;
" 2>&1 | grep -v "^$" || echo "")

if [ -n "$SIGNALS_CHECK" ]; then
    echo "   ✓ Numeric signals found:"
    echo "$SIGNALS_CHECK" | head -10
else
    echo "   ⚠ No numeric signals found for today"
fi

# 6) Call emerging endpoint and check results
echo ""
echo "6. Calling /api/v1/trends/games/emerging..."
EMERGING_RESPONSE=$(curl -sS "${API_URL}/api/v1/trends/games/emerging?limit=50" 2>&1)
EMERGING_HTTP=$(curl -sS -o /dev/null -w "%{http_code}" "${API_URL}/api/v1/trends/games/emerging?limit=50" 2>&1)

if [ "$EMERGING_HTTP" -eq 200 ]; then
    echo "   ✓ Endpoint returns 200"
    
    # Check if Valve games appear with only tag match
    VALVE_GAMES=$(echo "$EMERGING_RESPONSE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
games = d.get('games', [])
valve_apps = {570, 620, 730}
found = []
for g in games:
    app_id = g.get('steam_app_id')
    if app_id in valve_apps:
        why = g.get('why_flagged', '')
        score = g.get('trend_score', 0)
        # Check if flagged only due to tags
        if 'tag' in why.lower() and score <= 2:
            found.append((app_id, why, score))
if found:
    print('FAIL: Valve games found with tag-only flags:', found)
    sys.exit(1)
else:
    print('OK: No Valve games with tag-only flags')
" 2>&1)
    
    echo "   $VALVE_GAMES"
    
    # Show top 5 games
    echo ""
    echo "   Top 5 emerging games:"
    echo "$EMERGING_RESPONSE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
games = d.get('games', [])[:5]
for g in games:
    print(f\"     {g.get('steam_app_id')}: {g.get('name', 'N/A')} (score={g.get('trend_score', 0)}, why={g.get('why_flagged', 'N/A')})\")
" 2>&1
    
else
    echo "   ✗ Endpoint returned HTTP $EMERGING_HTTP"
    exit 1
fi

echo ""
echo "=== Verification Complete ==="
