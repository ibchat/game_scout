#!/bin/bash
# Скрипт проверки дашборда

echo "=== Проверка дашборда Game Scout ==="
echo ""

# Проверка 1: Файл существует
if [ -f "apps/api/static/game_scout_dashboard.html" ]; then
    echo "✓ Файл дашборда существует"
    SIZE=$(wc -c < apps/api/static/game_scout_dashboard.html)
    echo "  Размер: $SIZE байт"
else
    echo "✗ Файл дашборда НЕ найден!"
    exit 1
fi

# Проверка 2: Базовая структура
if grep -q "<!doctype html>" apps/api/static/game_scout_dashboard.html; then
    echo "✓ HTML структура найдена"
else
    echo "✗ HTML структура не найдена"
fi

if grep -q "<script>" apps/api/static/game_scout_dashboard.html && grep -q "</script>" apps/api/static/game_scout_dashboard.html; then
    echo "✓ JavaScript секция найдена"
else
    echo "✗ JavaScript секция не найдена"
fi

# Проверка 3: Критические функции
CRITICAL_FUNCS=("loadSystem" "switchTab" "jget" "qs" "qsa")
for func in "${CRITICAL_FUNCS[@]}"; do
    if grep -q "function $func\|async function $func" apps/api/static/game_scout_dashboard.html; then
        echo "✓ Функция $func найдена"
    else
        echo "✗ Функция $func НЕ найдена"
    fi
done

# Проверка 4: API константа
if grep -q 'const API =' apps/api/static/game_scout_dashboard.html; then
    API_VALUE=$(grep -o "const API = ['\"][^'\"]*['\"]" apps/api/static/game_scout_dashboard.html | head -1)
    echo "✓ Константа API найдена: $API_VALUE"
else
    echo "✗ Константа API не найдена"
fi

# Проверка 5: Инициализация
if grep -q "DOMContentLoaded\|document.readyState" apps/api/static/game_scout_dashboard.html; then
    echo "✓ Проверка готовности DOM найдена"
else
    echo "⚠️ Проверка готовности DOM не найдена"
fi

if grep -q "loadSystem()" apps/api/static/game_scout_dashboard.html; then
    echo "✓ Вызов loadSystem() найден"
else
    echo "✗ Вызов loadSystem() не найден"
fi

echo ""
echo "=== Проверка завершена ==="
echo ""
echo "Для проверки в браузере:"
echo "1. Убедитесь, что API сервер запущен: docker compose up -d"
echo "2. Откройте: http://localhost:8000/dashboard"
echo "3. Откройте консоль браузера (F12) и проверьте ошибки"
echo "4. Проверьте Network tab - должны быть запросы к /api/v1/admin/system/summary"
