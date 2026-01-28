#!/bin/bash
# Operations check script для проверки состояния системы
# Проверяет health, docs, отсутствие файлов со скобками в корне

set -e

echo "🔍 Operations check: проверка состояния системы..."
echo ""

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=true

# 1. Проверка health endpoint
echo "1. Проверка API health..."
HTTP_CODE=$(curl -4 -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/v1/health" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ PASS: API отвечает (HTTP $HTTP_CODE)${NC}"
else
    echo -e "${RED}❌ FAIL: API не отвечает (HTTP $HTTP_CODE)${NC}"
    PASS=false
fi

echo ""

# 2. Проверка docs-файлов
echo "2. Проверка канонических документов..."
REQUIRED_DOCS=(
    "docs/CURSOR_PROTOCOL.md"
    "docs/PLATFORM_THESIS.md"
    "docs/ANTI_PATTERNS.md"
)

for doc in "${REQUIRED_DOCS[@]}"; do
    if [ -f "$doc" ]; then
        echo -e "${GREEN}✅ PASS: $doc существует${NC}"
    else
        echo -e "${RED}❌ FAIL: $doc отсутствует${NC}"
        PASS=false
    fi
done

echo ""

# 3. Проверка отсутствия файлов со скобками в корне
echo "3. Проверка отсутствия файлов со скобками в корне..."
FILES_WITH_PARENS=$(ls -1 | grep -E "\(|\)" 2>/dev/null || true)

if [ -z "$FILES_WITH_PARENS" ]; then
    echo -e "${GREEN}✅ PASS: Нет файлов со скобками в корне${NC}"
else
    echo -e "${RED}❌ FAIL: Найдены файлы со скобками:${NC}"
    echo "$FILES_WITH_PARENS" | while read -r file; do
        echo "   - $file"
    done
    PASS=false
fi

echo ""

# 4. Проверка README.md
echo "4. Проверка README.md..."
if [ -f "README.md" ]; then
    if grep -q "Документация (канон)" README.md && grep -q "docker compose up" README.md; then
        echo -e "${GREEN}✅ PASS: README.md содержит необходимые блоки${NC}"
    else
        echo -e "${YELLOW}⚠️  WARN: README.md может быть неполным${NC}"
    fi
else
    echo -e "${RED}❌ FAIL: README.md отсутствует${NC}"
    PASS=false
fi

echo ""

# Итоговый результат
if [ "$PASS" = true ]; then
    echo -e "${GREEN}✅ Все проверки пройдены${NC}"
    exit 0
else
    echo -e "${RED}❌ Некоторые проверки не пройдены${NC}"
    exit 1
fi
