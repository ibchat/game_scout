#!/usr/bin/env bash
set -e

echo "=== Verify Discord ENV ==="

# 1. Проверяем, что docker compose config содержит DISCORD_BOT_TOKEN: не пустой строкой
echo "1. Checking docker compose config..."
CONFIG_HAS_TOKEN=$(docker compose config 2>&1 | grep "DISCORD_BOT_TOKEN:" || echo "")
if [[ -z "$CONFIG_HAS_TOKEN" ]]; then
  echo "❌ FAIL: DISCORD_BOT_TOKEN not found in docker compose config"
  exit 1
fi

# Проверяем, что значение не пустое
if echo "$CONFIG_HAS_TOKEN" | grep -q "DISCORD_BOT_TOKEN: $"; then
  echo "❌ FAIL: DISCORD_BOT_TOKEN is empty in docker compose config"
  exit 1
fi

echo "✅ DISCORD_BOT_TOKEN found in config"

# 2. Пересоздаём worker
echo "2. Recreating worker..."
docker compose up -d --force-recreate --no-deps worker > /dev/null 2>&1
sleep 5

# 3. Проверяем env внутри worker
echo "3. Checking env inside worker..."
TOKEN_LINE=$(docker compose exec -T worker sh -c 'env | grep "^DISCORD_BOT_TOKEN=" || echo "NO_TOKEN_IN_ENV"' 2>&1 | grep -v "time=" | grep -v "level=" | head -1 || echo "")

if [[ "$TOKEN_LINE" == "NO_TOKEN_IN_ENV" ]] || [[ -z "$TOKEN_LINE" ]]; then
  echo "❌ FAIL: DISCORD_BOT_TOKEN missing in worker env"
  exit 1
fi

TOKEN_VALUE=$(echo "$TOKEN_LINE" | sed 's/^DISCORD_BOT_TOKEN=//')

# Проверяем, является ли токен placeholder'ом
PLACEHOLDERS=("PUT_REAL_TOKEN_HERE" "PASTE_REAL_DISCORD_BOT_TOKEN_HERE" "REAL_TOKEN" "YOUR_REAL_TOKEN" "<EMPTY>")
IS_PLACEHOLDER=false

for placeholder in "${PLACEHOLDERS[@]}"; do
  if [[ "$TOKEN_VALUE" == "$placeholder" ]]; then
    IS_PLACEHOLDER=true
    break
  fi
done

# 4. Если токен placeholder или короткий → exit 0 но печатать WARNING
if [[ "$IS_PLACEHOLDER" == "true" ]]; then
  echo "⚠️  WARNING: DISCORD_BOT_TOKEN is placeholder ($TOKEN_VALUE)"
  echo "✅ PASS: Token is set (but placeholder)"
  exit 0
fi

if [[ ${#TOKEN_VALUE} -lt 20 ]]; then
  echo "⚠️  WARNING: DISCORD_BOT_TOKEN seems too short (length: ${#TOKEN_VALUE})"
  echo "✅ PASS: Token is set"
  exit 0
fi

# 5. Если токен валидный → exit 0 и PASS
echo "✅ PASS: DISCORD_BOT_TOKEN is set and looks valid (length: ${#TOKEN_VALUE} chars)"
