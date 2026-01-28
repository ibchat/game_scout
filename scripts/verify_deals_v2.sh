#!/bin/bash
# Проверка Deals / Publisher Intent v2.0
# Проверяет русификацию, разнообразие scoring, глубину breakdown, и Gate v2

set -e

API_URL="${API_URL:-http://localhost:8000/api/v1}"

echo "=== Проверка Deals v2.0 ==="
echo ""

PASS=true

# G1. Проверка API списка
echo "G1. Проверка API списка..."
LIST_RESPONSE=$(curl -sS "${API_URL}/deals/list?limit=50")

# Guard: проверяем что ответ валидный JSON и содержит .games
if ! echo "$LIST_RESPONSE" | jq empty 2>/dev/null; then
  echo "❌ FAIL: API вернул невалидный JSON"
  echo "Ответ:"
  echo "$LIST_RESPONSE" | head -c 1000
  exit 1
fi

GAMES_CHECK=$(echo "$LIST_RESPONSE" | jq -r '.games // empty')
if [ -z "$GAMES_CHECK" ] || [ "$GAMES_CHECK" = "null" ]; then
  echo "❌ FAIL: API ответ не содержит .games"
  echo "Структура ответа:"
  echo "$LIST_RESPONSE" | jq 'keys'
  echo "Полный ответ:"
  echo "$LIST_RESPONSE" | head -c 2000
  exit 1
fi

METRICS=$(echo "$LIST_RESPONSE" | jq '{
  count: .count,
  has_snake_case_reasons: ([.games[] | .. | strings | select(test("no_publisher_on_steam|positive_ratio_|stage_|has_|reviews_30d_|known_publisher|old_release|self_published|has_publisher|no_demo|no_contacts|zero_reviews|very_few_reviews"))] | length),
  intent_unique: ([.games[].intent_score] | unique | length),
  quality_unique: ([.games[].quality_score] | unique | length),
  intent_ru_present: ([.games[] | select((.intent_reasons_ru|length) > 0)] | length),
  quality_ru_present: ([.games[] | select((.quality_reasons_ru|length) > 0)] | length)
}')

echo "$METRICS" | jq '.'

# Проверки
SNAKE_CASE_COUNT=$(echo "$METRICS" | jq -r '.has_snake_case_reasons')
INTENT_UNIQUE=$(echo "$METRICS" | jq -r '.intent_unique')
QUALITY_UNIQUE=$(echo "$METRICS" | jq -r '.quality_unique')
INTENT_RU_PRESENT=$(echo "$METRICS" | jq -r '.intent_ru_present')
QUALITY_RU_PRESENT=$(echo "$METRICS" | jq -r '.quality_ru_present')
COUNT=$(echo "$METRICS" | jq -r '.count')

echo ""
echo "Проверки списка:"
if [ "$SNAKE_CASE_COUNT" -gt 0 ]; then
  echo "❌ FAIL: has_snake_case_reasons = $SNAKE_CASE_COUNT (должно быть 0)"
  PASS=false
else
  echo "✅ PASS: has_snake_case_reasons = 0"
fi

if [ "$INTENT_UNIQUE" -lt 5 ]; then
  echo "❌ FAIL: intent_unique = $INTENT_UNIQUE (должно быть >= 5)"
  PASS=false
else
  echo "✅ PASS: intent_unique = $INTENT_UNIQUE"
fi

if [ "$QUALITY_UNIQUE" -lt 5 ]; then
  echo "❌ FAIL: quality_unique = $QUALITY_UNIQUE (должно быть >= 5)"
  PASS=false
else
  echo "✅ PASS: quality_unique = $QUALITY_UNIQUE"
fi

if [ "$INTENT_RU_PRESENT" -eq 0 ] || [ "$INTENT_RU_PRESENT" -lt "$COUNT" ]; then
  echo "❌ FAIL: intent_ru_present = $INTENT_RU_PRESENT (должно быть == count=$COUNT)"
  PASS=false
else
  echo "✅ PASS: intent_ru_present = $INTENT_RU_PRESENT (== count)"
fi

if [ "$QUALITY_RU_PRESENT" -eq 0 ] || [ "$QUALITY_RU_PRESENT" -lt "$COUNT" ]; then
  echo "❌ FAIL: quality_ru_present = $QUALITY_RU_PRESENT (должно быть == count=$COUNT)"
  PASS=false
else
  echo "✅ PASS: quality_ru_present = $QUALITY_RU_PRESENT (== count)"
fi

echo ""

# G2. Проверка detail endpoint
echo "G2. Проверка detail endpoint..."
GAMES_COUNT=$(echo "$LIST_RESPONSE" | jq -r '(.games | length) // 0')
if [ "$GAMES_COUNT" -eq 0 ]; then
  echo "⚠️  Нет игр в списке (games.length = 0), пропускаем проверку detail"
  PASS=false
else
  APP_ID=$(echo "$LIST_RESPONSE" | jq -r '.games[0].app_id // empty')
  if [ -z "$APP_ID" ]; then
    echo "⚠️  Первая игра не имеет app_id, пропускаем проверку detail"
    PASS=false
  else
  echo "Используем app_id: $APP_ID"
  DETAIL_RESPONSE=$(curl -sS "${API_URL}/deals/${APP_ID}/detail")
  DETAIL_METRICS=$(echo "$DETAIL_RESPONSE" | jq '{
    app_id: .app_id,
    intent_breakdown_len: (.intent_breakdown | length),
    quality_breakdown_len: (.quality_breakdown | length),
    intent_breakdown_has_snake_case: ([.intent_breakdown[] | select(.label | test("^[a-z_]+$"))] | length),
    quality_breakdown_has_snake_case: ([.quality_breakdown[] | select(.label | test("^[a-z_]+$"))] | length)
  }')
  
  echo "$DETAIL_METRICS" | jq '.'
  
  INTENT_BREAKDOWN_LEN=$(echo "$DETAIL_METRICS" | jq -r '.intent_breakdown_len')
  QUALITY_BREAKDOWN_LEN=$(echo "$DETAIL_METRICS" | jq -r '.quality_breakdown_len')
  INTENT_BREAKDOWN_SNAKE=$(echo "$DETAIL_METRICS" | jq -r '.intent_breakdown_has_snake_case')
  QUALITY_BREAKDOWN_SNAKE=$(echo "$DETAIL_METRICS" | jq -r '.quality_breakdown_has_snake_case')
  
  echo ""
  echo "Проверки detail:"
  if [ "$INTENT_BREAKDOWN_LEN" -lt 4 ]; then
    echo "❌ FAIL: intent_breakdown_len = $INTENT_BREAKDOWN_LEN (должно быть >= 4)"
    PASS=false
  else
    echo "✅ PASS: intent_breakdown_len = $INTENT_BREAKDOWN_LEN"
  fi
  
  if [ "$QUALITY_BREAKDOWN_LEN" -lt 4 ]; then
    echo "❌ FAIL: quality_breakdown_len = $QUALITY_BREAKDOWN_LEN (должно быть >= 4)"
    PASS=false
  else
    echo "✅ PASS: quality_breakdown_len = $QUALITY_BREAKDOWN_LEN"
  fi
  
  if [ "$INTENT_BREAKDOWN_SNAKE" -gt 0 ] || [ "$QUALITY_BREAKDOWN_SNAKE" -gt 0 ]; then
    echo "❌ FAIL: Обнаружены snake_case в breakdown labels"
    PASS=false
  else
    echo "✅ PASS: Нет snake_case в breakdown labels"
  fi
  fi
fi

echo ""

# G3. Проверка Gate v2 (новизна + анти-успех)
echo "G3. Проверка Gate v2..."
if [ "$GAMES_COUNT" -eq 0 ]; then
  echo "⚠️  Нет игр в списке, пропускаем проверку Gate v2"
else
  GATE_METRICS=$(echo "$LIST_RESPONSE" | jq '{
    old_games: ([.games[] | select(.release_date != null and (.release_date | split("-")[0] | tonumber) < (now|strftime("%Y")|tonumber)-2)] | length),
    already_successful: ([.games[] | select((.recent_reviews_30d >= 200) or (.all_reviews_count >= 2000) or ((.positive_ratio >= 0.9) and (.all_reviews_count >= 1000)))] | length)
  }')

  echo "$GATE_METRICS" | jq '.'

  OLD_GAMES=$(echo "$GATE_METRICS" | jq -r '.old_games')
  ALREADY_SUCCESSFUL=$(echo "$GATE_METRICS" | jq -r '.already_successful')

  if [ "$OLD_GAMES" -gt 0 ]; then
    echo "⚠️  WARN: old_games = $OLD_GAMES (игры старше 2 лет)"
    # Не fail, так как Gate v2 использует 12 месяцев, но проверяем на 2 года
  fi

  if [ "$ALREADY_SUCCESSFUL" -gt 0 ]; then
    echo "❌ FAIL: already_successful = $ALREADY_SUCCESSFUL (должно быть 0)"
    PASS=false
  else
    echo "✅ PASS: already_successful = 0"
  fi
fi

echo ""
if [ "$PASS" = true ]; then
  echo "=== ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ==="
  exit 0
else
  echo "=== ❌ ЕСТЬ ОШИБКИ ==="
  exit 1
fi
