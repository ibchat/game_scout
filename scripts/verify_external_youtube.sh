#!/bin/bash
# Скрипт проверки YouTube API ключа в контейнерах
# Проверяет наличие и валидность ключа в api и worker контейнерах

set -e

echo "🔍 Проверка YouTube API ключа в контейнерах..."
echo ""

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=true

# Функция для проверки ключа в контейнере
check_container_key() {
    local container=$1
    local container_name=$2
    
    echo "📦 Проверка контейнера: $container_name"
    
    # Проверяем наличие переменной
    local key=$(docker compose exec -T $container python -c "
import os
key = os.getenv('YOUTUBE_API_KEY') or os.getenv('GOOGLE_API_KEY')
if key:
    print(key)
" 2>/dev/null || echo "")
    
    if [ -z "$key" ]; then
        echo -e "${RED}❌ FAIL: Ключ не найден в контейнере $container_name${NC}"
        echo "   Проверьте .env файл и docker-compose.yml"
        PASS=false
        return 1
    fi
    
    # Маскируем ключ для вывода (первые 4 символа + ***)
    local masked=""
    if [ ${#key} -ge 4 ]; then
        masked="${key:0:4}***"
    else
        masked="***"
    fi
    
    # Проверяем длину ключа
    if [ ${#key} -lt 20 ]; then
        echo -e "${YELLOW}⚠️  WARN: Ключ слишком короткий (${#key} символов, ожидается >= 20)${NC}"
        echo "   Маскированный ключ: $masked"
        PASS=false
        return 1
    fi
    
    echo -e "${GREEN}✅ PASS: Ключ найден (${#key} символов)${NC}"
    echo "   Маскированный ключ: $masked"
    return 0
}

# Проверяем контейнер api
if ! check_container_key "api" "api"; then
    PASS=false
fi

echo ""

# Проверяем контейнер worker
if ! check_container_key "worker" "worker"; then
    PASS=false
fi

echo ""

# Итоговый результат
if [ "$PASS" = true ]; then
    echo -e "${GREEN}✅ Все проверки пройдены${NC}"
    exit 0
else
    echo -e "${RED}❌ Некоторые проверки не пройдены${NC}"
    echo ""
    echo "Рекомендации:"
    echo "1. Убедитесь, что файл .env существует и содержит YOUTUBE_API_KEY"
    echo "2. Проверьте, что docker-compose.yml правильно прокидывает переменные"
    echo "3. Перезапустите контейнеры: docker compose restart api worker"
    exit 1
fi
