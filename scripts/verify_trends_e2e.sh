#!/bin/bash
set -e

# Verify Trends Contour E2E
# Checks: worker_trends process, trends tables, data in DB

echo "=== Verify Trends Contour E2E ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

EXIT_CODE=0
TREND_STATUS="NO DATA"

# 1. Check worker_trends container
echo "1. Checking worker_trends container..."
COMPOSE_OUTPUT=$(docker compose ps 2>&1 | grep -v "WARN" | grep -v "version" || true)

if echo "$COMPOSE_OUTPUT" | grep -q "game_scout-worker_trends.*Up"; then
    echo -e "   ${GREEN}✓${NC} worker_trends: Up"
    
    # Check what command it's running
    COMMAND=$(docker compose ps worker_trends 2>&1 | grep -v "WARN" | grep -v "version" | grep "worker_trends" | awk '{print $3}' || echo "unknown")
    echo "   Command: $COMMAND"
else
    echo -e "   ${RED}✗${NC} worker_trends: NOT RUNNING"
    EXIT_CODE=1
    TREND_STATUS="WORKER_NOT_RUNNING"
fi
echo ""

# 2. Check worker_trends logs (last 50 lines)
if [ $EXIT_CODE -eq 0 ]; then
    echo "2. Checking worker_trends logs (last 50 lines)..."
    LOGS=$(docker compose logs --tail 50 worker_trends 2>&1 | grep -v "WARN" | grep -v "version" || true)
    
    if [ -n "$LOGS" ]; then
        echo "   Recent log activity:"
        echo "$LOGS" | tail -5 | sed 's/^/     /'
        
        # Check for errors
        if echo "$LOGS" | grep -qi "error\|exception\|traceback"; then
            echo -e "   ${YELLOW}⚠${NC} Errors found in logs"
        fi
    else
        echo -e "   ${YELLOW}⚠${NC} No recent logs"
    fi
    echo ""
fi

# 3. Check trends_raw_events table
echo "3. Checking trends_raw_events table..."
EVENTS_24H=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
    SELECT COUNT(*)::text
    FROM trends_raw_events
    WHERE captured_at >= now() - interval '24 hours';
" 2>&1 | grep -v "time=" | grep -v "level=" | grep -E "^[0-9]+" || echo "0")

if [ "$EVENTS_24H" != "0" ] && [ -n "$EVENTS_24H" ]; then
    echo -e "   ${GREEN}✓${NC} Events in last 24h: $EVENTS_24H"
    TREND_STATUS="OK"
else
    echo -e "   ${YELLOW}⚠${NC} No events in last 24h"
fi

# Check by source
EVENTS_BY_SOURCE=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
    SELECT source, COUNT(*)::text
    FROM trends_raw_events
    WHERE captured_at >= now() - interval '24 hours'
    GROUP BY source
    ORDER BY COUNT(*) DESC;
" 2>&1 | grep -v "time=" | grep -v "level=" | grep -E "^[a-z_]+[[:space:]]+[0-9]+" || true)

if [ -n "$EVENTS_BY_SOURCE" ]; then
    echo "   Events by source:"
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            SOURCE=$(echo "$line" | awk '{print $1}')
            COUNT=$(echo "$line" | awk '{print $2}')
            echo -e "     ${GREEN}✓${NC} $SOURCE: $COUNT"
        fi
    done <<< "$EVENTS_BY_SOURCE"
fi
echo ""

# 4. Check trends_game_daily table
echo "4. Checking trends_game_daily table..."
DAILY_RECORDS=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
    SELECT COUNT(*)::text
    FROM trends_game_daily
    WHERE day >= CURRENT_DATE - interval '7 days';
" 2>&1 | grep -v "time=" | grep -v "level=" | grep -E "^[0-9]+" || echo "0")

if [ "$DAILY_RECORDS" != "0" ] && [ -n "$DAILY_RECORDS" ]; then
    echo -e "   ${GREEN}✓${NC} Daily records (last 7 days): $DAILY_RECORDS"
else
    echo -e "   ${YELLOW}⚠${NC} No daily records in last 7 days"
fi
echo ""

# 5. Check trends endpoint
echo "5. Checking /api/v1/trends/health endpoint..."
TRENDS_HEALTH=$(curl -sS "http://127.0.0.1:8000/api/v1/trends/health" 2>&1 || echo "ERROR")

if [ "$TRENDS_HEALTH" != "ERROR" ]; then
    STATUS=$(echo "$TRENDS_HEALTH" | jq -r '.status // "error"' 2>/dev/null || echo "error")
    if [ "$STATUS" = "ok" ] || [ "$STATUS" = "OK" ]; then
        echo -e "   ${GREEN}✓${NC} Trends health endpoint: OK"
    else
        echo -e "   ${YELLOW}⚠${NC} Trends health endpoint: $STATUS"
    fi
else
    echo -e "   ${RED}✗${NC} Trends health endpoint: NOT ACCESSIBLE"
    EXIT_CODE=1
fi
echo ""

# Summary
echo "=== Summary ==="
echo "TREND CONTOUR: $TREND_STATUS"

if [ "$TREND_STATUS" = "OK" ]; then
    echo -e "${GREEN}✓ Trends contour is operational${NC}"
    echo "   - worker_trends running"
    echo "   - Events collected"
    echo "   - Tables populated"
elif [ "$TREND_STATUS" = "NO DATA" ]; then
    echo -e "${YELLOW}⚠ Trends contour: NO DATA${NC}"
    echo "   Reasons:"
    echo "   - No events in trends_raw_events (last 24h)"
    echo "   - Possible causes:"
    echo "     * worker_trends not processing"
    echo "     * No events collected from sources"
    echo "     * Events not matching Steam games"
    EXIT_CODE=1
elif [ "$TREND_STATUS" = "WORKER_NOT_RUNNING" ]; then
    echo -e "${RED}✗ Trends contour: WORKER NOT RUNNING${NC}"
    echo "   To fix: docker compose up -d worker_trends"
    EXIT_CODE=1
fi

echo ""
exit $EXIT_CODE
