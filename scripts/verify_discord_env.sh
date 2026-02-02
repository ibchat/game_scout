#!/usr/bin/env bash
set -e

echo "=== Verify Discord ENV ==="

# 1. Проверяем, что в docker-compose.yml нет пустого DISCORD_BOT_TOKEN:
echo "1. Checking docker-compose.yml for empty DISCORD_BOT_TOKEN..."
EMPTY_TOKENS=$(grep "DISCORD_BOT_TOKEN:$" docker-compose.yml || echo "")
if [[ -n "$EMPTY_TOKENS" ]]; then
  echo "❌ FAIL: Found empty DISCORD_BOT_TOKEN: in docker-compose.yml"
  echo "$EMPTY_TOKENS"
  exit 1
fi
echo "✅ No empty DISCORD_BOT_TOKEN: found"

# 2. Проверяем, что docker compose config содержит DISCORD_BOT_TOKEN: (хотя бы 1 раз)
echo "2. Checking docker compose config..."
CONFIG_HAS_TOKEN=$(docker compose config 2>&1 | grep "DISCORD_BOT_TOKEN:" || echo "")
if [[ -z "$CONFIG_HAS_TOKEN" ]]; then
  echo "❌ FAIL: DISCORD_BOT_TOKEN not found in docker compose config"
  exit 1
fi
echo "✅ DISCORD_BOT_TOKEN found in config"

# 3. Пересоздаём worker
echo "3. Recreating worker..."
docker compose up -d --force-recreate --no-deps worker > /dev/null 2>&1
sleep 5

# 4. Проверяем внутри контейнера
echo "4. Checking env inside worker..."
TOKEN_LINE=$(docker compose exec -T worker sh -c 'env | grep "^DISCORD_BOT_TOKEN=" || echo "NO_TOKEN_IN_ENV"' 2>&1 | grep -v "time=" | grep -v "level=" | head -1 || echo "")

if [[ "$TOKEN_LINE" == "NO_TOKEN_IN_ENV" ]] || [[ -z "$TOKEN_LINE" ]]; then
  echo "❌ FAIL: DISCORD_BOT_TOKEN missing in worker env"
  exit 1
fi

TOKEN_VALUE=$(echo "$TOKEN_LINE" | sed 's/^DISCORD_BOT_TOKEN=//')

# 5. Если токен = PUT_REAL_TOKEN_HERE → exit 0, но печатать WARNING
if [[ "$TOKEN_VALUE" == "PUT_REAL_TOKEN_HERE" ]]; then
  echo "⚠️  WARNING: DISCORD_BOT_TOKEN is placeholder (PUT_REAL_TOKEN_HERE)"
  echo "✅ PASS: Token is set (but placeholder)"
  exit 0
fi

# 6. Если переменной нет → exit 1 (уже проверено выше)
echo "✅ PASS: DISCORD_BOT_TOKEN is set (length: ${#TOKEN_VALUE} chars)"
