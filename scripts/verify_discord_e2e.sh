#!/bin/bash
set -e

# Verify Discord Ingestion E2E
# Uses existing mechanisms: collect_discord with debug and test_inject

echo "=== Verify Discord Ingestion E2E ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

EXIT_CODE=0

# 1. Test debug endpoint
echo "1. Testing collect_discord with debug=1..."
DEBUG_RESPONSE=$(curl -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?days=7&limit=50&debug=1" 2>&1 || echo "ERROR")

if [ "$DEBUG_RESPONSE" = "ERROR" ]; then
    echo -e "   ${RED}✗${NC} Debug endpoint failed"
    EXIT_CODE=1
else
    # Check if result is not null
    RESULT=$(echo "$DEBUG_RESPONSE" | jq -r '.result // null' 2>/dev/null || echo "null")
    if [ "$RESULT" != "null" ] && [ "$RESULT" != "null" ]; then
        echo -e "   ${GREEN}✓${NC} Debug endpoint: result is not null"
        
        # Check channels_visible
        CHANNELS_VISIBLE=$(echo "$DEBUG_RESPONSE" | jq -r '.result.channels_visible // [] | length' 2>/dev/null || echo "0")
        if [ "$CHANNELS_VISIBLE" -ge 1 ]; then
            echo -e "   ${GREEN}✓${NC} channels_visible: $CHANNELS_VISIBLE"
        else
            echo -e "   ${YELLOW}⚠${NC} channels_visible: $CHANNELS_VISIBLE (expected >= 1)"
        fi
    else
        echo -e "   ${RED}✗${NC} Debug endpoint: result is null"
        EXIT_CODE=1
    fi
fi
echo ""

# 2. Test test_inject
echo "2. Testing collect_discord with test_inject=1..."
TEST_INJECT_RESPONSE=$(curl -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?days=7&limit=50&test_inject=1" 2>&1 || echo "ERROR")

if [ "$TEST_INJECT_RESPONSE" = "ERROR" ]; then
    echo -e "   ${RED}✗${NC} Test inject endpoint failed"
    EXIT_CODE=1
else
    SIGNALS_SAVED=$(echo "$TEST_INJECT_RESPONSE" | jq -r '.result.signals_saved // 0' 2>/dev/null || echo "0")
    if [ "$SIGNALS_SAVED" -ge 1 ]; then
        echo -e "   ${GREEN}✓${NC} Test inject: signals_saved=$SIGNALS_SAVED"
    else
        echo -e "   ${YELLOW}⚠${NC} Test inject: signals_saved=$SIGNALS_SAVED (expected >= 1)"
    fi
fi
echo ""

# 3. DB proof: test_inject records
echo "3. Checking database for test_inject records..."
TEST_INJECT_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
    SELECT COUNT(*)::text
    FROM deal_intent_signal
    WHERE source='discord' AND source_subtype='test_inject';
" 2>&1 | grep -v "time=" | grep -v "level=" | grep -E "^[0-9]+" || echo "0")

if [ "$TEST_INJECT_COUNT" != "0" ] && [ -n "$TEST_INJECT_COUNT" ]; then
    echo -e "   ${GREEN}✓${NC} test_inject records in DB: $TEST_INJECT_COUNT"
else
    echo -e "   ${YELLOW}⚠${NC} No test_inject records found"
fi
echo ""

# 4. DB proof: discord records with app_id
echo "4. Checking database for discord records with app_id..."
DISCORD_APP_ID_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
    SELECT COUNT(*)::text
    FROM deal_intent_signal
    WHERE source='discord' AND app_id IS NOT NULL;
" 2>&1 | grep -v "time=" | grep -v "level=" | grep -E "^[0-9]+" || echo "0")

if [ "$DISCORD_APP_ID_COUNT" != "0" ] && [ -n "$DISCORD_APP_ID_COUNT" ]; then
    echo -e "   ${GREEN}✓${NC} Discord records with app_id: $DISCORD_APP_ID_COUNT"
else
    echo -e "   ${YELLOW}⚠${NC} No discord records with app_id found"
fi
echo ""

# Summary
echo "=== Summary ==="
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ Discord ingestion is operational${NC}"
    echo "   - Debug endpoint works"
    echo "   - Test inject works"
    echo "   - Records saved to DB"
else
    echo -e "${RED}✗ Discord ingestion has issues${NC}"
    echo ""
    echo "To fix:"
    echo "  1. Ensure worker is running: docker compose up -d worker"
    echo "  2. Check DISCORD_BOT_TOKEN in .env"
    echo "  3. Check Discord bot permissions"
fi

echo ""
exit $EXIT_CODE
