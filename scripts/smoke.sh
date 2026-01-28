#!/bin/bash
# Smoke test для проверки стабильности API после изменений
# Проверяет, что API запускается и отвечает на health endpoint

set -e

echo "🔍 Smoke test: проверка стабильности API..."
echo ""

# Перезапускаем API
echo "1. Перезапуск API..."
docker compose restart api

# Ждём 2 секунды для запуска
echo "2. Ожидание запуска (2 сек)..."
sleep 2

# Проверяем health endpoint
echo "3. Проверка health endpoint..."
HTTP_CODE=$(curl -4 -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/v1/health" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ PASS: API отвечает (HTTP $HTTP_CODE)"
    echo ""
    echo "Response:"
    curl -4 -s "http://127.0.0.1:8000/api/v1/health" | python3 -m json.tool 2>/dev/null || curl -4 -s "http://127.0.0.1:8000/api/v1/health"
    exit 0
else
    echo "❌ FAIL: API не отвечает (HTTP $HTTP_CODE)"
    echo ""
    echo "Логи API:"
    docker compose logs api --tail 50
    exit 1
fi
