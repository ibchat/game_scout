#!/bin/bash
# Verify Emerging v4 DB setup
# Checks column names, data coverage, and diagnostics endpoint

set -e

echo "🔍 Verifying Emerging Engine v4 DB setup..."
echo ""

# Use docker exec to access postgres container
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-game_scout-postgres-1}"

# Check if container exists
if ! docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
    echo "⚠️  Postgres container '${POSTGRES_CONTAINER}' not found. Trying common names..."
    POSTGRES_CONTAINER=$(docker ps --format '{{.Names}}' | grep -i postgres | head -1)
    if [ -z "$POSTGRES_CONTAINER" ]; then
        echo "❌ No postgres container found. Please check docker compose ps"
        exit 1
    fi
    echo "✅ Using container: $POSTGRES_CONTAINER"
fi

docker exec -i "$POSTGRES_CONTAINER" psql -U postgres -d game_scout <<EOF
\echo '1️⃣ Detecting app_id column in steam_review_daily...'
SELECT column_name as detected_app_id_column
FROM information_schema.columns 
WHERE table_name = 'steam_review_daily' 
  AND table_schema = 'public'
  AND column_name IN ('app_id', 'steam_app_id', 'appid', 'steamid', 'game_id', 'steam_game_id')
ORDER BY CASE column_name
  WHEN 'app_id' THEN 1
  WHEN 'steam_app_id' THEN 2
  WHEN 'appid' THEN 3
  WHEN 'steamid' THEN 4
  WHEN 'game_id' THEN 5
  WHEN 'steam_game_id' THEN 6
END
LIMIT 1;

\echo ''
\echo '2️⃣ steam_review_daily stats...'
SELECT 
  COUNT(*) as total_rows,
  COUNT(DISTINCT steam_app_id) as distinct_apps,
  MIN(day) as min_day,
  MAX(day) as max_day
FROM steam_review_daily;

\echo ''
\echo '3️⃣ trends_seed_apps count...'
SELECT COUNT(*) as total_seed_apps
FROM trends_seed_apps
WHERE is_active = true;

\echo ''
\echo '4️⃣ Coverage: seed apps with reviews...'
SELECT COUNT(DISTINCT s.steam_app_id) as seed_with_reviews
FROM trends_seed_apps s
INNER JOIN steam_review_daily d ON d.steam_app_id = s.steam_app_id
WHERE s.is_active = true;

EOF

echo ""
echo "5️⃣ Waiting for API to be ready..."
sleep 3

echo ""
echo "6️⃣ Testing diagnostics endpoint..."
API_URL="${API_URL:-http://localhost:8000}"
if curl -sS --max-time 5 "${API_URL}/api/v1/trends/emerging/diagnostics" > /tmp/diagnostics.json 2>&1; then
    if command -v jq > /dev/null 2>&1; then
        cat /tmp/diagnostics.json | jq '.'
    else
        echo "⚠️  jq not installed, showing raw JSON:"
        cat /tmp/diagnostics.json
    fi
else
    echo "❌ Diagnostics endpoint failed. API might not be ready yet."
    echo "   Check with: docker compose logs api | tail -20"
fi

echo ""
echo "7️⃣ Testing system summary..."
if curl -sS --max-time 5 "${API_URL}/api/v1/admin/system/summary" > /tmp/summary.json 2>&1; then
    if command -v jq > /dev/null 2>&1; then
        echo "errors_today:"
        cat /tmp/summary.json | jq '.trends_today.errors_today // "N/A"'
        echo "coverage_reviews_pct:"
        cat /tmp/summary.json | jq '.trends_today.coverage_reviews_pct // "N/A"'
    else
        echo "⚠️  jq not installed, showing raw JSON:"
        cat /tmp/summary.json
    fi
else
    echo "❌ System summary endpoint failed."
fi

echo ""
echo "✅ Verification complete!"
