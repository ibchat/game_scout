#!/bin/bash
# Скрипт обновления Relaunch Scout MVP
# Выполняет миграции и перезапускает сервисы

set -e

echo "🚀 Обновление Relaunch Scout MVP..."

# 1. Проверка подключения к БД
echo "📊 Проверка подключения к БД..."
docker compose exec -T postgres psql -U postgres -d game_scout -c "SELECT 1;" > /dev/null 2>&1 || {
    echo "❌ Ошибка: не удалось подключиться к БД"
    exit 1
}
echo "✅ БД доступна"

# 2. Создание таблицы relaunch_scan_runs
echo "📋 Создание таблицы relaunch_scan_runs..."
docker compose exec -T postgres psql -U postgres -d game_scout -f migrations/create_relaunch_scan_runs.sql 2>&1 | grep -v "already exists" || true
echo "✅ Таблица relaunch_scan_runs готова"

# 3. Создание таблицы relaunch_failure_analysis
echo "📋 Создание таблицы relaunch_failure_analysis..."
docker compose exec -T postgres psql -U postgres -d game_scout -f migrations/create_relaunch_failure_analysis.sql 2>&1 | grep -v "already exists" || true
echo "✅ Таблица relaunch_failure_analysis готова"

# 4. Перезапуск API
echo "🔄 Перезапуск API..."
docker compose restart api
echo "⏳ Ожидание запуска API (10 сек)..."
sleep 10

# 5. Проверка health endpoint
echo "🏥 Проверка health endpoint..."
HEALTH_RESPONSE=$(curl -s http://localhost:8000/api/v1/relaunch/health 2>&1 || echo "ERROR")
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo "✅ API работает"
    echo "$HEALTH_RESPONSE" | jq '.' 2>/dev/null || echo "$HEALTH_RESPONSE"
else
    echo "⚠️  API не отвечает или вернул ошибку:"
    echo "$HEALTH_RESPONSE"
    echo "📋 Логи API:"
    docker compose logs api --tail 20
fi

echo ""
echo "✅ Обновление завершено!"
echo ""
echo "📝 Следующие шаги:"
echo "1. Проверь дашборд: http://localhost:8000/dashboard"
echo "2. Открой вкладку 'Relaunch Scout'"
echo "3. Попробуй 'Сканировать рынок' (вкладка Scan)"
echo "4. После сканирования запусти 'Диагностику' (вкладка Diagnosis)"
echo "5. Проверь список кандидатов (вкладка Candidates)"
