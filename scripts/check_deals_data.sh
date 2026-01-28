#!/bin/bash
# Wrapper script for SQL data check
# Detects postgres container and runs SQL script

# Detect postgres container name
POSTGRES_CONTAINER=""
if docker ps --format "{{.Names}}" 2>/dev/null | grep -q "^postgres$"; then
    POSTGRES_CONTAINER="postgres"
elif docker ps --format "{{.Names}}" 2>/dev/null | grep -q "postgres"; then
    POSTGRES_CONTAINER=$(docker ps --format "{{.Names}}" 2>/dev/null | grep postgres | head -1)
elif docker-compose ps --services 2>/dev/null | grep -q postgres; then
    # Try docker-compose naming
    POSTGRES_CONTAINER="game_scout-postgres-1"
fi

if [ -z "$POSTGRES_CONTAINER" ]; then
    echo "Error: Postgres container not found"
    echo "Available containers:"
    docker ps --format "{{.Names}}" 2>/dev/null || echo "  (docker not accessible)"
    exit 1
fi

echo "Using postgres container: $POSTGRES_CONTAINER"
docker exec -i "$POSTGRES_CONTAINER" psql -U postgres -d game_scout < scripts/check_deals_data.sql
