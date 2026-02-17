#!/bin/bash
set -e

# Verify Workers and Sources
# Checks that worker/beat are running and sources are collecting data

echo "=== Verify Workers and Sources ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

EXIT_CODE=0
ACTION_REQUIRED=""

# 1. Check docker compose services
echo "1. Checking Docker Compose services..."
COMPOSE_OUTPUT=$(docker compose ps 2>&1 | grep -v "WARN" | grep -v "version" || true)

# Check worker
if echo "$COMPOSE_OUTPUT" | grep -q "game_scout-worker.*Up"; then
    echo -e "   ${GREEN}✓${NC} worker: Up"
else
    echo -e "   ${RED}✗${NC} worker: NOT RUNNING"
    EXIT_CODE=1
    ACTION_REQUIRED="${ACTION_REQUIRED}worker is not running. "
fi

# Check beat
if echo "$COMPOSE_OUTPUT" | grep -q "game_scout-beat.*Up"; then
    echo -e "   ${GREEN}✓${NC} beat: Up"
else
    echo -e "   ${RED}✗${NC} beat: NOT RUNNING"
    EXIT_CODE=1
    ACTION_REQUIRED="${ACTION_REQUIRED}beat is not running. "
fi

# Check worker_trends (optional, but good to know)
if echo "$COMPOSE_OUTPUT" | grep -q "game_scout-worker_trends.*Up"; then
    echo -e "   ${GREEN}✓${NC} worker_trends: Up"
else
    echo -e "   ${YELLOW}⚠${NC} worker_trends: NOT RUNNING (optional)"
fi

echo ""

# 2. Check worker is actually responding
if [ $EXIT_CODE -eq 0 ]; then
    echo "2. Checking worker connectivity..."
    if docker compose exec -T worker celery -A apps.worker.celery_app inspect ping 2>&1 | grep -q "pong"; then
        echo -e "   ${GREEN}✓${NC} worker responds to ping"
    else
        echo -e "   ${RED}✗${NC} worker does not respond"
        EXIT_CODE=1
        ACTION_REQUIRED="${ACTION_REQUIRED}worker is not responding. "
    fi
    echo ""
fi

# 3. Check registered tasks (if worker is up)
if [ $EXIT_CODE -eq 0 ]; then
    echo "3. Checking registered tasks..."
    REGISTERED=$(docker compose exec -T worker celery -A apps.worker.celery_app inspect registered 2>&1 | grep -E "reddit|youtube|tiktok|twitter|discord" || true)
    
    SOURCES_FOUND=0
    if echo "$REGISTERED" | grep -qi "reddit"; then
        echo -e "   ${GREEN}✓${NC} reddit tasks registered"
        SOURCES_FOUND=$((SOURCES_FOUND + 1))
    fi
    if echo "$REGISTERED" | grep -qi "youtube"; then
        echo -e "   ${GREEN}✓${NC} youtube tasks registered"
        SOURCES_FOUND=$((SOURCES_FOUND + 1))
    fi
    if echo "$REGISTERED" | grep -qi "tiktok"; then
        echo -e "   ${GREEN}✓${NC} tiktok tasks registered"
        SOURCES_FOUND=$((SOURCES_FOUND + 1))
    fi
    if echo "$REGISTERED" | grep -qi "twitter"; then
        echo -e "   ${GREEN}✓${NC} twitter tasks registered"
        SOURCES_FOUND=$((SOURCES_FOUND + 1))
    fi
    if echo "$REGISTERED" | grep -qi "discord"; then
        echo -e "   ${GREEN}✓${NC} discord tasks registered"
        SOURCES_FOUND=$((SOURCES_FOUND + 1))
    fi
    
    if [ $SOURCES_FOUND -eq 0 ]; then
        echo -e "   ${YELLOW}⚠${NC} No source tasks found in registered tasks"
    fi
    echo ""
fi

# 4. Detailed sources status table
echo "4. Sources Status Table (Deal Intent):"
echo ""
printf "%-12s | %-10s | %-20s | %-30s\n" "SOURCE" "STATUS" "LAST_SIGNAL_AT" "REASON"
echo "------------|-----------|---------------------|------------------------------"

SOURCES=("reddit" "discord" "youtube" "twitter" "tiktok" "steam")
SOURCES_WITH_DATA=0

for SOURCE in "${SOURCES[@]}"; do
    # Check if source has data in last 24h
    LAST_SIGNAL=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
        SELECT MAX(created_at)::text
        FROM deal_intent_signal
        WHERE source='$SOURCE' AND created_at >= now() - interval '24 hours';
    " 2>&1 | grep -v "time=" | grep -v "level=" | grep -v "ERROR" | tr -d ' \n' || echo "")
    
    # Check total count
    TOTAL_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
        SELECT COUNT(*)::text
        FROM deal_intent_signal
        WHERE source='$SOURCE';
    " 2>&1 | grep -v "time=" | grep -v "level=" | grep -v "ERROR" | grep -E "^[0-9]+" | tr -d ' \n' || echo "0")
    
    # Check if task is registered
    TASK_REGISTERED="NO"
    if [ $EXIT_CODE -eq 0 ]; then
        if echo "$REGISTERED" | grep -qi "$SOURCE"; then
            TASK_REGISTERED="YES"
        fi
    fi
    
    # Determine status
    STATUS="UNKNOWN"
    REASON=""
    
    if [ "$TOTAL_COUNT" != "0" ] && [ -n "$TOTAL_COUNT" ] && [ "$TOTAL_COUNT" -gt 0 ] 2>/dev/null; then
        if [ -n "$LAST_SIGNAL" ] && [ "$LAST_SIGNAL" != "" ]; then
            STATUS="ACTIVE"
            SOURCES_WITH_DATA=$((SOURCES_WITH_DATA + 1))
            REASON="Has data in last 24h"
        else
            STATUS="STALE"
            REASON="Has data but none in last 24h"
        fi
    else
        if [ "$TASK_REGISTERED" = "YES" ]; then
            STATUS="NO_DATA"
            REASON="Task registered but no data"
        else
            STATUS="DISABLED"
            REASON="Task not registered"
        fi
    fi
    
    # Format last signal time
    if [ -n "$LAST_SIGNAL" ] && [ "$LAST_SIGNAL" != "" ]; then
        LAST_SIGNAL_DISPLAY=$(echo "$LAST_SIGNAL" | cut -d' ' -f1,2 | cut -d'T' -f1,2 | sed 's/T/ /' | cut -d'.' -f1 || echo "N/A")
    else
        LAST_SIGNAL_DISPLAY="N/A"
    fi
    
    # Color code status
    if [ "$STATUS" = "ACTIVE" ]; then
        STATUS_DISPLAY="${GREEN}ACTIVE${NC}"
    elif [ "$STATUS" = "STALE" ]; then
        STATUS_DISPLAY="${YELLOW}STALE${NC}"
    elif [ "$STATUS" = "NO_DATA" ]; then
        STATUS_DISPLAY="${YELLOW}NO_DATA${NC}"
    elif [ "$STATUS" = "DISABLED" ]; then
        STATUS_DISPLAY="${RED}DISABLED${NC}"
    else
        STATUS_DISPLAY="${RED}UNKNOWN${NC}"
    fi
    
    printf "%-12s | %-10s | %-20s | %-30s\n" "$SOURCE" "$STATUS_DISPLAY" "$LAST_SIGNAL_DISPLAY" "$REASON"
done

echo ""
echo "   Summary: $SOURCES_WITH_DATA source(s) with recent data (last 24h)"
if [ "$SOURCES_WITH_DATA" -lt 2 ]; then
    echo -e "   ${YELLOW}⚠${NC} Expected at least 2 active sources (Reddit + Discord minimum)"
    if [ "$SOURCES_WITH_DATA" -eq 0 ]; then
        ACTION_REQUIRED="${ACTION_REQUIRED}No sources collecting data. "
    fi
fi
echo ""

# 5. Summary
echo "=== Summary ==="
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All critical checks passed${NC}"
    if [ -n "$ACTION_REQUIRED" ]; then
        echo -e "${YELLOW}⚠ Warnings: $ACTION_REQUIRED${NC}"
    fi
else
    echo -e "${RED}✗ Some checks failed${NC}"
    echo -e "${RED}ACTION_REQUIRED: $ACTION_REQUIRED${NC}"
    echo ""
    echo "To fix, run:"
    echo "  docker compose up -d worker beat"
    echo "  or"
    echo "  bash scripts/up_all.sh"
fi

echo ""
exit $EXIT_CODE
