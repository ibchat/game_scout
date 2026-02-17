#!/usr/bin/env bash
# Verify Autopilot C+ Setup - Diagnostic script
# Checks all prerequisites and setup without applying fixes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "🔍 Verifying Autopilot C+ Setup"
echo "================================"
echo ""

ERRORS=0

# 1) Host/Container check
echo "1. Checking execution context..."
if [ -f "/.dockerenv" ] || [ "${IN_DOCKER:-}" = "1" ]; then
    echo "   ❌ Running inside container (should run on host)"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ Running on host"
fi
echo ""

# 2) Docker presence
echo "2. Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "   ❌ Docker not found"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ Docker found: $(docker --version)"
fi

if ! docker compose version &> /dev/null 2>&1; then
    echo "   ❌ docker compose not found"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ docker compose found: $(docker compose version | head -1)"
fi
echo ""

# 3) Docker services
echo "3. Checking Docker services..."
if ! docker compose ps api &> /dev/null 2>&1; then
    echo "   ⚠️  Services not running, starting..."
    docker compose up -d
    sleep 5
else
    echo "   ✅ Services running"
fi
echo ""

# 4) Inside api container checks
echo "4. Checking inside api container..."

# Check git
if docker compose exec -T api git --version &> /dev/null 2>&1; then
    echo "   ✅ git available"
else
    echo "   ❌ git not found in container"
    ERRORS=$((ERRORS + 1))
fi

# Check python
if docker compose exec -T api python --version &> /dev/null 2>&1; then
    PYTHON_VERSION=$(docker compose exec -T api python --version 2>&1)
    echo "   ✅ python available: $PYTHON_VERSION"
else
    echo "   ❌ python not found in container"
    ERRORS=$((ERRORS + 1))
fi

# Check imports
echo "   Checking Python imports..."
for module in pytest feedparser yaml httpx; do
    if docker compose exec -T api python -c "import $module" 2>/dev/null; then
        echo "   ✅ $module importable"
    else
        echo "   ❌ $module not importable"
        ERRORS=$((ERRORS + 1))
    fi
done
echo ""

# 5) Intel health endpoint
echo "5. Checking Intel health endpoint..."
HEALTH_CHECK_SCRIPT=$(mktemp)
cat > "$HEALTH_CHECK_SCRIPT" <<'PYTHON_SCRIPT'
import sys
import httpx

try:
    response = httpx.get('http://localhost:8000/api/v1/intel/health', timeout=5)
    if response.status_code == 200:
        print("OK")
        sys.exit(0)
    elif response.status_code == 404:
        print("404 - Intel router not mounted")
        sys.exit(1)
    else:
        print(f"HTTP {response.status_code}")
        sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
PYTHON_SCRIPT

if docker compose exec -T api python "$HEALTH_CHECK_SCRIPT" 2>&1 | grep -q "OK"; then
    echo "   ✅ Intel health endpoint accessible (200)"
elif docker compose exec -T api python "$HEALTH_CHECK_SCRIPT" 2>&1 | grep -q "404"; then
    echo "   ❌ Intel health endpoint returned 404 (router not mounted)"
    ERRORS=$((ERRORS + 1))
else
    HEALTH_OUTPUT=$(docker compose exec -T api python "$HEALTH_CHECK_SCRIPT" 2>&1 || true)
    echo "   ⚠️  Intel health endpoint issue: $HEALTH_OUTPUT"
    ERRORS=$((ERRORS + 1))
fi
rm -f "$HEALTH_CHECK_SCRIPT"
echo ""

# 6) Check intel_raw_items count
echo "6. Checking intel_raw_items in database..."
RAW_ITEMS_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM intel_raw_items;" 2>/dev/null | tr -d ' ' || echo "0")
if [ "$RAW_ITEMS_COUNT" = "" ]; then
    RAW_ITEMS_COUNT=0
fi

if [ "$RAW_ITEMS_COUNT" -gt 0 ]; then
    echo "   ✅ intel_raw_items count: $RAW_ITEMS_COUNT"
else
    echo "   ⚠️  intel_raw_items is empty (expected after first smoke test)"
fi
echo ""

# Summary
echo "================================"
if [ $ERRORS -eq 0 ]; then
    echo "✅ All checks passed"
    exit 0
else
    echo "❌ Found $ERRORS issue(s)"
    exit 1
fi
