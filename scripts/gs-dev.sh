#!/bin/bash
# Game Scout Dev Orchestrator - Single command runner
# Runs dev_supervisor inside Docker container

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "🚀 Game Scout Dev Orchestrator"
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

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 5

# Run supervisor inside container
echo "🔍 Running dev supervisor..."
echo ""

docker compose exec -T api python dev_supervisor/run.py

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Dev Orchestrator: STABLE"
else
    echo "❌ Dev Orchestrator: FAILED (exit code: $EXIT_CODE)"
fi

exit $EXIT_CODE
