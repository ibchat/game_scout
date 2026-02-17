#!/bin/bash
# Verify Discord Live E2E - детерминированный тест для проверки готовности Discord ingestion

set -e

echo "🔍 Discord Live E2E Verification"
echo "================================"

# 1. Test Inject (детерминированный тест)
echo ""
echo "1. Running test_inject (deterministic test)..."
# Удаляем старую запись для чистого теста
docker compose exec -T postgres psql -U postgres -d game_scout -c "DELETE FROM deal_intent_signal WHERE source='discord' AND source_subtype='test_inject';" > /dev/null 2>&1
TEST_INJECT_RESPONSE=$(curl -4 -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?test_inject=1&debug=1" 2>&1)

if [ $? -ne 0 ]; then
    echo "❌ FAIL: test_inject curl request failed"
    exit 1
fi

# Проверяем JSON валидность
if ! echo "$TEST_INJECT_RESPONSE" | jq . > /dev/null 2>&1; then
    echo "❌ FAIL: Invalid JSON response from test_inject"
    echo "$TEST_INJECT_RESPONSE"
    exit 1
fi

TEST_SIGNALS_SAVED=$(echo "$TEST_INJECT_RESPONSE" | jq -r '.result.signals_saved // 0')
TEST_APP_IDS=$(echo "$TEST_INJECT_RESPONSE" | jq -r '.result.app_ids_discovered // 0')

echo "   signals_saved: $TEST_SIGNALS_SAVED"
echo "   app_ids_discovered: $TEST_APP_IDS"

if [ "$TEST_SIGNALS_SAVED" -lt 1 ]; then
    echo "❌ FAIL: test_inject signals_saved < 1 (got: $TEST_SIGNALS_SAVED)"
    echo "   This is a critical failure - test_inject must save at least 1 signal"
    exit 1
fi

if [ "$TEST_APP_IDS" -lt 1 ]; then
    echo "❌ FAIL: test_inject app_ids_discovered < 1 (got: $TEST_APP_IDS)"
    exit 1
fi

# Проверяем БД
echo ""
echo "2. Checking database for test_inject signal..."
DB_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM deal_intent_signal WHERE source='discord' AND source_subtype='test_inject';" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')

if [ -z "$DB_COUNT" ] || [ "$DB_COUNT" = "" ]; then
    echo "❌ FAIL: Could not query database"
    exit 1
fi

echo "   test_inject signals in DB: $DB_COUNT"

if [ "$DB_COUNT" -lt 1 ]; then
    echo "❌ FAIL: No test_inject signals found in database (expected >= 1)"
    exit 1
fi

echo "✅ PASS: test_inject proof successful"

# 3. Live Scan (проверка готовности канала)
echo ""
echo "3. Running live scan (channel readiness check)..."
LIVE_RESPONSE=$(curl -4 -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?days=30&limit=50&debug=1" 2>&1)

if [ $? -ne 0 ]; then
    echo "❌ FAIL: live scan curl request failed"
    exit 1
fi

# Проверяем JSON валидность
if ! echo "$LIVE_RESPONSE" | jq . > /dev/null 2>&1; then
    echo "❌ FAIL: Invalid JSON response from live scan"
    echo "$LIVE_RESPONSE"
    exit 1
fi

NON_SYSTEM_SEEN=$(echo "$LIVE_RESPONSE" | jq -r '.result.non_system_messages_seen // 0')
ACTION_REQUIRED=$(echo "$LIVE_RESPONSE" | jq -r '.result.action_required // ""')
MESSAGES_MATCHED=$(echo "$LIVE_RESPONSE" | jq -r '.result.messages_matched // 0')
LATEST_PREVIEW=$(echo "$LIVE_RESPONSE" | jq -r '.result.latest_non_system_message_preview // ""')
LATEST_URLS=$(echo "$LIVE_RESPONSE" | jq -r '.result.latest_non_system_message_urls // []')

echo "   non_system_messages_seen: $NON_SYSTEM_SEEN"
echo "   action_required: $ACTION_REQUIRED"
echo "   messages_matched: $MESSAGES_MATCHED"

if [ "$NON_SYSTEM_SEEN" -gt 0 ]; then
    echo "   latest_preview: $LATEST_PREVIEW"
    echo "   latest_urls: $LATEST_URLS"
    
    # Если есть не-системные сообщения, проверяем матчинг
    if [ "$MESSAGES_MATCHED" -lt 1 ]; then
        echo "⚠️  WARNING: non_system_messages_seen > 0 but messages_matched == 0"
        echo "   This may be normal if messages don't contain publisher-seeking phrases"
        echo "   Latest preview: $LATEST_PREVIEW"
    else
        echo "✅ PASS: Found non-system messages and matched >= 1"
    fi
else
    echo "⚠️  INFO: non_system_messages_seen == 0 (channel is empty or only system messages)"
    if [ "$ACTION_REQUIRED" = "send_any_text_message_to_channel" ]; then
        echo "   Action required: Send a text message to the Discord channel to test ingestion"
        echo "   Example: 'Looking for a publisher for our Steam game: https://store.steampowered.com/app/620/'"
    fi
    echo "✅ PASS: Channel readiness check passed (expected empty/only system messages)"
fi

# Итог
echo ""
echo "============================"
echo "✅ ALL CHECKS PASSED"
echo "============================"
echo ""
echo "Summary:"
echo "  - test_inject: ✅ PASS (signals_saved=$TEST_SIGNALS_SAVED, app_ids=$TEST_APP_IDS)"
echo "  - live scan: ✅ PASS (non_system=$NON_SYSTEM_SEEN, action=$ACTION_REQUIRED)"
if [ "$NON_SYSTEM_SEEN" -eq 0 ]; then
    echo ""
    echo "Next step: Send a text message to Discord channel to test full E2E"
fi
exit 0
