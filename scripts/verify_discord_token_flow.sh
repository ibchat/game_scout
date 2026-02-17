#!/usr/bin/env bash
set -e

echo "=== Verify Discord Token Flow ==="

# 1. Проверить, что docker-compose.yml содержит ${DISCORD_BOT_TOKEN} для api/worker
echo "1. Checking docker-compose.yml..."
API_HAS_TOKEN=$(grep -A 25 "^  api:" docker-compose.yml | grep "DISCORD_BOT_TOKEN:" | grep "\${DISCORD_BOT_TOKEN}" || echo "")
WORKER_HAS_TOKEN=$(grep -A 25 "^  worker:" docker-compose.yml | grep "DISCORD_BOT_TOKEN:" | grep "\${DISCORD_BOT_TOKEN}" || echo "")

if [[ -z "$API_HAS_TOKEN" ]]; then
  echo "❌ FAIL: api service missing DISCORD_BOT_TOKEN: \${DISCORD_BOT_TOKEN}"
  exit 1
fi

if [[ -z "$WORKER_HAS_TOKEN" ]]; then
  echo "❌ FAIL: worker service missing DISCORD_BOT_TOKEN: \${DISCORD_BOT_TOKEN}"
  exit 1
fi

echo "✅ docker-compose.yml config OK"

# 2. Запустить scripts/recreate_env_services.sh
echo "2. Recreating services..."
bash scripts/recreate_env_services.sh > /dev/null 2>&1
sleep 3

# 3. Проверить валидатор в api и worker
echo "3. Checking token validator in containers..."

API_CONFIGURED=$(docker compose exec -T api python - <<'PY'
import os
from apps.worker.tasks.collect_discord_signals import is_discord_token_configured
t=(os.getenv("DISCORD_BOT_TOKEN") or "").strip()
print(is_discord_token_configured(t))
PY
2>&1 | grep -v "time=" | grep -v "level=" | tail -1 || echo "ERROR")

WORKER_CONFIGURED=$(docker compose exec -T worker python - <<'PY'
import os
from apps.worker.tasks.collect_discord_signals import is_discord_token_configured
t=(os.getenv("DISCORD_BOT_TOKEN") or "").strip()
print(is_discord_token_configured(t))
PY
2>&1 | grep -v "time=" | grep -v "level=" | tail -1 || echo "ERROR")

if [[ "$API_CONFIGURED" == "ERROR" ]] || [[ "$WORKER_CONFIGURED" == "ERROR" ]]; then
  echo "❌ FAIL: Error checking token validator"
  exit 1
fi

echo "  API configured: $API_CONFIGURED"
echo "  WORKER configured: $WORKER_CONFIGURED"

if [[ "$API_CONFIGURED" != "$WORKER_CONFIGURED" ]]; then
  echo "⚠️  WARNING: API and WORKER have different token validation results"
fi

# 4. Дёрнуть endpoint
echo "4. Calling endpoint..."
RESPONSE=$(curl -4 -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?days=1&limit=5" 2>&1)

if [[ -z "$RESPONSE" ]]; then
  echo "❌ FAIL: Empty response from endpoint"
  exit 1
fi

# Проверяем JSON
if ! echo "$RESPONSE" | jq . > /dev/null 2>&1; then
  echo "❌ FAIL: Invalid JSON response"
  echo "Response: $RESPONSE"
  exit 1
fi

RESULT_STATUS=$(echo "$RESPONSE" | jq -r '.result.status' 2>/dev/null || echo "")
ERRORS=$(echo "$RESPONSE" | jq -r '.result.errors[] // ""' 2>/dev/null | grep -i "not configured" || echo "")

echo "  Result status: $RESULT_STATUS"
if [[ -n "$ERRORS" ]]; then
  echo "  Errors contain 'not configured': yes"
else
  echo "  Errors contain 'not configured': no"
fi

# Критерии PASS
if [[ "$API_CONFIGURED" == "False" ]] || [[ "$WORKER_CONFIGURED" == "False" ]]; then
  # Если валидатор False → endpoint должен вернуть skipped с "not configured"
  if [[ "$RESULT_STATUS" != "skipped" ]]; then
    echo "❌ FAIL: Token not configured but endpoint status is not 'skipped'"
    exit 1
  fi
  
  if [[ -z "$ERRORS" ]]; then
    echo "❌ FAIL: Token not configured but endpoint errors don't contain 'not configured'"
    exit 1
  fi
  
  echo "✅ PASS: Placeholder token correctly handled (skipped with 'not configured')"
  exit 0
else
  # Если валидатор True → endpoint НЕ должен возвращать "not configured"
  if [[ -n "$ERRORS" ]]; then
    echo "❌ FAIL: Token is configured but endpoint errors contain 'not configured'"
    exit 1
  fi
  
  echo "✅ PASS: Real token correctly handled (no 'not configured' error)"
  exit 0
fi

echo "✅ PASS: Token flow verification complete"
