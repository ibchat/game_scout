#!/bin/bash
# Apply deal_intent tables migration directly via SQL

set -e

echo "🔧 Applying deal_intent tables migration..."

# Find postgres container
POSTGRES_CONTAINER=$(docker compose ps -q postgres)
if [ -z "$POSTGRES_CONTAINER" ]; then
  echo "❌ Postgres container not found. Is docker compose running?"
  exit 1
fi

# Apply SQL migration
docker compose exec -T postgres psql -U postgres -d game_scout < migrations/apply_deal_intent_tables.sql

echo "✅ Migration applied successfully!"
echo ""
echo "Verifying tables..."
docker compose exec postgres psql -U postgres -d game_scout -c "\dt deal_intent*"
