#!/bin/bash
# Comprehensive Dashboard Test Script
# Tests all dashboard endpoints and functionality

set -e

API_BASE="http://localhost:8000"
DASHBOARD_URL="${API_BASE}/dashboard"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0
WARNINGS=0

test_endpoint() {
    local name=$1
    local url=$2
    local method=${3:-GET}
    local expected_status=${4:-200}
    
    echo -n "  Testing $name... "
    
    if [ "$method" = "GET" ]; then
        HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$url" 2>&1 || echo "000")
    else
        HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" -X "$method" "$url" 2>&1 || echo "000")
    fi
    
    if [ "$HTTP_CODE" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} HTTP $HTTP_CODE"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} HTTP $HTTP_CODE (expected $expected_status)"
        ((FAILED++))
        return 1
    fi
}

test_json_response() {
    local name=$1
    local url=$2
    
    echo -n "  Testing JSON response for $name... "
    
    RESPONSE=$(curl -sS "$url" 2>&1 || echo "ERROR")
    
    if [ "$RESPONSE" = "ERROR" ]; then
        echo -e "${RED}✗${NC} Request failed"
        ((FAILED++))
        return 1
    fi
    
    # Check if it's valid JSON
    if echo "$RESPONSE" | python3 -m json.tool > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Valid JSON"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} Invalid JSON"
        ((FAILED++))
        return 1
    fi
}

echo -e "${BLUE}=== Comprehensive Dashboard Test ===${NC}"
echo ""

# 1. Check if API is running
echo "1. Checking API availability..."
if curl -sS -f "${API_BASE}/" > /dev/null 2>&1; then
    echo -e "   ${GREEN}✓${NC} API is running"
    ((PASSED++))
else
    echo -e "   ${RED}✗${NC} API is not running"
    echo "   Please start API: docker compose up -d api"
    ((FAILED++))
    exit 1
fi
echo ""

# 2. Test Dashboard Endpoint
echo "2. Testing Dashboard Endpoint..."
test_endpoint "Dashboard HTML" "${DASHBOARD_URL}" "GET" "200"

# Check if it returns HTML
DASHBOARD_CONTENT=$(curl -sS "${DASHBOARD_URL}" 2>&1 | head -5 || echo "")
if echo "$DASHBOARD_CONTENT" | grep -qi "<!doctype html\|<html"; then
    echo -e "   ${GREEN}✓${NC} Returns HTML content"
    ((PASSED++))
else
    echo -e "   ${RED}✗${NC} Does not return HTML"
    ((FAILED++))
fi
echo ""

# 3. Test System Endpoints
echo "3. Testing System Endpoints..."
test_endpoint "System Summary" "${API_BASE}/api/v1/admin/system/summary"
test_json_response "System Summary" "${API_BASE}/api/v1/admin/system/summary"
echo ""

# 4. Test Trends Endpoints
echo "4. Testing Trends Endpoints..."
test_endpoint "Emerging Games" "${API_BASE}/api/v1/trends/emerging?limit=20"
test_json_response "Emerging Games" "${API_BASE}/api/v1/trends/emerging?limit=20"
test_endpoint "Emerging Diagnostics" "${API_BASE}/api/v1/trends/emerging/diagnostics"
test_json_response "Emerging Diagnostics" "${API_BASE}/api/v1/trends/emerging/diagnostics"
echo ""

# 5. Test Deals Endpoints
echo "5. Testing Deals Endpoints..."
test_endpoint "Deals List" "${API_BASE}/api/v1/deals/list?limit=10"
test_json_response "Deals List" "${API_BASE}/api/v1/deals/list?limit=10"
test_endpoint "Deals Diagnostics" "${API_BASE}/api/v1/deals/diagnostics"
test_json_response "Deals Diagnostics" "${API_BASE}/api/v1/deals/diagnostics"
echo ""

# 6. Test Sources Endpoints
echo "6. Testing Sources Endpoints..."
test_endpoint "YouTube Health" "${API_BASE}/api/v1/youtube/health"
test_endpoint "Reddit Health" "${API_BASE}/api/v1/reddit/health"
echo ""

# 7. Test Games Endpoints
echo "7. Testing Games Endpoints..."
test_endpoint "Games Health" "${API_BASE}/api/v1/games/health"
test_endpoint "Games List" "${API_BASE}/api/v1/games/list?limit=10"
test_json_response "Games List" "${API_BASE}/api/v1/games/list?limit=10"
echo ""

# 8. Test Relaunch Endpoints
echo "8. Testing Relaunch Endpoints..."
test_endpoint "Relaunch Health" "${API_BASE}/api/v1/relaunch/health"
test_endpoint "Relaunch Candidates" "${API_BASE}/api/v1/relaunch/candidates?limit=10"
test_json_response "Relaunch Candidates" "${API_BASE}/api/v1/relaunch/candidates?limit=10"
echo ""

# 9. Test VOY Endpoints (if enabled)
echo "9. Testing VOY Endpoints..."
VOY_HEALTH=$(curl -sS -o /dev/null -w "%{http_code}" "${API_BASE}/api/v1/voy/health" 2>&1 || echo "000")
if [ "$VOY_HEALTH" = "200" ] || [ "$VOY_HEALTH" = "404" ]; then
    if [ "$VOY_HEALTH" = "200" ]; then
        echo -e "   ${GREEN}✓${NC} VOY module is enabled"
        test_endpoint "VOY Health" "${API_BASE}/api/v1/voy/health"
        test_endpoint "VOY Runs" "${API_BASE}/api/v1/voy/runs?limit=10"
    else
        echo -e "   ${YELLOW}⚠${NC} VOY module is not enabled (404)"
        ((WARNINGS++))
    fi
else
    echo -e "   ${RED}✗${NC} VOY endpoint error: HTTP $VOY_HEALTH"
    ((FAILED++))
fi
echo ""

# 10. Test Health Endpoint
echo "10. Testing Health Endpoint..."
test_endpoint "API Health" "${API_BASE}/api/v1/health"
test_json_response "API Health" "${API_BASE}/api/v1/health"
echo ""

# Summary
echo -e "${BLUE}=== Test Summary ===${NC}"
echo -e "   ${GREEN}Passed:${NC} $PASSED"
echo -e "   ${RED}Failed:${NC} $FAILED"
echo -e "   ${YELLOW}Warnings:${NC} $WARNINGS"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed! Dashboard is fully operational.${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Please check the errors above.${NC}"
    exit 1
fi
