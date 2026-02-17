#!/bin/bash
set -e

# Verify Dashboard Accessibility
# Checks: dashboard endpoint, basic API calls

echo "=== Verify Dashboard ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

EXIT_CODE=0

# 1. Check dashboard endpoint
echo "1. Checking /dashboard endpoint..."
DASHBOARD_RESPONSE=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/dashboard" 2>&1 || echo "ERROR")

if [ "$DASHBOARD_RESPONSE" = "200" ]; then
    echo -e "   ${GREEN}✓${NC} Dashboard endpoint: 200 OK"
elif [ "$DASHBOARD_RESPONSE" = "ERROR" ]; then
    echo -e "   ${RED}✗${NC} Dashboard endpoint: NOT ACCESSIBLE"
    EXIT_CODE=1
else
    echo -e "   ${RED}✗${NC} Dashboard endpoint: HTTP $DASHBOARD_RESPONSE"
    EXIT_CODE=1
fi
echo ""

# 2. Check dashboard content (should be HTML)
echo "2. Checking dashboard content..."
DASHBOARD_CONTENT=$(curl -sS "http://127.0.0.1:8000/dashboard" 2>&1 | head -5 || echo "ERROR")

if [ "$DASHBOARD_CONTENT" != "ERROR" ] && echo "$DASHBOARD_CONTENT" | grep -qi "<html\|<!DOCTYPE"; then
    echo -e "   ${GREEN}✓${NC} Dashboard returns HTML"
else
    echo -e "   ${RED}✗${NC} Dashboard does not return HTML"
    echo "   Content preview: $(echo "$DASHBOARD_CONTENT" | head -2)"
    EXIT_CODE=1
fi
echo ""

# 3. Check key API endpoint used by dashboard
echo "3. Checking key API endpoint (/api/v1/deals/signals/list)..."
LIST_RESPONSE=$(curl -sS "http://127.0.0.1:8000/api/v1/deals/signals/list?min_intent_score=0&min_quality_score=0&limit=5" 2>&1 || echo "ERROR")

if [ "$LIST_RESPONSE" != "ERROR" ]; then
    HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/v1/deals/signals/list?min_intent_score=0&min_quality_score=0&limit=5" 2>&1 || echo "500")
    
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "   ${GREEN}✓${NC} API endpoint: 200 OK"
        
        # Check if response is valid JSON
        STATUS=$(echo "$LIST_RESPONSE" | jq -r '.status // "error"' 2>/dev/null || echo "error")
        if [ "$STATUS" = "ok" ] || [ "$STATUS" = "OK" ]; then
            echo -e "   ${GREEN}✓${NC} API response: valid JSON with status=ok"
        else
            echo -e "   ${YELLOW}⚠${NC} API response: status=$STATUS"
        fi
    else
        echo -e "   ${RED}✗${NC} API endpoint: HTTP $HTTP_CODE"
        EXIT_CODE=1
    fi
else
    echo -e "   ${RED}✗${NC} API endpoint: NOT ACCESSIBLE"
    EXIT_CODE=1
fi
echo ""

# Summary
echo "=== Summary ==="
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ Dashboard is accessible and operational${NC}"
    echo "   - Dashboard endpoint: 200 OK"
    echo "   - Dashboard returns HTML"
    echo "   - Key API endpoint works"
else
    echo -e "${RED}✗ Dashboard has issues${NC}"
    echo ""
    echo "To fix:"
    echo "  1. Ensure api service is running: docker compose up -d api"
    echo "  2. Check api logs: docker compose logs --tail 100 api"
    echo "  3. Verify dashboard file exists: ls -la apps/api/static/game_scout_dashboard.html"
fi

echo ""
exit $EXIT_CODE
