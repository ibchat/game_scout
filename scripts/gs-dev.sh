#!/bin/bash
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
    echo "   Run: ./scripts/gs-dev.sh from your host machine."
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

# Check docker compose
if ! docker compose version &> /dev/null; then
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

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    # Check if API is ready using Python inside container (no curl needed)
    if docker compose exec -T api python -c "
import sys
try:
    import httpx
    response = httpx.get('http://localhost:8000/api/v1/health', timeout=2)
    sys.exit(0 if response.status_code == 200 else 1)
except:
    sys.exit(1)
" 2>/dev/null; then
        API_READY=true
        break
    fi
    
    ATTEMPT=$((ATTEMPT + 1))
    sleep 2
done

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
    # Run with autofix mode (will be implemented in supervisor)
    docker compose exec -T api python dev_supervisor/run.py --autofix
else
    docker compose exec -T api python dev_supervisor/run.py
fi

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Dev Orchestrator: STABLE"
else
    echo "❌ Dev Orchestrator: FAILED (exit code: $EXIT_CODE)"
    if [ "$AUTOFIX_MODE" = false ]; then
        echo ""
        echo "💡 Tip: Run with --autofix to attempt automatic fixes:"
        echo "   ./scripts/gs-dev.sh --autofix"
    fi
fi

exit $EXIT_CODE
