#!/bin/bash
# Verify Deals / Intent data quality
# Criteria:
# - ≥95% games with real names (not "App ####")
# - ≥90% games with release_date
# - 0 games older than 4 years in output (if filter enabled)
# - API and UI show same data

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Data Truth Check ===${NC}"

# Detect postgres container name
POSTGRES_CONTAINER=""
if docker ps --format "{{.Names}}" 2>/dev/null | grep -q "^postgres$"; then
    POSTGRES_CONTAINER="postgres"
elif docker ps --format "{{.Names}}" 2>/dev/null | grep -q "postgres"; then
    POSTGRES_CONTAINER=$(docker ps --format "{{.Names}}" 2>/dev/null | grep postgres | head -1)
elif docker-compose ps --services 2>/dev/null | grep -q postgres; then
    # Try docker-compose naming
    POSTGRES_CONTAINER="game_scout-postgres-1"  # Common docker-compose naming
fi

# Check if we can connect to DB
if [ -n "$POSTGRES_CONTAINER" ]; then
    if docker exec "$POSTGRES_CONTAINER" psql -U postgres -d game_scout -c "SELECT 1" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Database connection OK (container: $POSTGRES_CONTAINER)${NC}"
        USE_DB=true
    else
        echo -e "${YELLOW}⚠ Cannot connect to database via docker, trying API...${NC}"
        USE_DB=false
    fi
else
    echo -e "${YELLOW}⚠ Postgres container not found, using API for checks...${NC}"
    USE_DB=false
fi

# Step 1: Check deal_intent_game table
echo -e "\n${YELLOW}1. deal_intent_game table:${NC}"
if [ "$USE_DB" = true ]; then
    TOTAL_DEALS=$(docker exec "$POSTGRES_CONTAINER" psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM deal_intent_game" | tr -d ' ')
    WITH_NAME=$(docker exec "$POSTGRES_CONTAINER" psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM deal_intent_game WHERE steam_name IS NOT NULL AND steam_name != ''" | tr -d ' ')
    WITH_RELEASE=$(docker exec "$POSTGRES_CONTAINER" psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM deal_intent_game WHERE release_date IS NOT NULL" | tr -d ' ')
    APP_FORMAT=$(docker exec "$POSTGRES_CONTAINER" psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM deal_intent_game WHERE steam_name LIKE 'App %' OR steam_name LIKE 'App #%'" | tr -d ' ')
    echo "  Total rows: $TOTAL_DEALS"
    echo "  With steam_name: $WITH_NAME"
    echo "  With release_date: $WITH_RELEASE"
    echo "  App #### format: $APP_FORMAT"
else
    echo "  Skipping (using API checks instead)"
    TOTAL_DEALS="?"
    WITH_NAME="?"
    WITH_RELEASE="?"
    APP_FORMAT="?"
fi

# Step 2: Check steam_app_cache coverage
echo -e "\n${YELLOW}2. steam_app_cache coverage:${NC}"
if [ "$USE_DB" = true ]; then
    CACHE_COUNT=$(docker exec "$POSTGRES_CONTAINER" psql -U postgres -d game_scout -t -c "
        SELECT COUNT(DISTINCT d.app_id)
        FROM deal_intent_game d
        INNER JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
    " | tr -d ' ')
    echo "  deal_intent_game apps with cache: $CACHE_COUNT / $TOTAL_DEALS"
    
    CACHE_WITH_NAME=$(docker exec "$POSTGRES_CONTAINER" psql -U postgres -d game_scout -t -c "
        SELECT COUNT(DISTINCT d.app_id)
        FROM deal_intent_game d
        INNER JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
        WHERE c.name IS NOT NULL AND c.name != ''
    " | tr -d ' ')
    echo "  With real name in cache: $CACHE_WITH_NAME / $TOTAL_DEALS"
else
    echo "  Skipping (using API checks instead)"
fi

# Step 3: Check steam_app_facts coverage
echo -e "\n${YELLOW}3. steam_app_facts coverage:${NC}"
if [ "$USE_DB" = true ]; then
    FACTS_COUNT=$(docker exec "$POSTGRES_CONTAINER" psql -U postgres -d game_scout -t -c "
        SELECT COUNT(DISTINCT d.app_id)
        FROM deal_intent_game d
        INNER JOIN steam_app_facts f ON f.steam_app_id = d.app_id
    " | tr -d ' ')
    echo "  deal_intent_game apps with facts: $FACTS_COUNT / $TOTAL_DEALS"
else
    echo "  Skipping (using API checks instead)"
fi

# Step 4: Sample problematic rows
echo -e "\n${YELLOW}4. Sample problematic rows (App #### format):${NC}"
if [ "$USE_DB" = true ]; then
    docker exec "$POSTGRES_CONTAINER" psql -U postgres -d game_scout -c "
        SELECT d.app_id, d.steam_name, 
               CASE WHEN c.name IS NOT NULL THEN 'cache' ELSE 'no cache' END as source
        FROM deal_intent_game d
        LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
        WHERE d.steam_name LIKE 'App %' OR d.steam_name LIKE 'App #%'
        LIMIT 5
    "
else
    echo "  Skipping (check API response for 'App ####' titles)"
fi

# Step 5: Check old games (>4 years)
echo -e "\n${YELLOW}5. Old games (>4 years):${NC}"
if [ "$USE_DB" = true ]; then
    OLD_GAMES=$(docker exec "$POSTGRES_CONTAINER" psql -U postgres -d game_scout -t -c "
        SELECT COUNT(*)
        FROM deal_intent_game d
        LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
        LEFT JOIN steam_app_facts f ON f.steam_app_id = d.app_id
        WHERE COALESCE(c.release_date, f.release_date, d.release_date) < CURRENT_DATE - INTERVAL '4 years'
    " | tr -d ' ')
    echo "  Games older than 4 years: $OLD_GAMES"
else
    echo "  Will check in API response"
    OLD_GAMES="?"
fi

# Step 6: Test API endpoint
echo -e "\n${YELLOW}6. Testing API endpoint /api/v1/deals/list:${NC}"
API_RESPONSE=$(curl -sS "http://localhost:8000/api/v1/deals/list?limit=50" 2>/dev/null || echo "")
if [ -z "$API_RESPONSE" ]; then
    echo -e "${RED}✗ API not accessible${NC}"
    exit 1
fi

# Parse API response
GAMES_COUNT=$(echo "$API_RESPONSE" | grep -o '"count":[0-9]*' | head -1 | cut -d':' -f2 || echo "0")
echo "  Games returned: $GAMES_COUNT"

# Check names in API response
APP_FORMAT_API=$(echo "$API_RESPONSE" | grep -o '"title":"App [0-9]*"' | wc -l | tr -d ' ')
REAL_NAMES=$((GAMES_COUNT - APP_FORMAT_API))
REAL_NAMES_PCT=$((REAL_NAMES * 100 / GAMES_COUNT)) 2>/dev/null || echo "0"

echo "  Real names: $REAL_NAMES / $GAMES_COUNT ($REAL_NAMES_PCT%)"

# Check release_date in API response
WITH_RELEASE_API=$(echo "$API_RESPONSE" | grep -o '"release_date":"[^"]*"' | wc -l | tr -d ' ')
WITH_RELEASE_PCT=$((WITH_RELEASE_API * 100 / GAMES_COUNT)) 2>/dev/null || echo "0"
echo "  With release_date: $WITH_RELEASE_API / $GAMES_COUNT ($WITH_RELEASE_PCT%)"

# Check old games in API response
OLD_IN_API=$(echo "$API_RESPONSE" | grep -o '"release_date":"[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"' | while read date; do
    YEAR=$(echo "$date" | cut -d'"' -f4 | cut -d'-' -f1)
    if [ "$YEAR" -lt 2020 ]; then
        echo "old"
    fi
done | wc -l | tr -d ' ')
echo "  Old games in API output: $OLD_IN_API"

# Step 7: Final verdict
echo -e "\n${YELLOW}=== Verification Results ===${NC}"

PASS=true

if [ "$REAL_NAMES_PCT" -lt 95 ]; then
    echo -e "${RED}✗ FAIL: Real names < 95% ($REAL_NAMES_PCT%)${NC}"
    PASS=false
else
    echo -e "${GREEN}✓ PASS: Real names ≥ 95% ($REAL_NAMES_PCT%)${NC}"
fi

if [ "$WITH_RELEASE_PCT" -lt 90 ]; then
    echo -e "${RED}✗ FAIL: Games with release_date < 90% ($WITH_RELEASE_PCT%)${NC}"
    PASS=false
else
    echo -e "${GREEN}✓ PASS: Games with release_date ≥ 90% ($WITH_RELEASE_PCT%)${NC}"
fi

if [ "$OLD_IN_API" -gt 0 ]; then
    echo -e "${RED}✗ FAIL: Old games (>4 years) in output: $OLD_IN_API${NC}"
    PASS=false
else
    echo -e "${GREEN}✓ PASS: No old games in output${NC}"
fi

if [ "$PASS" = true ]; then
    echo -e "\n${GREEN}✓✓✓ ALL CHECKS PASSED ✓✓✓${NC}"
    exit 0
else
    echo -e "\n${RED}✗✗✗ VERIFICATION FAILED ✗✗✗${NC}"
    exit 1
fi
