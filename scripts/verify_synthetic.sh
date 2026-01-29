#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
DB_SERVICE="${DB_SERVICE:-postgres}"
DB_NAME="${DB_NAME:-game_scout}"
DB_USER="${DB_USER:-postgres}"

echo "=== Проверка Synthetic UI Check ==="
echo

fail=0

fetch_list() { curl -4 -sS "$1"; }

psql_db() {
  local sql="$1"
  docker compose exec -T "$DB_SERVICE" bash -lc "export PAGER=cat; psql -U '$DB_USER' -d '$DB_NAME' -Atc \"$sql\""
}

echo "S1. Проверка synthetic_only=true..."
LIST_JSON="$(fetch_list "$API_BASE/api/v1/deals/list?limit=50&synthetic_only=true&min_intent_score=0&min_quality_score=0")"
COUNT="$(echo "$LIST_JSON" | jq -r '.count // 0')"
APP_IDS="$(echo "$LIST_JSON" | jq -r '.games[]?.app_id' || true)"

echo "  count: $COUNT"
echo "  app_ids: ${APP_IDS:-<empty>}"

if [[ "$COUNT" -ge 1 ]]; then
  echo "✅ PASS: synthetic_only=true вернул count = $COUNT"
else
  echo "❌ FAIL: synthetic_only=true вернул count = $COUNT"
  fail=1
fi

if echo "$APP_IDS" | grep -qxE "(999999|1410400)"; then
  echo "✅ PASS: найден app_id=999999 или 1410400 в synthetic_only=true"
else
  echo "❌ FAIL: нет app_id=999999/1410400 в synthetic_only=true"
  fail=1
fi
echo

echo "S2. Проверка steam_url NOT NULL..."
NULL_URLS="$(echo "$LIST_JSON" | jq -r '[.games[]? | select((.steam_url // "") == "")] | length')"
if [[ "$NULL_URLS" -eq 0 ]]; then
  echo "✅ PASS: все $COUNT игр имеют steam_url NOT NULL"
else
  echo "❌ FAIL: найдено $NULL_URLS игр без steam_url"
  fail=1
fi
echo

echo "S3. Проверка games.tags NOT NULL (через БД)..."
FIRST_APP_ID="$(echo "$LIST_JSON" | jq -r '.games[0].app_id // empty')"
if [[ -z "${FIRST_APP_ID:-}" ]]; then
  echo "❌ FAIL: synthetic_only список пуст — не с чем проверять tags"
  fail=1
else
  TAGS_NULL_CNT="$(psql_db "SELECT COUNT(*) FROM games WHERE source='steam' AND source_id='${FIRST_APP_ID}' AND tags IS NULL;")"
  GAMES_CNT="$(psql_db "SELECT COUNT(*) FROM games WHERE source='steam' AND source_id='${FIRST_APP_ID}';")"
  echo "  games rows: $GAMES_CNT"
  echo "  tags IS NULL rows: $TAGS_NULL_CNT"

  if [[ "$GAMES_CNT" -ge 1 ]] && [[ "$TAGS_NULL_CNT" -eq 0 ]]; then
    echo "✅ PASS: games.tags NOT NULL для app_id=$FIRST_APP_ID"
  else
    echo "❌ FAIL: games.tags NULL или нет строки в games для app_id=$FIRST_APP_ID"
    fail=1
  fi
fi
echo

echo "S4. Проверка default (synthetic_only=false)..."
DEFAULT_JSON="$(fetch_list "$API_BASE/api/v1/deals/list?limit=50")"
STATUS="$(echo "$DEFAULT_JSON" | jq -r '.status // empty')"
DCOUNT="$(echo "$DEFAULT_JSON" | jq -r '.count // 0')"
echo "  status: $STATUS"
echo "  count: $DCOUNT"

if [[ "$STATUS" == "ok" ]]; then
  echo "✅ PASS: default endpoint вернул status = ok"
else
  echo "❌ FAIL: default status = $STATUS"
  fail=1
fi
echo

echo "S5. Проверка steam_url NOT NULL в default списке..."
DNULL_URLS="$(echo "$DEFAULT_JSON" | jq -r '[.games[]? | select((.steam_url // "") == "")] | length')"
if [[ "$DNULL_URLS" -eq 0 ]]; then
  echo "✅ PASS: все игры имеют steam_url NOT NULL в default списке"
else
  echo "❌ FAIL: найдено $DNULL_URLS игр без steam_url в default"
  fail=1
fi
echo

if [[ "$fail" -eq 0 ]]; then
  echo "=== ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ==="
  exit 0
else
  echo "=== ❌ ЕСТЬ ОШИБКИ ==="
  exit 1
fi
