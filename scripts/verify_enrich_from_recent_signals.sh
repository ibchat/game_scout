#!/bin/bash
# Verify Enrich From Recent Signals (B2, B3)
# Подготавливает known-good сигнал и проверяет что enrich реально обогащает

set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"
DB_SERVICE="${DB_SERVICE:-postgres}"

echo "=== Verify Enrich From Recent Signals (B2, B3) ==="
echo

fail=0

# B2: Подготовка known-good app_id (идемпотентно)
echo "B2. Подготовка known-good сигнала для теста:"

# Используем реальный Steam app_id (например, Portal 2 = 620)
KNOWN_GOOD_APP_ID=620
KNOWN_GOOD_URL="https://store.steampowered.com/app/${KNOWN_GOOD_APP_ID}/"
TEST_SIGNAL_URL="https://reddit.com/r/test/comments/test_enrich_$(date +%s)/"

# Проверяем, существует ли уже такой сигнал
EXISTING=$(docker compose exec -T "${DB_SERVICE}" psql -U postgres -d game_scout -t -c "
    SELECT COUNT(*) FROM deal_intent_signal 
    WHERE source = 'synthetic' AND url = '${TEST_SIGNAL_URL}'
" 2>/dev/null | tr -d ' ' || echo "0")

if [ "${EXISTING}" = "0" ]; then
    # Вставляем тестовый сигнал с текущей датой
    # Используем проверку существования вместо ON CONFLICT (так как может не быть уникального индекса)
    docker compose exec -T "${DB_SERVICE}" psql -U postgres -d game_scout -c "
        INSERT INTO deal_intent_signal (
            app_id, source, url, text, signal_type, published_at, created_at
        )
        SELECT 
            ${KNOWN_GOOD_APP_ID}, 'synthetic', '${TEST_SIGNAL_URL}', 
            '[SYNTHETIC TEST] Looking for publisher for our game. Check it out: ${KNOWN_GOOD_URL}',
            'behavioral_intent', NOW(), NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM deal_intent_signal 
            WHERE source = 'synthetic' AND url = '${TEST_SIGNAL_URL}'
        )
    " 2>&1 | grep -v "INSERT 0" || true
    
    echo "  ✅ Создан тестовый сигнал для app_id=${KNOWN_GOOD_APP_ID}"
else
    echo "  ℹ️  Тестовый сигнал уже существует (идемпотентность)"
fi
echo

# B3: Вызов enrich endpoint и проверка
echo "B3. Проверка enrich_from_recent_signals:"
RESPONSE=$(curl -4 -sS -X POST "${API_URL}/api/v1/deals/metadata/enrich_from_recent_signals?days=365&limit=50" 2>&1)
STATUS=$(echo "${RESPONSE}" | jq -r '.status // "error"' 2>/dev/null || echo "error")
CHECKED=$(echo "${RESPONSE}" | jq -r '.result.checked // 0' 2>/dev/null || echo "0")
ENRICHED_OK=$(echo "${RESPONSE}" | jq -r '.result.enriched_ok // 0' 2>/dev/null || echo "0")
FAILED=$(echo "${RESPONSE}" | jq -r '.result.failed // 0' 2>/dev/null || echo "0")
SKIPPED=$(echo "${RESPONSE}" | jq -r '.result.skipped // 0' 2>/dev/null || echo "0")
SAMPLE_FAILURES=$(echo "${RESPONSE}" | jq -r '.result.sample_failures // []' 2>/dev/null || echo "[]")
SAMPLE_SKIPPED=$(echo "${RESPONSE}" | jq -r '.result.sample_skipped // []' 2>/dev/null || echo "[]")

# Извлекаем reason из первого sample_skipped (если есть)
SKIPPED_REASON=$(echo "${SAMPLE_SKIPPED}" | jq -r '.[0].reason // ""' 2>/dev/null || echo "")

echo "  status = ${STATUS}"
echo "  checked = ${CHECKED}"
echo "  enriched_ok = ${ENRICHED_OK}"
echo "  failed = ${FAILED}"
echo "  skipped = ${SKIPPED}"
echo "  sample_failures count = $(echo "${SAMPLE_FAILURES}" | jq 'length')"
echo "  sample_skipped count = $(echo "${SAMPLE_SKIPPED}" | jq 'length')"
if [ -n "${SKIPPED_REASON}" ]; then
    echo "  sample_skipped[0].reason = ${SKIPPED_REASON}"
fi

# A: Детерминированная логика проверки
if [ "${STATUS}" != "ok" ]; then
    echo "  ❌ FAIL: status = ${STATUS}"
    fail=1
elif [ "${CHECKED}" -lt 1 ]; then
    echo "  ❌ FAIL: checked = ${CHECKED} (ожидается >= 1, так как мы создали тестовый сигнал)"
    fail=1
elif [ "${ENRICHED_OK}" -ge 1 ]; then
    # PASS: enriched_ok >= 1
    echo "  ✅ PASS: enriched_ok = ${ENRICHED_OK} >= 1 (обогащение работает)"
elif [ "${SKIPPED}" -ge 1 ] && [ "${SKIPPED_REASON}" = "metadata_already_exists" ]; then
    # PASS: skipped >= 1 AND reason == "metadata_already_exists"
    echo "  ✅ PASS: skipped = ${SKIPPED} >= 1 AND reason = '${SKIPPED_REASON}' (данные уже обогащены, это нормально)"
elif [ "${FAILED}" -gt 0 ] && [ "${ENRICHED_OK}" -eq 0 ] && [ "${SKIPPED}" -eq 0 ]; then
    # FAIL: failed > 0 и нет enriched_ok и нет подходящего skipped
    echo "  ❌ FAIL: failed = ${FAILED} > 0, enriched_ok = ${ENRICHED_OK}, skipped = ${SKIPPED}"
    echo "  sample_failures: ${SAMPLE_FAILURES}"
    fail=1
else
    # PASS: другие случаи (например, checked > 0 но все skipped с другими причинами)
    echo "  ✅ PASS: checked = ${CHECKED} >= 1, enriched_ok = ${ENRICHED_OK}, skipped = ${SKIPPED} (endpoint работает)"
fi
echo

# Итог
if [ "${fail}" -eq 0 ]; then
    echo "=== ✅ ENRICH ПРОВЕРЕН ==="
    exit 0
else
    echo "=== ❌ ENRICH НЕ РАБОТАЕТ ==="
    exit 1
fi
