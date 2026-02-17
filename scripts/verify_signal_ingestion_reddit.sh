#!/bin/bash
# Verify Signal Ingestion Reddit (Vector A EXEC v1)
# Согласно TZ_SIGNAL_INGESTION_VECTOR_A_EXEC_V1.md п.9.1

set -euo pipefail

DB_SERVICE="${DB_SERVICE:-postgres}"
API_URL="${API_URL:-http://127.0.0.1:8000}"

echo "=== Verify Signal Ingestion Reddit (Vector A EXEC v1) ==="
echo

# Helper для psql
psql_db() {
    docker compose exec -T "${DB_SERVICE}" bash -lc "export PAGER=cat; psql -U postgres -d game_scout -Atc \"$1\"" 2>&1 | tail -1
}

# Helper для curl с retry
CURL="curl -4 -sS --max-time 10 --retry 2 --retry-delay 1"

fail=0

# 1. apps_with_signals >= 100 (Progress Gate - НЕ блокирует merge)
# Согласно TZ_SYSTEM_GOVERNANCE_MASTER.md Mode B: Progress Gate
echo "1. apps_with_signals (Progress Gate - отчет, не блокирует merge):"
APPS_WITH_SIGNALS=$(psql_db "SELECT COUNT(DISTINCT app_id) FROM deal_intent_signal WHERE app_id IS NOT NULL;")
echo "  apps_with_signals = ${APPS_WITH_SIGNALS} / 100"
if [ "${APPS_WITH_SIGNALS}" -ge 100 ]; then
    echo "  ✅ Progress Gate PASS: apps_with_signals >= 100"
else
    echo "  ⚠️  Progress Gate FAIL: apps_with_signals = ${APPS_WITH_SIGNALS} (< 100) - не блокирует merge"
    # НЕ устанавливаем fail=1, так как это Progress Gate, не Stability Gate
fi
echo

# 2. Все сигналы имеют валидный app_id
echo "2. Сигналы без app_id:"
SIGNALS_WITHOUT_APP_ID=$(psql_db "SELECT COUNT(*) FROM deal_intent_signal WHERE source='reddit' AND app_id IS NULL;")
echo "  signals_without_app_id = ${SIGNALS_WITHOUT_APP_ID}"
if [ "${SIGNALS_WITHOUT_APP_ID}" -eq 0 ]; then
    echo "  ✅ PASS: Все Reddit сигналы имеют app_id"
else
    echo "  ❌ FAIL: Найдено ${SIGNALS_WITHOUT_APP_ID} Reddit сигналов без app_id"
    fail=1
fi
echo

# 3. Нет дублей (source, url)
echo "3. Дубликаты (source, url):"
DUPLICATES=$(psql_db "SELECT COUNT(*) FROM (SELECT source, url, COUNT(*) as cnt FROM deal_intent_signal WHERE source='reddit' AND url IS NOT NULL GROUP BY source, url HAVING COUNT(*) > 1) sub;")
echo "  duplicates = ${DUPLICATES}"
if [ "${DUPLICATES}" -eq 0 ]; then
    echo "  ✅ PASS: Нет дубликатов (source, url)"
else
    echo "  ❌ FAIL: Найдено ${DUPLICATES} дубликатов"
    fail=1
fi
echo

# 4. Source = reddit
echo "4. Распределение по источникам:"
REDDIT_COUNT=$(psql_db "SELECT COUNT(*) FROM deal_intent_signal WHERE source='reddit';")
echo "  reddit: ${REDDIT_COUNT} сигналов"
if [ "${REDDIT_COUNT}" -gt 0 ]; then
    echo "  ✅ PASS: Reddit сигналы присутствуют"
else
    echo "  ❌ FAIL: Нет Reddit сигналов"
    fail=1
fi
echo

# 5. Контракт /list: count > 0 при min_intent_score=0&min_quality_score=0 (Stability Gate)
# Согласно TZ_SYSTEM_GOVERNANCE_MASTER.md п.2.3: минимальный смысловой контракт
# Stability Gate секция: контрактные проверки
echo "5. Контракт /list: count > 0 при min_intent_score=0&min_quality_score=0 (Stability Gate)..."
LIST_RESPONSE=$(${CURL} "${API_URL}/api/v1/deals/list?limit=50&min_intent_score=0&min_quality_score=0" 2>&1)
LIST_COUNT=$(echo "${LIST_RESPONSE}" | jq -r '.count // 0' 2>/dev/null || echo "0")
LIST_STATUS=$(echo "${LIST_RESPONSE}" | jq -r '.status // "error"' 2>/dev/null || echo "error")
EXCLUDED_REASONS=$(echo "${LIST_RESPONSE}" | jq -r '.excluded_reasons // {}' 2>/dev/null || echo "{}")
EXCLUDED=$(echo "${LIST_RESPONSE}" | jq -r '.excluded // {}' 2>/dev/null || echo "{}")
echo "  status = ${LIST_STATUS}, count = ${LIST_COUNT}"

# Stability Gate: проверяем минимальный смысловой контракт
if [ "${LIST_STATUS}" != "ok" ]; then
    echo "  ❌ FAIL: /api/v1/deals/list status = ${LIST_STATUS} (регрессия API)"
    fail=1
elif [ "${LIST_COUNT}" -gt 0 ]; then
    echo "  ✅ PASS: /api/v1/deals/list count = ${LIST_COUNT} > 0 (минимальный смысловой контракт соблюден)"
else
    echo "  ❌ FAIL: /api/v1/deals/list count = 0 при min_intent_score=0&min_quality_score=0 (регрессия gates/filters)"
    echo "  excluded_reasons: ${EXCLUDED_REASONS}"
    echo "  excluded: ${EXCLUDED}"
    echo "  Диагностика: все игры исключены gates/filters, требуется анализ причин"
    fail=1
fi
echo

# 6. Reddit Comments Ingestion regression check (NEW)
echo "6. Reddit Comments Ingestion (include_comments=true):"
COMMENTS_BEFORE=$(psql_db "SELECT COUNT(*) FROM deal_intent_signal WHERE source='reddit' AND url LIKE '%/comments/%';")
echo "  comment_like_before: ${COMMENTS_BEFORE}"

# Run ingestion with include_comments=true
echo "  Running API call with include_comments=true..."
API_RESPONSE=$(${CURL} -X POST "${API_URL}/api/v1/deals/signals/collect_reddit?days=7&limit_per_sub=20&include_comments=true" 2>&1)
COMMENTS_SCRAPED=$(echo "${API_RESPONSE}" | jq -r '.result.comments_scraped // .result.comments_fetched // 0' 2>/dev/null | head -1 || echo "0")
COMMENTS_KEPT=$(echo "${API_RESPONSE}" | jq -r '.result.comments_kept // 0' 2>/dev/null | head -1 || echo "0")
echo "  comments_scraped: ${COMMENTS_SCRAPED}"
echo "  comments_kept: ${COMMENTS_KEPT}"

COMMENTS_AFTER=$(psql_db "SELECT COUNT(*) FROM deal_intent_signal WHERE source='reddit' AND url LIKE '%/comments/%';")
COMMENTS_DELTA=$((COMMENTS_AFTER - COMMENTS_BEFORE))
echo "  comment_like_after: ${COMMENTS_AFTER} (delta: ${COMMENTS_DELTA})"

# Check: comments_scraped >= 1 OR comments_kept >= 1 OR delta > 0
if [ "${COMMENTS_SCRAPED}" -ge 1 ] || [ "${COMMENTS_KEPT}" -ge 1 ] || [ "${COMMENTS_DELTA}" -gt 0 ]; then
    echo "  ✅ PASS: Comments ingestion working (scraped=${COMMENTS_SCRAPED}, kept=${COMMENTS_KEPT}, delta=${COMMENTS_DELTA})"
else
    echo "  ❌ FAIL: comments_scraped=0 AND comments_kept=0 AND delta=0"
    fail=1
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
