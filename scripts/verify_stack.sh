#!/bin/bash
set -e

# Verify Stack Infrastructure
# Checks: docker compose, health endpoint, alembic, postgres

echo "=== Verify Stack Infrastructure ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

EXIT_CODE=0

# 1. Check docker compose services
echo "1. Checking Docker Compose services..."
COMPOSE_OUTPUT=$(docker compose ps 2>&1 | grep -v "WARN" | grep -v "version" || true)

# Check postgres
if echo "$COMPOSE_OUTPUT" | grep -q "game_scout-postgres.*healthy\|Up"; then
    echo -e "   ${GREEN}✓${NC} postgres: Up/Healthy"
else
    echo -e "   ${RED}✗${NC} postgres: NOT RUNNING or NOT HEALTHY"
    EXIT_CODE=1
fi

# Check redis
if echo "$COMPOSE_OUTPUT" | grep -q "game_scout-redis.*healthy\|Up"; then
    echo -e "   ${GREEN}✓${NC} redis: Up/Healthy"
else
    echo -e "   ${RED}✗${NC} redis: NOT RUNNING or NOT HEALTHY"
    EXIT_CODE=1
fi

# Check api
if echo "$COMPOSE_OUTPUT" | grep -q "game_scout-api.*Up"; then
    echo -e "   ${GREEN}✓${NC} api: Up"
else
    echo -e "   ${RED}✗${NC} api: NOT RUNNING"
    EXIT_CODE=1
fi

echo ""

# 2. Check health endpoint
echo "2. Checking API health endpoint..."
HEALTH_RESPONSE=$(curl -sS -f "http://127.0.0.1:8000/api/v1/health" 2>&1 || echo "ERROR")
if echo "$HEALTH_RESPONSE" | grep -q "healthy\|ok"; then
    echo -e "   ${GREEN}✓${NC} /api/v1/health: OK"
    echo "   Response: $(echo "$HEALTH_RESPONSE" | head -1)"
else
    echo -e "   ${RED}✗${NC} /api/v1/health: FAILED"
    echo "   Error: $HEALTH_RESPONSE"
    EXIT_CODE=1
fi
echo ""

# 3. Check alembic (if api container is running)
if echo "$COMPOSE_OUTPUT" | grep -q "game_scout-api.*Up"; then
    echo "3. Checking Alembic migrations..."
    ALEMBIC_CURRENT=$(docker compose exec -T api alembic current 2>&1 | grep -v "time=" | grep -v "level=" | head -1 || echo "ERROR")
    ALEMBIC_HEADS=$(docker compose exec -T api alembic heads 2>&1 | grep -v "time=" | grep -v "level=" | head -1 || echo "ERROR")
    
    if [ "$ALEMBIC_CURRENT" != "ERROR" ] && [ "$ALEMBIC_HEADS" != "ERROR" ]; then
        CURRENT_REV=$(echo "$ALEMBIC_CURRENT" | awk '{print $1}' | head -1)
        HEADS_REV=$(echo "$ALEMBIC_HEADS" | awk '{print $1}' | head -1)
        
        if [ "$CURRENT_REV" = "$HEADS_REV" ]; then
            echo -e "   ${GREEN}✓${NC} Alembic: current == heads ($CURRENT_REV)"
        else
            echo -e "   ${YELLOW}⚠${NC} Alembic: current ($CURRENT_REV) != heads ($HEADS_REV)"
            echo "   Run: docker compose exec api alembic upgrade head"
        fi
    else
        echo -e "   ${YELLOW}⚠${NC} Alembic: Could not check (api container may not be ready)"
    fi
    echo ""
fi

# 4. Check postgres access
echo "4. Checking PostgreSQL access..."
PG_TEST=$(docker compose exec -T postgres psql -U postgres -d game_scout -c "SELECT 1;" 2>&1 | grep -v "time=" | grep -v "level=" | grep -E "^[[:space:]]*1[[:space:]]*$" || echo "ERROR")
if [ "$PG_TEST" != "ERROR" ] && echo "$PG_TEST" | grep -q "1"; then
    echo -e "   ${GREEN}✓${NC} PostgreSQL: Accessible"
else
    echo -e "   ${RED}✗${NC} PostgreSQL: NOT ACCESSIBLE"
    EXIT_CODE=1
fi
echo ""

# Summary
echo "=== Summary ==="
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All infrastructure checks passed${NC}"
else
    echo -e "${RED}✗ Some infrastructure checks failed${NC}"
    echo ""
    echo "To fix:"
    echo "  bash scripts/up_all.sh"
fi

echo ""
exit $EXIT_CODE
