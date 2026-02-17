#!/bin/bash
# Verify Reddit Daily Scan Contract (A3)
# Проверяет что collect_reddit возвращает НЕ null метрики

set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"

echo "=== Verify Reddit Daily Contract (A3) ==="
echo

fail=0

# Проверка контракта ответа collect_reddit
echo "A3. Проверка контракта /api/v1/deals/signals/collect_reddit:"
RESPONSE=$(curl -4 -sS -X POST "${API_URL}/api/v1/deals/signals/collect_reddit?days=1&limit_per_sub=200&include_comments=true" 2>&1)
STATUS=$(echo "${RESPONSE}" | jq -r '.status // "error"' 2>/dev/null || echo "error")
RESULT=$(echo "${RESPONSE}" | jq -r '.result // {}' 2>/dev/null || echo "{}")

echo "  status = ${STATUS}"

# Проверяем обязательные поля (не null)
SIGNALS_FETCHED=$(echo "${RESULT}" | jq -r '.signals_fetched // "null"' 2>/dev/null || echo "null")
SIGNALS_SAVED=$(echo "${RESULT}" | jq -r '.signals_saved // "null"' 2>/dev/null || echo "null")
APPS_DISCOVERED=$(echo "${RESULT}" | jq -r '.apps_discovered // "null"' 2>/dev/null || echo "null")
POSTS_FETCHED=$(echo "${RESULT}" | jq -r '.posts_fetched // "null"' 2>/dev/null || echo "null")
COMMENTS_SCRAPED=$(echo "${RESULT}" | jq -r '.comments_scraped // "null"' 2>/dev/null || echo "null")

echo "  signals_fetched = ${SIGNALS_FETCHED}"
echo "  signals_saved = ${SIGNALS_SAVED}"
echo "  apps_discovered = ${APPS_DISCOVERED}"
echo "  posts_fetched = ${POSTS_FETCHED}"
echo "  comments_scraped = ${COMMENTS_SCRAPED}"

if [ "${STATUS}" != "ok" ]; then
    echo "  ❌ FAIL: status = ${STATUS}"
    fail=1
elif [ "${SIGNALS_FETCHED}" = "null" ]; then
    echo "  ❌ FAIL: signals_fetched is null (должно быть int, даже если 0)"
    fail=1
elif [ "${APPS_DISCOVERED}" = "null" ]; then
    echo "  ❌ FAIL: apps_discovered is null (должно быть int, даже если 0)"
    fail=1
elif [ "${SIGNALS_SAVED}" = "null" ]; then
    echo "  ❌ FAIL: signals_saved is null (должно быть int, даже если 0)"
    fail=1
else
    echo "  ✅ PASS: Все обязательные поля присутствуют и не null"
fi
echo

# Итог
if [ "${fail}" -eq 0 ]; then
    echo "=== ✅ КОНТРАКТ ПРОВЕРЕН ==="
    exit 0
else
    echo "=== ❌ КОНТРАКТ НАРУШЕН ==="
    exit 1
fi
