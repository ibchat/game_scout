#!/bin/bash
# Verify Discord Calibration Test
# Проверяет, что test_inject режим работает и сохраняет сигналы в БД

set -e

echo "🔍 Discord Calibration Test"
echo "============================"

# 1. Вызываем endpoint с test_inject=1
echo ""
echo "1. Calling collect_discord with test_inject=1..."
RESPONSE=$(curl -4 -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?days=1&limit=50&test_inject=1" 2>&1)

if [ $? -ne 0 ]; then
    echo "❌ FAIL: curl request failed"
    echo "$RESPONSE"
    exit 1
fi

# Проверяем JSON валидность
if ! echo "$RESPONSE" | jq . > /dev/null 2>&1; then
    echo "❌ FAIL: Invalid JSON response"
    echo "$RESPONSE"
    exit 1
fi

# Извлекаем поля
STATUS=$(echo "$RESPONSE" | jq -r '.status // "MISSING"')
RESULT_STATUS=$(echo "$RESPONSE" | jq -r '.result.status // "MISSING"')
SIGNALS_SAVED=$(echo "$RESPONSE" | jq -r '.result.signals_saved // 0')

echo "   status: $STATUS"
echo "   result.status: $RESULT_STATUS"
echo "   signals_saved: $SIGNALS_SAVED"

# Проверяем статус
if [ "$STATUS" != "ok" ]; then
    echo "❌ FAIL: status != 'ok' (got: $STATUS)"
    exit 1
fi

if [ "$RESULT_STATUS" = "skipped" ]; then
    echo "⚠️  WARNING: result.status is 'skipped' (token may not be configured)"
    echo "   This is expected if DISCORD_BOT_TOKEN is a placeholder"
fi

# Проверяем signals_saved (может быть 0 из-за idempotency, если сигнал уже существует)
if [ "$SIGNALS_SAVED" -lt 1 ]; then
    echo "⚠️  WARNING: signals_saved < 1 (got: $SIGNALS_SAVED) - checking if signal exists in DB (idempotency)..."
    # Проверяем БД напрямую
    DB_TEST_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM deal_intent_signal WHERE source='discord' AND source_subtype='test_inject';" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')
    if [ "$DB_TEST_COUNT" -ge 1 ]; then
        echo "✅ PASS: Signal exists in DB (idempotency check passed)"
    else
        echo "❌ FAIL: signals_saved < 1 AND no test_inject signal in DB"
        echo "   Full response:"
        echo "$RESPONSE" | jq .
        exit 1
    fi
else
    echo "✅ PASS: signals_saved >= 1"
fi

# 2. Проверяем БД
echo ""
echo "2. Checking database for Discord signals..."
DB_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM deal_intent_signal WHERE source='discord';" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')

if [ -z "$DB_COUNT" ] || [ "$DB_COUNT" = "" ]; then
    echo "❌ FAIL: Could not query database"
    exit 1
fi

echo "   Discord signals in DB: $DB_COUNT"

if [ "$DB_COUNT" -lt 1 ]; then
    echo "❌ FAIL: No Discord signals found in database (expected >= 1)"
    exit 1
fi

echo "✅ PASS: Database contains Discord signals"

# 3. Проверяем наличие test_inject сигнала
echo ""
echo "3. Checking for test_inject signal..."
TEST_INJECT_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM deal_intent_signal WHERE source='discord' AND source_subtype='test_inject';" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')

echo "   test_inject signals: $TEST_INJECT_COUNT"

if [ "$TEST_INJECT_COUNT" -lt 1 ]; then
    echo "⚠️  WARNING: No test_inject signals found (may have been created in previous run)"
else
    echo "✅ PASS: test_inject signal found"
fi

# 4. Проверяем обязательные поля в ответе
echo ""
echo "4. Checking response contract..."
STATUS_FIELD=$(echo "$RESPONSE" | jq -r '.status // "MISSING"' 2>/dev/null)
RESULT_STATUS_FIELD=$(echo "$RESPONSE" | jq -r '.result.status // "MISSING"' 2>/dev/null)
MESSAGES_SCANNED_FIELD=$(echo "$RESPONSE" | jq -r '.result.messages_scanned // "MISSING"' 2>/dev/null)
SIGNALS_SAVED_FIELD=$(echo "$RESPONSE" | jq -r '.result.signals_saved // "MISSING"' 2>/dev/null)

MISSING_FIELDS=()

if [ "$STATUS_FIELD" = "MISSING" ] || [ "$STATUS_FIELD" = "null" ]; then
    MISSING_FIELDS+=("status")
fi

if [ "$RESULT_STATUS_FIELD" = "MISSING" ] || [ "$RESULT_STATUS_FIELD" = "null" ]; then
    MISSING_FIELDS+=("result.status")
fi

if [ "$MESSAGES_SCANNED_FIELD" = "MISSING" ] || [ "$MESSAGES_SCANNED_FIELD" = "null" ]; then
    MISSING_FIELDS+=("result.messages_scanned")
fi

if [ "$SIGNALS_SAVED_FIELD" = "MISSING" ] || [ "$SIGNALS_SAVED_FIELD" = "null" ]; then
    MISSING_FIELDS+=("result.signals_saved")
fi

if [ ${#MISSING_FIELDS[@]} -gt 0 ]; then
    echo "❌ FAIL: Missing required fields: ${MISSING_FIELDS[*]}"
    exit 1
fi

echo "✅ PASS: All required fields present"

# Итог
echo ""
echo "============================"
echo "✅ ALL CHECKS PASSED"
echo "============================"
exit 0
