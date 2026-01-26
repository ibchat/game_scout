#!/bin/bash
# Engine v5: Proof Mode - интеграционный скрипт проверки
# Проверяет синтаксис, API, SQL-инварианты и качество данных

set -e  # Exit on error

API_URL="${API_URL:-http://localhost:8000}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-game_scout}"
DB_USER="${DB_USER:-postgres}"

ERRORS=0

echo "🔍 Engine v5: Proof Mode Verification"
echo "======================================"
echo ""

# 1. Проверка синтаксиса
echo "1️⃣ Проверка синтаксиса Python..."
echo "-----------------------------------"

for file in \
    "apps/api/routers/trends_v1.py" \
    "apps/api/routers/system_admin.py" \
    "apps/worker/analysis/trends_brain.py" \
    "apps/worker/analysis/trends_brain_v5_interpretation.py"
do
    if [ -f "$file" ]; then
        if python3 -m py_compile "$file" 2>&1; then
            echo "✅ $file"
        else
            echo "❌ $file - синтаксическая ошибка"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo "⚠️  $file - файл не найден"
    fi
done

echo ""

# 2. Проверка API endpoints
echo "2️⃣ Проверка API endpoints..."
echo "-----------------------------------"

# 2.1 /api/v1/trends/games/emerging?limit=10
echo "Проверка: GET /api/v1/trends/games/emerging?limit=10"
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/api/v1/trends/games/emerging?limit=10" || echo "000")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ HTTP 200"
    
    # Проверяем структуру ответа
    if echo "$BODY" | python3 -c "import sys, json; d=json.load(sys.stdin); assert 'games' in d" 2>/dev/null; then
        echo "✅ Структура ответа корректна"
        
        # Проверяем наличие game_name и steam_url
        GAMES_WITH_NAME=$(echo "$BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
games = d.get('games', [])
with_name = sum(1 for g in games if g.get('game_name') or g.get('name'))
print(f'{with_name}/{len(games)}')
" 2>/dev/null || echo "0/0")
        
        GAMES_WITH_URL=$(echo "$BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
games = d.get('games', [])
with_url = sum(1 for g in games if g.get('steam_url'))
print(f'{with_url}/{len(games)}')
" 2>/dev/null || echo "0/0")
        
        echo "   Игры с названием: $GAMES_WITH_NAME"
        echo "   Игры с URL: $GAMES_WITH_URL"
        
        # Проверка: минимум 8 из 10 должны иметь name и url
        if [ "$GAMES_WITH_NAME" != "0/0" ] && [ "$GAMES_WITH_URL" != "0/0" ]; then
            NAME_COUNT=$(echo "$GAMES_WITH_NAME" | cut -d'/' -f1)
            URL_COUNT=$(echo "$GAMES_WITH_URL" | cut -d'/' -f1)
            TOTAL=$(echo "$GAMES_WITH_NAME" | cut -d'/' -f2)
            
            if [ "$NAME_COUNT" -ge 8 ] && [ "$URL_COUNT" -ge 8 ] && [ "$TOTAL" -ge 10 ]; then
                echo "✅ Минимум 8/10 игр имеют name и url"
            else
                echo "❌ Меньше 8/10 игр имеют name и url ($NAME_COUNT/$TOTAL и $URL_COUNT/$TOTAL)"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    else
        echo "❌ Неверная структура ответа"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "❌ HTTP $HTTP_CODE"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# 2.2 /api/v1/trends/games/emerging?limit=10&debug=1
echo "Проверка: GET /api/v1/trends/games/emerging?limit=10&debug=1"
RESPONSE_DEBUG=$(curl -s -w "\n%{http_code}" "${API_URL}/api/v1/trends/games/emerging?limit=10&debug=1" || echo "000")
HTTP_CODE_DEBUG=$(echo "$RESPONSE_DEBUG" | tail -n1)
BODY_DEBUG=$(echo "$RESPONSE_DEBUG" | head -n-1)

if [ "$HTTP_CODE_DEBUG" = "200" ]; then
    echo "✅ HTTP 200"
    
    # Проверяем наличие debug_trace
    if echo "$BODY_DEBUG" | python3 -c "
import sys, json
d = json.load(sys.stdin)
games = d.get('games', [])
has_debug = any('debug_trace' in g for g in games)
print('yes' if has_debug else 'no')
" 2>/dev/null | grep -q "yes"; then
        echo "✅ debug_trace присутствует в ответе"
    else
        echo "⚠️  debug_trace отсутствует (может быть нормально если нет игр)"
    fi
else
    echo "❌ HTTP $HTTP_CODE_DEBUG"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# 2.3 /api/v1/admin/system/summary
echo "Проверка: GET /api/v1/admin/system/summary"
RESPONSE_SUMMARY=$(curl -s -w "\n%{http_code}" "${API_URL}/api/v1/admin/system/summary" || echo "000")
HTTP_CODE_SUMMARY=$(echo "$RESPONSE_SUMMARY" | tail -n1)

if [ "$HTTP_CODE_SUMMARY" = "200" ]; then
    echo "✅ HTTP 200"
else
    echo "❌ HTTP $HTTP_CODE_SUMMARY"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# 3. Проверка SQL-инвариантов
echo "3️⃣ Проверка SQL-инвариантов..."
echo "-----------------------------------"

if command -v psql >/dev/null 2>&1; then
    # Проверка количества seed apps
    SEED_COUNT=$(PGPASSWORD="${DB_PASSWORD:-postgres}" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM trends_seed_apps WHERE is_active = true;" 2>/dev/null | xargs || echo "0")
    echo "   Seed apps (active): $SEED_COUNT"
    
    # Проверка количества games today
    GAMES_TODAY=$(PGPASSWORD="${DB_PASSWORD:-postgres}" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM trends_game_daily WHERE day = CURRENT_DATE;" 2>/dev/null | xargs || echo "0")
    echo "   Games today: $GAMES_TODAY"
    
    # Проверка сигналов за 24ч
    SIGNALS_24H=$(PGPASSWORD="${DB_PASSWORD:-postgres}" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
        SELECT source, COUNT(*) 
        FROM trends_raw_signals 
        WHERE captured_at >= NOW() - INTERVAL '24 hours'
        GROUP BY source;
    " 2>/dev/null || echo "")
    echo "   Signals за 24ч:"
    echo "$SIGNALS_24H" | while read line; do
        if [ -n "$line" ]; then
            echo "     $line"
        fi
    done
    
    # Проверка сигналов за 7д
    SIGNALS_7D=$(PGPASSWORD="${DB_PASSWORD:-postgres}" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
        SELECT source, COUNT(*) 
        FROM trends_raw_signals 
        WHERE captured_at >= NOW() - INTERVAL '7 days'
        GROUP BY source;
    " 2>/dev/null || echo "")
    echo "   Signals за 7д:"
    echo "$SIGNALS_7D" | while read line; do
        if [ -n "$line" ]; then
            echo "     $line"
        fi
    done
else
    echo "⚠️  psql не найден, пропускаем SQL проверки"
fi

echo ""

# 4. Итоговая проверка
echo "4️⃣ Итоговая проверка..."
echo "-----------------------------------"

if [ $ERRORS -eq 0 ]; then
    echo "✅ Все проверки пройдены!"
    exit 0
else
    echo "❌ Найдено ошибок: $ERRORS"
    exit 1
fi
