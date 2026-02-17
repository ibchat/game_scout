#!/bin/bash
set -e

# Start all required services for Game Scout
# This ensures worker, beat, and other services are running

echo "=== Starting Game Scout Services ==="
echo ""

# Start services in order
echo "Starting infrastructure services..."
docker compose up -d postgres redis

echo "Waiting for postgres and redis to be healthy..."
sleep 5

echo "Starting application services..."
docker compose up -d api beat worker worker_trends

echo ""
echo "Waiting for services to start..."
sleep 3

echo ""
echo "=== Service Status ==="
docker compose ps | grep -E "NAME|postgres|redis|api|beat|worker" | grep -v "WARN" | grep -v "version" || true

echo ""
echo "=== Next Steps ==="
echo "1. Check status: docker compose ps"
echo "2. Verify workers: bash scripts/verify_workers_and_sources.sh"
echo "3. Check logs: docker compose logs -f worker"
