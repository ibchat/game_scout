#!/bin/bash
set -e

# Verify Deal Intent Contour E2E
# Checks: deal_intent_signal table, list endpoint

echo "=== Verify Deal Intent Contour E2E ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

EXIT_CODE=0

# 1. Check table exists and has data
echo "1. Checking deal_intent_signal table..."
DB_SOURCES=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
    SELECT source, source_subtype, COUNT(*)::text as count
    FROM deal_intent_signal
    GROUP BY source, source_subtype
    ORDER BY COUNT(*) DESC;
" 2>&1 | grep -v "time=" | grep -v "level=" | grep -v "ERROR" | grep -E "^[a-z_]+[[:space:]]+[a-z_]*[[:space:]]+[0-9]+" || true)

if [ -z "$DB_SOURCES" ] || [ "$DB_SOURCES" = "" ]; then
    echo -e "   ${YELLOW}⚠${NC} No data in deal_intent_signal table"
    EXIT_CODE=1
else
    echo "   Sources in database:"
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            SOURCE=$(echo "$line" | awk '{print $1}')
            SUBTYPE=$(echo "$line" | awk '{print $2}')
            COUNT=$(echo "$line" | awk '{print $3}')
            echo -e "     ${GREEN}✓${NC} $SOURCE / $SUBTYPE: $COUNT signals"
        fi
    done <<< "$DB_SOURCES"
fi
echo ""

# 2. Check unique app_ids
echo "2. Checking unique app_ids..."
UNIQUE_APP_IDS=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
    SELECT COUNT(DISTINCT app_id)::text
    FROM deal_intent_signal
    WHERE app_id IS NOT NULL;
" 2>&1 | grep -v "time=" | grep -v "level=" | grep -E "^[0-9]+" || echo "0")

if [ "$UNIQUE_APP_IDS" != "0" ] && [ -n "$UNIQUE_APP_IDS" ]; then
    echo -e "   ${GREEN}✓${NC} Unique app_ids: $UNIQUE_APP_IDS"
else
    echo -e "   ${YELLOW}⚠${NC} No app_ids found (no Steam games matched)"
fi
echo ""

# 3. Check list endpoint
echo "3. Checking /api/v1/deals/signals/list endpoint..."
LIST_RESPONSE=$(curl -sS "http://127.0.0.1:8000/api/v1/deals/signals/list?min_intent_score=0&min_quality_score=0&limit=5" 2>&1 || echo "ERROR")

if [ "$LIST_RESPONSE" = "ERROR" ]; then
    echo -e "   ${RED}✗${NC} Endpoint failed or not accessible"
    EXIT_CODE=1
else
    # Check if response is valid JSON and has count
    COUNT=$(echo "$LIST_RESPONSE" | jq -r '.count // 0' 2>/dev/null || echo "0")
    STATUS=$(echo "$LIST_RESPONSE" | jq -r '.status // "error"' 2>/dev/null || echo "error")
    
    if [ "$STATUS" = "ok" ] || [ "$STATUS" = "OK" ]; then
        if [ "$COUNT" -gt 0 ]; then
            echo -e "   ${GREEN}✓${NC} Endpoint OK: count=$COUNT"
        else
            echo -e "   ${YELLOW}⚠${NC} Endpoint OK but count=0 (no signals match filters)"
        fi
    else
        echo -e "   ${RED}✗${NC} Endpoint returned error status: $STATUS"
        echo "   Response: $(echo "$LIST_RESPONSE" | head -3)"
        EXIT_CODE=1
    fi
fi
echo ""

# Summary
echo "=== Summary ==="
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ Deal Intent contour is operational${NC}"
    echo "   - Table accessible"
    echo "   - Endpoint responds"
else
    echo -e "${RED}✗ Deal Intent contour has issues${NC}"
    echo ""
    echo "To fix:"
    echo "  1. Ensure worker is running: docker compose up -d worker"
    echo "  2. Run ingestion: curl -X POST 'http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?days=7&limit=50'"
fi

echo ""
exit $EXIT_CODE
