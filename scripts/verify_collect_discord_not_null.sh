#!/bin/bash
# Verify that collect_discord endpoint always returns non-null result

set -e

echo "🔍 Verify collect_discord Not Null"
echo "=================================="

# 1. Check services
echo ""
echo "1. Checking services..."
API_STATUS=$(docker compose ps api --format "{{.Status}}" 2>/dev/null | head -1 || echo "not_running")
WORKER_STATUS=$(docker compose ps worker --format "{{.Status}}" 2>/dev/null | head -1 || echo "not_running")

if [ -z "$API_STATUS" ] || echo "$API_STATUS" | grep -qE "Exited|Restarting"; then
    echo "❌ FAIL: API service is not running (status: $API_STATUS)"
    exit 1
fi

echo "   API: $API_STATUS"
echo "   Worker: $WORKER_STATUS"

# 2. Test invalid days (days=30)
echo ""
echo "2. Testing invalid days (days=30)..."
INVALID_RESPONSE=$(curl -4 -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?days=30&limit=50&debug=1" 2>&1)

if [ $? -ne 0 ]; then
    echo "❌ FAIL: Invalid days curl request failed"
    exit 1
fi

# Check JSON validity
if ! echo "$INVALID_RESPONSE" | jq . > /dev/null 2>&1; then
    echo "❌ FAIL: Invalid JSON response from invalid days request"
    echo "$INVALID_RESPONSE"
    exit 1
fi

INVALID_STATUS=$(echo "$INVALID_RESPONSE" | jq -r '.status // "NULL"')
INVALID_RESULT=$(echo "$INVALID_RESPONSE" | jq -r '.result // "NULL"')

echo "   status: $INVALID_STATUS"
echo "   result: $INVALID_RESULT"

if [ "$INVALID_STATUS" != "error" ]; then
    echo "❌ FAIL: Invalid days should return status='error' (got: $INVALID_STATUS)"
    exit 1
fi

if [ "$INVALID_RESULT" = "NULL" ] || [ "$INVALID_RESULT" = "null" ]; then
    echo "❌ FAIL: Invalid days result is null (should be structured error)"
    exit 1
fi

# Check that result is a dict with required fields
INVALID_MESSAGES_SCANNED=$(echo "$INVALID_RESPONSE" | jq -r '.result.messages_scanned // "NULL"')
if [ "$INVALID_MESSAGES_SCANNED" = "NULL" ]; then
    echo "❌ FAIL: Invalid days result.messages_scanned is null"
    exit 1
fi

echo "✅ PASS: Invalid days returns structured error with non-null result"

# 3. Test endpoint with normal parameters
echo ""
echo "3. Testing endpoint with days=7..."
RESPONSE=$(curl -4 -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?days=7&debug=1" 2>&1)

if [ $? -ne 0 ]; then
    echo "❌ FAIL: curl request failed"
    exit 1
fi

# Check JSON validity
if ! echo "$RESPONSE" | jq . > /dev/null 2>&1; then
    echo "❌ FAIL: Invalid JSON response"
    echo "$RESPONSE"
    exit 1
fi

# Check result is not null
RESULT=$(echo "$RESPONSE" | jq -r '.result // "NULL"')

if [ "$RESULT" = "NULL" ] || [ "$RESULT" = "null" ]; then
    echo "❌ FAIL: result is null"
    echo "Response:"
    echo "$RESPONSE" | jq .
    exit 1
fi

echo "✅ PASS: result is not null"

# 4. Check required fields
echo ""
echo "4. Checking required fields..."
STATUS=$(echo "$RESPONSE" | jq -r '.result.status // "NULL"')
MESSAGES_SCANNED=$(echo "$RESPONSE" | jq -r '.result.messages_scanned // "NULL"')
NON_SYSTEM_SEEN=$(echo "$RESPONSE" | jq -r '.result.non_system_messages_seen // "NULL"')
ACTION_REQUIRED=$(echo "$RESPONSE" | jq -r '.result.action_required // "NULL"')

echo "   status: $STATUS"
echo "   messages_scanned: $MESSAGES_SCANNED"
echo "   non_system_messages_seen: $NON_SYSTEM_SEEN"
echo "   action_required: $ACTION_REQUIRED"

if [ "$STATUS" = "NULL" ] || [ "$MESSAGES_SCANNED" = "NULL" ] || [ "$NON_SYSTEM_SEEN" = "NULL" ] || [ "$ACTION_REQUIRED" = "NULL" ]; then
    echo "❌ FAIL: Some required fields are null"
    exit 1
fi

# Check that numbers are actually numbers
if ! echo "$MESSAGES_SCANNED" | grep -qE '^[0-9]+$'; then
    echo "❌ FAIL: messages_scanned is not a number (got: $MESSAGES_SCANNED)"
    exit 1
fi

if ! echo "$NON_SYSTEM_SEEN" | grep -qE '^[0-9]+$'; then
    echo "❌ FAIL: non_system_messages_seen is not a number (got: $NON_SYSTEM_SEEN)"
    exit 1
fi

echo "✅ PASS: All required fields present and valid"

# 5. Test with test_inject
echo ""
echo "5. Testing with test_inject=1..."
# Delete old test_inject record
docker compose exec -T postgres psql -U postgres -d game_scout -c "DELETE FROM deal_intent_signal WHERE source='discord' AND source_subtype='test_inject';" > /dev/null 2>&1

TEST_RESPONSE=$(curl -4 -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?test_inject=1&debug=1" 2>&1)

if [ $? -ne 0 ]; then
    echo "❌ FAIL: test_inject curl request failed"
    exit 1
fi

TEST_RESULT=$(echo "$TEST_RESPONSE" | jq -r '.result // "NULL"')
if [ "$TEST_RESULT" = "NULL" ] || [ "$TEST_RESULT" = "null" ]; then
    echo "❌ FAIL: test_inject result is null"
    exit 1
fi

TEST_SIGNALS_SAVED=$(echo "$TEST_RESPONSE" | jq -r '.result.signals_saved // 0')
TEST_APP_IDS=$(echo "$TEST_RESPONSE" | jq -r '.result.app_ids_discovered // 0')

echo "   signals_saved: $TEST_SIGNALS_SAVED"
echo "   app_ids_discovered: $TEST_APP_IDS"

if [ "$TEST_SIGNALS_SAVED" -lt 1 ]; then
    echo "❌ FAIL: test_inject signals_saved < 1"
    exit 1
fi

if [ "$TEST_APP_IDS" -lt 1 ]; then
    echo "❌ FAIL: test_inject app_ids_discovered < 1"
    exit 1
fi

echo "✅ PASS: test_inject works correctly"

# 6. Check database
echo ""
echo "6. Checking database..."
DB_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM deal_intent_signal WHERE source='discord' AND source_subtype='test_inject';" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')

if [ "$DB_COUNT" -lt 1 ]; then
    echo "❌ FAIL: No test_inject signals in database"
    exit 1
fi

echo "   test_inject signals in DB: $DB_COUNT"
echo "✅ PASS: Database check passed"

# Summary
echo ""
echo "============================"
echo "✅ ALL CHECKS PASSED"
echo "============================"
echo ""
echo "Summary:"
echo "  - result is not null: ✅"
echo "  - required fields present: ✅"
echo "  - test_inject works: ✅ (signals_saved=$TEST_SIGNALS_SAVED, app_ids=$TEST_APP_IDS)"
echo "  - database check: ✅ ($DB_COUNT records)"
exit 0
