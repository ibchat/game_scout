#!/bin/bash
# Проверка окружения для запуска Game Scout

echo "=== Проверка окружения Game Scout ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

EXIT_CODE=0

# 1. Check Docker
echo "1. Проверка Docker..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version 2>&1)
    echo -e "   ${GREEN}✓${NC} Docker установлен: $DOCKER_VERSION"
    
    # Check if Docker daemon is running
    if docker ps &> /dev/null; then
        echo -e "   ${GREEN}✓${NC} Docker daemon запущен"
    else
        echo -e "   ${RED}✗${NC} Docker daemon не запущен"
        echo "      Запустите Docker Desktop: open /Applications/Docker.app"
        EXIT_CODE=1
    fi
else
    echo -e "   ${RED}✗${NC} Docker не установлен"
    echo "      Установите Docker Desktop: https://www.docker.com/products/docker-desktop/"
    echo "      Или через Homebrew: brew install --cask docker"
    EXIT_CODE=1
fi
echo ""

# 2. Check Docker Compose
echo "2. Проверка Docker Compose..."
if docker compose version &> /dev/null; then
    COMPOSE_VERSION=$(docker compose version 2>&1 | head -1)
    echo -e "   ${GREEN}✓${NC} Docker Compose доступен: $COMPOSE_VERSION"
else
    echo -e "   ${RED}✗${NC} Docker Compose не найден"
    EXIT_CODE=1
fi
echo ""

# 3. Check Python (optional, for local development)
echo "3. Проверка Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    echo -e "   ${GREEN}✓${NC} Python установлен: $PYTHON_VERSION"
else
    echo -e "   ${YELLOW}⚠${NC} Python не найден (не обязательно, если используете Docker)"
fi
echo ""

# 4. Check project files
echo "4. Проверка файлов проекта..."
if [ -f "docker-compose.yml" ]; then
    echo -e "   ${GREEN}✓${NC} docker-compose.yml найден"
else
    echo -e "   ${RED}✗${NC} docker-compose.yml не найден"
    EXIT_CODE=1
fi

if [ -f ".env" ]; then
    echo -e "   ${GREEN}✓${NC} .env файл найден"
else
    echo -e "   ${YELLOW}⚠${NC} .env файл не найден (может потребоваться создать из .env.example)"
fi

if [ -f "apps/api/static/game_scout_dashboard.html" ]; then
    echo -e "   ${GREEN}✓${NC} Дашборд найден"
else
    echo -e "   ${RED}✗${NC} Дашборд не найден"
    EXIT_CODE=1
fi
echo ""

# 5. Check ports
echo "5. Проверка портов..."
if lsof -i :8000 &> /dev/null; then
    echo -e "   ${YELLOW}⚠${NC} Порт 8000 занят"
    echo "      Процесс: $(lsof -i :8000 | tail -1)"
else
    echo -e "   ${GREEN}✓${NC} Порт 8000 свободен"
fi

if lsof -i :5432 &> /dev/null; then
    echo -e "   ${YELLOW}⚠${NC} Порт 5432 (PostgreSQL) занят"
else
    echo -e "   ${GREEN}✓${NC} Порт 5432 свободен"
fi

if lsof -i :6379 &> /dev/null; then
    echo -e "   ${YELLOW}⚠${NC} Порт 6379 (Redis) занят"
else
    echo -e "   ${GREEN}✓${NC} Порт 6379 свободен"
fi
echo ""

# Summary
echo "=== Итоги ==="
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ Окружение готово к запуску!${NC}"
    echo ""
    echo "Следующие шаги:"
    echo "  1. docker compose up -d"
    echo "  2. docker compose ps"
    echo "  3. open http://localhost:8000/dashboard"
else
    echo -e "${RED}✗ Окружение не готово${NC}"
    echo ""
    echo "Исправьте проблемы выше и запустите скрипт снова."
    echo ""
    echo "Инструкции по установке Docker:"
    echo "  - См. DOCKER_SETUP.md"
    echo "  - Или: https://www.docker.com/products/docker-desktop/"
fi
echo ""

exit $EXIT_CODE
