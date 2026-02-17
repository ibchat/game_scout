#!/bin/bash
# Guardrail script for Game Scout
# Checks: no unexpected deletions, alembic chain validity, Python syntax

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

EXIT_CODE=0
ERRORS=()

echo "=== Guardrail Checks ==="
echo ""

# Check 1: No unexpected file deletions
echo "1. Checking for unexpected file deletions..."
DELETED=$(git diff --name-status HEAD | grep '^D' | grep -v '^D\t\(DOCKER_SETUP\|QUICK_FIX\|scripts/check_environment\|scripts/test_dashboard_comprehensive\)' || true)

if [ -n "$DELETED" ]; then
    echo -e "   ${RED}✗${NC} Unexpected file deletions detected:"
    echo "$DELETED" | sed 's/^/      /'
    ERRORS+=("Unexpected file deletions")
    EXIT_CODE=1
else
    echo -e "   ${GREEN}✓${NC} No unexpected file deletions"
fi
echo ""

# Check 2: Alembic chain validity (if Docker is available)
echo "2. Checking Alembic migration chain..."
if command -v docker &> /dev/null && docker ps &> /dev/null; then
    if docker compose ps api &> /dev/null | grep -q "Up"; then
        # Check alembic heads (should be single head)
        HEADS=$(docker compose exec -T api alembic heads 2>&1 | grep -v "INFO:" | wc -l || echo "0")
        if [ "$HEADS" -gt 1 ]; then
            echo -e "   ${RED}✗${NC} Multiple Alembic heads detected"
            docker compose exec -T api alembic heads 2>&1 | grep -v "INFO:" | sed 's/^/      /'
            ERRORS+=("Multiple Alembic heads")
            EXIT_CODE=1
        else
            echo -e "   ${GREEN}✓${NC} Alembic chain valid (single head)"
        fi
        
        # Try to validate history
        if docker compose exec -T api alembic history &> /dev/null; then
            echo -e "   ${GREEN}✓${NC} Alembic history valid"
        else
            echo -e "   ${YELLOW}⚠${NC} Could not validate Alembic history"
        fi
    else
        echo -e "   ${YELLOW}⚠${NC} API container not running, skipping Alembic check"
    fi
else
    echo -e "   ${YELLOW}⚠${NC} Docker not available, skipping Alembic check"
fi
echo ""

# Check 3: Python syntax (if Python available)
echo "3. Checking Python syntax..."
if command -v python3 &> /dev/null; then
    # Check Intel module syntax
    if [ -d "apps/intel" ]; then
        if python3 -m py_compile apps/intel/**/*.py 2>&1 | grep -v "\.pyc"; then
            echo -e "   ${GREEN}✓${NC} Intel module syntax valid"
        else
            SYNTAX_ERRORS=$(python3 -m py_compile apps/intel/**/*.py 2>&1 | grep -v "\.pyc" || true)
            if [ -n "$SYNTAX_ERRORS" ]; then
                echo -e "   ${RED}✗${NC} Python syntax errors in Intel module:"
                echo "$SYNTAX_ERRORS" | sed 's/^/      /'
                ERRORS+=("Python syntax errors")
                EXIT_CODE=1
            else
                echo -e "   ${GREEN}✓${NC} Intel module syntax valid"
            fi
        fi
    else
        echo -e "   ${YELLOW}⚠${NC} Intel module not found, skipping syntax check"
    fi
else
    echo -e "   ${YELLOW}⚠${NC} Python3 not available, skipping syntax check"
fi
echo ""

# Check 4: No changes to existing migrations (except current Intel migration)
echo "4. Checking for unauthorized migration changes..."
MODIFIED_MIGRATIONS=$(git diff --name-only HEAD | grep "migrations/versions/" | grep -v "009_add_intel_tables.py" || true)

if [ -n "$MODIFIED_MIGRATIONS" ]; then
    echo -e "   ${RED}✗${NC} Unauthorized changes to existing migrations:"
    echo "$MODIFIED_MIGRATIONS" | sed 's/^/      /'
    echo "   Only new migrations (009_intel_tables) should be added"
    ERRORS+=("Unauthorized migration changes")
    EXIT_CODE=1
else
    echo -e "   ${GREEN}✓${NC} No unauthorized migration changes"
fi
echo ""

# Summary
echo "=== Summary ==="
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All guardrail checks passed${NC}"
    exit 0
else
    echo -e "${RED}✗ Guardrail checks failed${NC}"
    echo ""
    echo "Errors:"
    for error in "${ERRORS[@]}"; do
        echo "  - $error"
    done
    echo ""
    echo "Please fix the issues above before committing."
    exit 1
fi
