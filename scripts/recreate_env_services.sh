#!/usr/bin/env bash
set -e

echo "=== Recreating services with updated env ==="

# Пересоздаём api и worker с обновлёнными переменными окружения
echo "1. Recreating api and worker..."
docker compose up -d --force-recreate --no-deps api worker > /dev/null 2>&1
sleep 5

# Проверяем env внутри контейнеров (без вывода полного токена)
echo "2. Checking env in containers..."
echo "API:"
docker compose exec -T api sh -c 'echo "DISCORD_BOT_TOKEN=<set> (length: ${#DISCORD_BOT_TOKEN})"; env | grep "^DISCORD_BOT_TOKEN=" > /dev/null 2>&1 && echo "  ✅ Token is set" || echo "  ❌ Token missing"' 2>&1 | grep -v "time=" | grep -v "level=" || true

echo "WORKER:"
docker compose exec -T worker sh -c 'echo "DISCORD_BOT_TOKEN=<set> (length: ${#DISCORD_BOT_TOKEN})"; env | grep "^DISCORD_BOT_TOKEN=" > /dev/null 2>&1 && echo "  ✅ Token is set" || echo "  ❌ Token missing"' 2>&1 | grep -v "time=" | grep -v "level=" || true

echo "✅ Services recreated"
