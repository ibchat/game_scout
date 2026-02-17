#!/usr/bin/env bash
# Game Scout Dev Orchestrator - Single command runner
# Runs dev_supervisor inside Docker container
# MUST be run on host, not inside container

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Check if running inside container (must run on host)
if [ -f "/.dockerenv" ] || [ "${IN_DOCKER:-}" = "1" ]; then
    echo "❌ This script must be run on the host, not inside a container."
    echo "   Run: bash scripts/gs-dev.sh from your host machine."
    exit 2
fi

# Parse arguments
AUTOFIX_MODE=false
if [ "${1:-}" = "--autofix" ]; then
    AUTOFIX_MODE=true
fi

echo "🚀 Game Scout Dev Orchestrator"
if [ "$AUTOFIX_MODE" = true ]; then
    echo "   Mode: AUTOFIX (will attempt to fix issues automatically)"
fi
echo "================================"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker."
    exit 1
fi

# Check docker compose (not docker-compose)
if ! docker compose version &> /dev/null 2>&1; then
    echo "❌ docker compose not found. Please install Docker Compose."
    exit 1
fi

# Ensure services are up
echo "📦 Ensuring Docker services are running..."
docker compose up -d --build

# Wait for services to be ready (with readiness check)
echo "⏳ Waiting for services to be ready..."
MAX_ATTEMPTS=30
ATTEMPT=0
API_READY=false
INTEL_HEALTH_OK=false

# Create temporary Python script for readiness check (avoid heredoc issues)
READINESS_SCRIPT=$(mktemp)
cat > "$READINESS_SCRIPT" <<'PYTHON_SCRIPT'
import sys
import httpx

try:
    # Check standard health endpoint
    try:
        response = httpx.get('http://localhost:8000/api/v1/health', timeout=2)
        if response.status_code == 200:
            health_ok = True
        else:
            health_ok = False
    except:
        health_ok = False
    
    # Check Intel health endpoint
    try:
        response = httpx.get('http://localhost:8000/api/v1/intel/health', timeout=2)
        if response.status_code == 200:
            intel_ok = True
        elif response.status_code == 404:
            print("ERROR: Intel router not mounted (404 on /api/v1/intel/health)", file=sys.stderr)
            intel_ok = False
        else:
            intel_ok = False
    except Exception as e:
        intel_ok = False
    
    if health_ok and intel_ok:
        sys.exit(0)
    elif health_ok:
        # API is up but Intel not ready - this is OK for now
        sys.exit(0)
    else:
        sys.exit(1)
except Exception as e:
    sys.exit(1)
PYTHON_SCRIPT

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    # Check if API is ready using Python script inside container
    if docker compose exec -T api python "$READINESS_SCRIPT" 2>&1 | grep -q "Intel router not mounted"; then
        echo "❌ Intel router not mounted in apps/api/main.py"
        rm -f "$READINESS_SCRIPT"
        exit 1
    fi
    
    if docker compose exec -T api python "$READINESS_SCRIPT" 2>/dev/null; then
        API_READY=true
        INTEL_HEALTH_OK=true
        break
    fi
    
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
        sleep 2
    fi
done

rm -f "$READINESS_SCRIPT"

if [ "$API_READY" = false ]; then
    echo "⚠️  API did not become ready after $((MAX_ATTEMPTS * 2)) seconds"
    echo "   Showing last API logs:"
    docker compose logs --tail=20 api
    echo ""
    echo "   Continuing anyway..."
fi

# Run supervisor inside container
echo "🔍 Running dev supervisor..."
echo ""

if [ "$AUTOFIX_MODE" = true ]; then
    docker compose exec -T api python dev_supervisor/run.py --autofix
else
    docker compose exec -T api python dev_supervisor/run.py
fi

EXIT_CODE=$?

# Run production check if supervisor passed
if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "🔍 Running Intel production check..."
    echo ""
    
    if docker compose exec -T api bash scripts/intel_production_check.sh 2>&1; then
        PROD_CHECK_EXIT=0
    else
        PROD_CHECK_EXIT=$?
        if [ $PROD_CHECK_EXIT -ne 0 ]; then
            echo ""
            echo "⚠️  Production check failed (exit code: $PROD_CHECK_EXIT)"
            echo "   This may indicate pipeline issues even if supervisor passed."
            # Don't fail gs-dev.sh, just warn
        fi
    fi
fi

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Dev Orchestrator: STABLE"
    if [ "${PROD_CHECK_EXIT:-0}" -eq 0 ]; then
        echo "✅ Production Check: PASSED"
    else
        echo "⚠️  Production Check: FAILED (see above)"
    fi
else
    echo "❌ Dev Orchestrator: FAILED (exit code: $EXIT_CODE)"
    if [ "$AUTOFIX_MODE" = false ]; then
        echo ""
        echo "💡 Tip: Run with --autofix to attempt automatic fixes:"
        echo "   bash scripts/gs-dev.sh --autofix"
    fi
fi

exit $EXIT_CODE
