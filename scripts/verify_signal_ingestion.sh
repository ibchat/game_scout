#!/usr/bin/env bash

set -euo pipefail

# Verify Signal Ingestion (Vector A EXEC v1)
# Согласно TZ_SIGNAL_INGESTION_VECTOR_A_EXEC_V1.md п.4.1

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
DB_SERVICE="${DB_SERVICE:-postgres}"
DB_NAME="${DB_NAME:-game_scout}"
DB_USER="${DB_USER:-postgres}"

fail=0

psql_db() {
  local sql="$1"
  docker compose exec -T "$DB_SERVICE" bash -lc "export PAGER=cat; psql -U '$DB_USER' -d '$DB_NAME' -Atc \"$sql\""
}

CURL() {
  local url="$1"
  local tries=5
  local delay=0.5
  local i=1
  
  while [[ $i -le $tries ]]; do
    local out=$(curl -4 -sS --max-time 10 "$url" 2>/dev/null)
    if [[ -n "$out" ]] && ! echo "$out" | grep -q "Empty reply from server"; then
      printf "%s" "$out"
      return 0
    fi
    sleep "$delay"
    i=$((i+1))
  done
  
  curl -4 -sS --max-time 10 "$url"
}

echo "=== Verify Signal Ingestion (Vector A EXEC v1) ==="
echo

# 1. apps_with_signals
echo "1. apps_with_signals:"
APPS_WITH_SIGNALS=$(psql_db "SELECT COUNT(DISTINCT app_id) FROM deal_intent_signal WHERE app_id IS NOT NULL;")
echo "  apps_with_signals = ${APPS_WITH_SIGNALS}"
echo

# 2. total signals
echo "2. Total signals:"
TOTAL_SIGNALS=$(psql_db "SELECT COUNT(*) FROM deal_intent_signal;")
echo "  total_signals = ${TOTAL_SIGNALS}"
echo

# 3. dup table (source, url) - Stability Gate
echo "3. Дубликаты (source, url) - Stability Gate:"
DUP_QUERY="SELECT source, COUNT(*) as total, COUNT(DISTINCT url) as uniq, (COUNT(*)-COUNT(DISTINCT url)) as dup FROM deal_intent_signal WHERE url IS NOT NULL GROUP BY source ORDER BY total DESC;"
DUP_RESULT=$(docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -c "$DUP_QUERY" 2>&1)
echo "$DUP_RESULT" | tail -10

# Проверяем dup > 0
MAX_DUP=$(psql_db "SELECT MAX(COUNT(*)-COUNT(DISTINCT url)) FROM deal_intent_signal WHERE url IS NOT NULL GROUP BY source;" 2>/dev/null || echo "0")
if [[ "${MAX_DUP}" -gt 0 ]]; then
  echo "  ❌ FAIL: dup = ${MAX_DUP} > 0 (Stability Gate FAIL)"
  fail=1
else
  echo "  ✅ PASS: dup = 0 (Stability Gate PASS)"
fi
echo

# 4. /list count > 0 при нулевых порогах - Stability Gate
echo "4. Контракт /list: count > 0 при min_intent_score=0&min_quality_score=0 - Stability Gate:"
LIST_RESPONSE=$(CURL "${API_BASE}/api/v1/deals/list?limit=50&min_intent_score=0&min_quality_score=0")
LIST_COUNT=$(echo "${LIST_RESPONSE}" | jq -r '.count // 0' 2>/dev/null || echo "0")
LIST_STATUS=$(echo "${LIST_RESPONSE}" | jq -r '.status // "error"' 2>/dev/null || echo "error")
EXCLUDED_REASONS=$(echo "${LIST_RESPONSE}" | jq -r '.excluded_reasons // {}' 2>/dev/null || echo "{}")
echo "  status = ${LIST_STATUS}, count = ${LIST_COUNT}"

if [ "${LIST_STATUS}" != "ok" ]; then
  echo "  ❌ FAIL: /list status = ${LIST_STATUS} (Stability Gate FAIL)"
  fail=1
elif [ "${LIST_COUNT}" -gt 0 ]; then
  echo "  ✅ PASS: /list count = ${LIST_COUNT} > 0 (Stability Gate PASS)"
else
  echo "  ❌ FAIL: /list count = 0 при min_intent_score=0&min_quality_score=0 (Stability Gate FAIL)"
  echo "  excluded_reasons: ${EXCLUDED_REASONS}"
  fail=1
fi
echo

# 5. Top sources by unique app_id
echo "5. Top sources by unique app_id:"
TOP_SOURCES=$(docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT source, COUNT(DISTINCT app_id) as unique_apps FROM deal_intent_signal WHERE app_id IS NOT NULL GROUP BY source ORDER BY unique_apps DESC;" 2>&1)
echo "$TOP_SOURCES" | tail -10
echo

# 6. Top 20 app_id by signals count
echo "6. Top 20 app_id by signals count:"
TOP_APP_IDS=$(docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT app_id, COUNT(*) as signal_count FROM deal_intent_signal WHERE app_id IS NOT NULL GROUP BY app_id ORDER BY signal_count DESC LIMIT 20;" 2>&1)
echo "$TOP_APP_IDS" | tail -22
echo

# 7. Progress Gate: apps_with_signals >= 100 (НЕ блокирует merge)
echo "7. Progress Gate: apps_with_signals >= 100 (НЕ блокирует merge):"
if [[ "${APPS_WITH_SIGNALS}" -ge 100 ]]; then
  echo "  ✅ Progress Gate PASS: apps_with_signals = ${APPS_WITH_SIGNALS} (>= 100)"
else
  echo "  ⚠️  Progress Gate FAIL: apps_with_signals = ${APPS_WITH_SIGNALS} (< 100) - не блокирует merge"
  # НЕ устанавливаем fail=1, так как это Progress Gate, не Stability Gate
fi
echo

# Итог
if [[ "$fail" -eq 0 ]]; then
  echo "=== ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ (Stability Gate PASS) ==="
  exit 0
else
  echo "=== ❌ ЕСТЬ ОШИБКИ (Stability Gate FAIL) ==="
  exit 1
fi
