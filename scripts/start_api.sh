#!/bin/bash
# Start API in background mode
# Usage: bash scripts/start_api.sh

echo "Starting API in detached mode..."
docker-compose up -d api

echo "Waiting for API to be ready..."
sleep 3

# Check if API is responding
MAX_RETRIES=10
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if curl -sSf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
        echo "✓ API is ready at http://localhost:8000"
        echo "  Dashboard: http://localhost:8000/dashboard"
        exit 0
    fi
    sleep 1
    RETRY=$((RETRY + 1))
done

echo "⚠ API started but not responding yet. Check logs:"
echo "  docker-compose logs api"
