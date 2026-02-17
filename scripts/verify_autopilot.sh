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
    GIT_VERSION=$(docker compose exec -T api git --version 2>&1)
    echo "   ✅ git found in container: $GIT_VERSION"
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

# 5) Intel health endpoint (check both paths, no temp files)
echo "5. Checking Intel health endpoint..."
INTEL_HEALTH_OK=false
INTEL_HEALTH_ERROR=""

# Try /api/v1/intel/health first
HEALTH_OUTPUT=$(docker compose exec -T api python -c "
import sys
import httpx

try:
    # Try /api/v1/intel/health first
    try:
        response = httpx.get('http://localhost:8000/api/v1/intel/health', timeout=5)
        if response.status_code == 200:
            print('OK:/api/v1/intel/health')
            sys.exit(0)
        elif response.status_code == 404:
            # Try /intel/health as fallback
            try:
                response2 = httpx.get('http://localhost:8000/intel/health', timeout=5)
                if response2.status_code == 200:
                    print('OK:/intel/health')
                    sys.exit(0)
                else:
                    print(f'FAIL: Both paths returned non-200. /api/v1/intel/health={response.status_code}, /intel/health={response2.status_code}')
                    sys.exit(1)
            except Exception as e2:
                print(f'FAIL: /api/v1/intel/health=404, /intel/health error: {e2}')
                sys.exit(1)
        else:
            print(f'FAIL: /api/v1/intel/health returned HTTP {response.status_code}')
            sys.exit(1)
    except Exception as e:
        # Try /intel/health as fallback
        try:
            response2 = httpx.get('http://localhost:8000/intel/health', timeout=5)
            if response2.status_code == 200:
                print('OK:/intel/health')
                sys.exit(0)
            else:
                print(f'FAIL: /intel/health returned HTTP {response2.status_code}, first attempt error: {e}')
                sys.exit(1)
        except Exception as e2:
            print(f'FAIL: Both attempts failed. First: {e}, Second: {e2}')
            sys.exit(1)
except Exception as e:
    print(f'FAIL: Unexpected error: {e}')
    sys.exit(1)
" 2>&1) || INTEL_HEALTH_ERROR="$HEALTH_OUTPUT"

if echo "$HEALTH_OUTPUT" | grep -q "OK:"; then
    ENDPOINT_PATH=$(echo "$HEALTH_OUTPUT" | grep "OK:" | cut -d: -f2)
    echo "   ✅ Intel health endpoint accessible (200) at $ENDPOINT_PATH"
    INTEL_HEALTH_OK=true
elif echo "$HEALTH_OUTPUT" | grep -q "404"; then
    echo "   ❌ Intel health endpoint returned 404 (router not mounted)"
    echo "      Tried: /api/v1/intel/health and /intel/health"
    ERRORS=$((ERRORS + 1))
else
    echo "   ❌ Intel health endpoint issue: $INTEL_HEALTH_ERROR"
    ERRORS=$((ERRORS + 1))
fi
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

# 7) Check policy allowlist
echo "7. Checking Intel policy allowlist..."
POLICY_CHECK=$(docker compose exec -T api python -c "
import sys
try:
    from apps.intel.policy.policy_engine import load_policy
    policy = load_policy()
    allowed_domains = policy.get('allowed_domains', [])
    if allowed_domains:
        print(f'OK:{len(allowed_domains)} domains')
        sys.exit(0)
    else:
        print('WARN:allowed_domains is empty')
        sys.exit(0)
except Exception as e:
    print(f'ERROR:{e}')
    sys.exit(1)
" 2>&1)

if echo "$POLICY_CHECK" | grep -q "OK:"; then
    DOMAIN_COUNT=$(echo "$POLICY_CHECK" | grep "OK:" | cut -d: -f2 | cut -d' ' -f1)
    echo "   ✅ Policy allowlist has $DOMAIN_COUNT domain(s)"
elif echo "$POLICY_CHECK" | grep -q "WARN:"; then
    echo "   ⚠️  Policy allowlist is empty (warn only, not blocking)"
else
    echo "   ❌ Failed to check policy allowlist: $POLICY_CHECK"
    ERRORS=$((ERRORS + 1))
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
