#!/usr/bin/env bash
set -euo pipefail

# Verify List Populated (Explore Mode)
# Проверяет, что /api/v1/deals/list возвращает много игр при нулевых порогах

API_URL="${API_URL:-http://127.0.0.1:8000}"

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

echo "=== Verify List Populated (Explore Mode) ==="
echo

fail=0

# S1: /list с нулевыми порогами → n == 50 и count >= 50
echo "S1. /list с нулевыми порогами (min_intent_score=0&min_quality_score=0):"
LIST_RESPONSE=$(CURL "${API_URL}/api/v1/deals/list?limit=50&min_intent_score=0&min_quality_score=0")
LIST_COUNT=$(echo "${LIST_RESPONSE}" | jq -r '.count // 0' 2>/dev/null || echo "0")
LIST_N=$(echo "${LIST_RESPONSE}" | jq -r '.games | length' 2>/dev/null || echo "0")
LIST_STATUS=$(echo "${LIST_RESPONSE}" | jq -r '.status // "error"' 2>/dev/null || echo "error")
EXPLORE_MODE=$(echo "${LIST_RESPONSE}" | jq -r '.debug.explore_mode // false' 2>/dev/null || echo "false")

echo "  status = ${LIST_STATUS}"
echo "  count = ${LIST_COUNT}"
echo "  n (games length) = ${LIST_N}"
echo "  explore_mode = ${EXPLORE_MODE}"

if [ "${LIST_STATUS}" != "ok" ]; then
    echo "  ❌ FAIL: /api/v1/deals/list status = ${LIST_STATUS}"
    fail=1
elif [ "${LIST_N}" -ne 50 ]; then
    echo "  ❌ FAIL: n = ${LIST_N} (ожидается 50)"
    fail=1
elif [ "${LIST_COUNT}" -lt 50 ]; then
    echo "  ❌ FAIL: count = ${LIST_COUNT} (ожидается >= 50)"
    fail=1
elif [ "${EXPLORE_MODE}" != "true" ]; then
    echo "  ❌ FAIL: explore_mode = ${EXPLORE_MODE} (ожидается true)"
    fail=1
else
    echo "  ✅ PASS: n = ${LIST_N}, count = ${LIST_COUNT}, explore_mode = ${EXPLORE_MODE}"
fi
echo

# S2: has_thesis == false
echo "S2. Проверка что thesis НЕ попал в list:"
FIRST_GAME=$(echo "${LIST_RESPONSE}" | jq -r '.games[0] // {}' 2>/dev/null || echo "{}")
HAS_THESIS=$(echo "${FIRST_GAME}" | jq -r 'has("thesis")' 2>/dev/null || echo "false")
HAS_THESIS_EXPLAIN=$(echo "${FIRST_GAME}" | jq -r 'has("thesis_explain")' 2>/dev/null || echo "false")

echo "  has_thesis = ${HAS_THESIS}"
echo "  has_thesis_explain = ${HAS_THESIS_EXPLAIN}"

if [ "${HAS_THESIS}" = "true" ]; then
    echo "  ❌ FAIL: games[0] содержит thesis (не должно быть в list)"
    fail=1
elif [ "${HAS_THESIS_EXPLAIN}" = "true" ]; then
    echo "  ❌ FAIL: games[0] содержит thesis_explain (не должно быть в list)"
    fail=1
else
    echo "  ✅ PASS: thesis и thesis_explain отсутствуют в list"
fi
echo

# Итог
if [ "${fail}" -eq 0 ]; then
    echo "=== ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ==="
    exit 0
else
    echo "=== ❌ НЕКОТОРЫЕ ПРОВЕРКИ ПРОВАЛЕНЫ ==="
    exit 1
fi
