#!/bin/bash
set -e

# Detailed Sources Status Report
# Shows comprehensive status for each source with env keys, tasks, logs, DB records

echo "=== Detailed Sources Status Report ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if services are running
if ! docker compose ps 2>&1 | grep -q "game_scout-worker.*Up"; then
    echo -e "${RED}ERROR: Worker is not running${NC}"
    echo "Run: docker compose up -d worker"
    exit 1
fi

echo "Checking each source..."
echo ""

# Function to check source
check_source() {
    local SOURCE=$1
    local TASK_NAME=$2
    local ENV_KEY=$3
    
    echo "--- $SOURCE ---"
    
    # 1. Environment key
    if [ -n "$ENV_KEY" ]; then
        ENV_VALUE=$(docker compose exec -T worker env 2>&1 | grep "^${ENV_KEY}=" | cut -d'=' -f2 || echo "")
        if [ -n "$ENV_VALUE" ] && [ "$ENV_VALUE" != "" ]; then
            ENV_PREVIEW=$(echo "$ENV_VALUE" | cut -c1-20)
            echo -e "  Env key: ${GREEN}✓${NC} $ENV_KEY=${ENV_PREVIEW}..."
        else
            echo -e "  Env key: ${YELLOW}⚠${NC} $ENV_KEY not set"
        fi
    else
        echo -e "  Env key: ${GREEN}✓${NC} Not required"
    fi
    
    # 2. Celery task
    TASK_FOUND=$(docker compose exec -T worker celery -A apps.worker.celery_app inspect registered 2>&1 | grep -i "$TASK_NAME" || echo "")
    if [ -n "$TASK_FOUND" ]; then
        echo -e "  Celery task: ${GREEN}✓${NC} Registered"
    else
        echo -e "  Celery task: ${RED}✗${NC} Not registered"
    fi
    
    # 3. Recent logs
    LOG_COUNT=$(docker compose logs --tail 200 worker 2>&1 | grep -i "$SOURCE" | wc -l | tr -d ' ')
    if [ "$LOG_COUNT" -gt 0 ]; then
        echo -e "  Recent logs: ${GREEN}✓${NC} $LOG_COUNT mentions in last 200 lines"
    else
        echo -e "  Recent logs: ${YELLOW}⚠${NC} No mentions in last 200 lines"
    fi
    
    # 4. DB records (24h)
    DB_COUNT_24H=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
        SELECT COUNT(*)::text
        FROM deal_intent_signal
        WHERE source='$SOURCE' AND created_at >= now() - interval '24 hours';
    " 2>&1 | grep -v "time=" | grep -v "level=" | grep -E "^[0-9]+" | tr -d ' \n' || echo "0")
    
    if [ "$DB_COUNT_24H" != "0" ] && [ "$DB_COUNT_24H" != "" ]; then
        echo -e "  DB records (24h): ${GREEN}✓${NC} $DB_COUNT_24H signals"
    else
        echo -e "  DB records (24h): ${YELLOW}⚠${NC} 0 signals"
    fi
    
    # 5. Total DB records
    DB_TOTAL=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
        SELECT COUNT(*)::text
        FROM deal_intent_signal
        WHERE source='$SOURCE';
    " 2>&1 | grep -v "time=" | grep -v "level=" | grep -E "^[0-9]+" | tr -d ' \n' || echo "0")
    echo "  DB records (total): $DB_TOTAL signals"
    
    echo ""
}

# Check each source
check_source "reddit" "collect_deal_intent_signals_reddit" ""
check_source "discord" "collect_discord_signals" "DISCORD_BOT_TOKEN"
check_source "youtube" "collect_deal_intent_signals_youtube\|collect_youtube" "YOUTUBE_API_KEY"
check_source "tiktok" "collect_tiktok" "TIKTOK_API_KEY"
check_source "twitter" "collect_twitter" ""
check_source "steam" "collect_steam" ""

echo "=== Summary ==="
echo ""
echo "For Deal Intent, sources should write to: deal_intent_signal"
echo "For Trends, sources should write to: trends_raw_events"
echo ""
echo "To activate a source:"
echo "  1. Ensure worker is running"
echo "  2. Set required environment variables"
echo "  3. Verify task is registered"
echo "  4. Trigger collection manually or via beat schedule"
