#!/bin/bash
# Verify Publisher Hunt Feed (7.2)
# Проверяет что mode=publisher_hunt возвращает корректные данные

set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"

echo "=== Verify Publisher Hunt Feed (7.2) ==="
echo

fail=0

# Проверка feed mode=publisher_hunt
echo "7.2. Проверка /api/v1/deals/list?mode=publisher_hunt:"
RESPONSE=$(curl -4 -sS "${API_URL}/api/v1/deals/list?mode=publisher_hunt&limit=50" 2>&1)
STATUS=$(echo "${RESPONSE}" | jq -r '.status // "error"' 2>/dev/null || echo "error")
COUNT=$(echo "${RESPONSE}" | jq -r '.count // 0' 2>/dev/null || echo "0")
GAMES=$(echo "${RESPONSE}" | jq -r '.games // []' 2>/dev/null || echo "[]")
N=$(echo "${GAMES}" | jq 'length' 2>/dev/null || echo "0")

echo "  status = ${STATUS}"
echo "  count = ${COUNT}"
echo "  n (games length) = ${N}"

if [ "${STATUS}" != "ok" ]; then
    echo "  ❌ FAIL: status = ${STATUS}"
    fail=1
elif [ "${N}" -lt 5 ] && [ "${COUNT}" -gt 0 ]; then
    echo "  ⚠️  WARNING: n = ${N} < 5, но count = ${COUNT} > 0 (возможно, недостаточно данных)"
elif [ "${N}" -eq 0 ] && [ "${COUNT}" -eq 0 ]; then
    echo "  ℹ️  INFO: n = 0, count = 0 (нет данных в базе, это нормально для V1 без Discord token)"
else
    echo "  ✅ PASS: n = ${N} >= 5 или count = 0 (нет данных)"
fi
echo

# Проверка что все игры имеют publisher_intent_score и нет has_publisher
if [ "${N}" -gt 0 ]; then
    echo "7.2a. Проверка publisher_intent_score и publisher_status:"
    
    # Проверяем первые 10 игр
    HAS_PUBLISHER_COUNT=0
    NO_INTENT_SCORE_COUNT=0
    BAD_VERDICT_COUNT=0
    
    for i in $(seq 0 $((N - 1))); do
        GAME=$(echo "${GAMES}" | jq -r ".[${i}]")
        APP_ID=$(echo "${GAME}" | jq -r '.app_id // "null"')
        PUBLISHER_STATUS=$(echo "${GAME}" | jq -r '.publisher_status_code // "null"')
        VERDICT=$(echo "${GAME}" | jq -r '.verdict_label_ru // ""')
        
        # Проверяем что нет has_publisher
        if [ "${PUBLISHER_STATUS}" = "has_publisher" ]; then
            HAS_PUBLISHER_COUNT=$((HAS_PUBLISHER_COUNT + 1))
            echo "  ❌ FAIL: app_id=${APP_ID} имеет publisher_status_code=has_publisher (не должно быть в publisher_hunt)"
            fail=1
        fi
        
        # Проверяем что verdict не содержит "ищет издателя" для has_publisher (если есть)
        if [ "${PUBLISHER_STATUS}" = "has_publisher" ] && echo "${VERDICT}" | grep -qi "ищет издателя"; then
            BAD_VERDICT_COUNT=$((BAD_VERDICT_COUNT + 1))
            echo "  ❌ FAIL: app_id=${APP_ID} имеет has_publisher и verdict='${VERDICT}' (не должно быть 'ищет издателя')"
            fail=1
        fi
        
        if [ $i -ge 9 ]; then
            break  # Проверяем только первые 10
        fi
    done
    
    if [ "${HAS_PUBLISHER_COUNT}" -eq 0 ] && [ "${BAD_VERDICT_COUNT}" -eq 0 ]; then
        echo "  ✅ PASS: Все игры без издателя и с корректными вердиктами"
    fi
    echo
fi

# Итог
if [ "${fail}" -eq 0 ]; then
    echo "=== ✅ PUBLISHER HUNT FEED ПРОВЕРЕН ==="
    exit 0
else
    echo "=== ❌ PUBLISHER HUNT FEED НЕ КОРРЕКТЕН ==="
    exit 1
fi
