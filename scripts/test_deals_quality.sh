#!/bin/bash
# Real test for Deals data quality
# DoD criteria:
# - titles_missing = 0
# - app_fallback = 0
# - release_missing = 0
# - old_games = 0
# - intent_unique > 3
# - quality_unique > 3

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Testing Deals Data Quality ===${NC}"

# Check if API is accessible
if ! curl -sSf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    echo -e "${RED}✗ API is not accessible at http://localhost:8000${NC}"
    exit 1
fi

echo -e "${GREEN}✓ API is accessible${NC}"

# Get data from API
API_RESPONSE=$(curl -sS "http://localhost:8000/api/v1/deals/list?limit=50" 2>/dev/null || echo "")

if [ -z "$API_RESPONSE" ]; then
    echo -e "${RED}✗ Failed to get data from API${NC}"
    exit 1
fi

# Parse response using jq
if ! command -v jq > /dev/null 2>&1; then
    echo -e "${RED}✗ jq is not installed. Install: brew install jq${NC}"
    exit 1
fi

# Extract metrics
COUNT=$(echo "$API_RESPONSE" | jq -r '.count // 0')
TITLES_MISSING=$(echo "$API_RESPONSE" | jq '[.games[]? | select(.title==null or .title=="")] | length')
APP_FALLBACK=$(echo "$API_RESPONSE" | jq '[.games[]? | select(.title | test("^App "))] | length')
RELEASE_MISSING=$(echo "$API_RESPONSE" | jq '[.games[]? | select(.release_date==null)] | length')

# Calculate current year for old games check
CURRENT_YEAR=$(date +%Y)
OLD_GAMES=$(echo "$API_RESPONSE" | jq --arg year "$CURRENT_YEAR" '[.games[]? | select(.release_date!=null and (.release_date | split("-")[0] | tonumber) < ($year | tonumber)-4)] | length')

# Check unique scores
INTENT_UNIQUE=$(echo "$API_RESPONSE" | jq '[.games[].intent_score] | unique | length')
QUALITY_UNIQUE=$(echo "$API_RESPONSE" | jq '[.games[].quality_score] | unique | length')

echo ""
echo "Results:"
echo "  count: $COUNT"
echo "  titles_missing: $TITLES_MISSING"
echo "  app_fallback: $APP_FALLBACK"
echo "  release_missing: $RELEASE_MISSING"
echo "  old_games: $OLD_GAMES"
echo "  intent_unique: $INTENT_UNIQUE"
echo "  quality_unique: $QUALITY_UNIQUE"
echo ""

# Check DoD criteria
PASS=true

if [ "$TITLES_MISSING" != "0" ]; then
    echo -e "${RED}✗ FAIL: titles_missing = $TITLES_MISSING (expected 0)${NC}"
    PASS=false
else
    echo -e "${GREEN}✓ PASS: titles_missing = 0${NC}"
fi

if [ "$APP_FALLBACK" != "0" ]; then
    echo -e "${RED}✗ FAIL: app_fallback = $APP_FALLBACK (expected 0)${NC}"
    PASS=false
else
    echo -e "${GREEN}✓ PASS: app_fallback = 0${NC}"
fi

if [ "$RELEASE_MISSING" != "0" ]; then
    echo -e "${RED}✗ FAIL: release_missing = $RELEASE_MISSING (expected 0)${NC}"
    PASS=false
else
    echo -e "${GREEN}✓ PASS: release_missing = 0${NC}"
fi

if [ "$OLD_GAMES" != "0" ]; then
    echo -e "${RED}✗ FAIL: old_games = $OLD_GAMES (expected 0)${NC}"
    PASS=false
else
    echo -e "${GREEN}✓ PASS: old_games = 0${NC}"
fi

if [ "$INTENT_UNIQUE" -le 3 ]; then
    echo -e "${RED}✗ FAIL: intent_unique = $INTENT_UNIQUE (expected > 3)${NC}"
    PASS=false
else
    echo -e "${GREEN}✓ PASS: intent_unique = $INTENT_UNIQUE (> 3)${NC}"
fi

if [ "$QUALITY_UNIQUE" -le 3 ]; then
    echo -e "${RED}✗ FAIL: quality_unique = $QUALITY_UNIQUE (expected > 3)${NC}"
    PASS=false
else
    echo -e "${GREEN}✓ PASS: quality_unique = $QUALITY_UNIQUE (> 3)${NC}"
fi

echo ""

if [ "$PASS" = true ]; then
    echo -e "${GREEN}✓✓✓ ALL TESTS PASSED ✓✓✓${NC}"
    exit 0
else
    echo -e "${RED}✗✗✗ TESTS FAILED ✗✗✗${NC}"
    exit 1
fi
