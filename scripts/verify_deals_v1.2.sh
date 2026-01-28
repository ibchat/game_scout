#!/bin/bash
# Проверка Deals / Publisher Intent v1.2
# Проверяет русификацию, разнообразие scoring, и глубину breakdown

set -e

API_URL="${API_URL:-http://localhost:8000/api/v1}"

echo "=== Проверка Deals v1.2 ==="
echo ""

PASS=true

# G1. Проверка API списка
echo "G1. Проверка API списка..."
LIST_RESPONSE=$(curl -sS "${API_URL}/deals/list?limit=50")
METRICS=$(echo "$LIST_RESPONSE" | jq '{
  count: .count,
  has_snake_case_reasons: ([.games[] | .. | strings | select(test("no_publisher_on_steam|positive_ratio_|stage_|has_|reviews_30d_|known_publisher|old_release"))] | length),
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

if [ "$INTENT_RU_PRESENT" -eq 0 ]; then
  echo "❌ FAIL: intent_ru_present = 0 (должно быть > 0)"
  PASS=false
else
  echo "✅ PASS: intent_ru_present = $INTENT_RU_PRESENT"
fi

if [ "$QUALITY_RU_PRESENT" -eq 0 ]; then
  echo "❌ FAIL: quality_ru_present = 0 (должно быть > 0)"
  PASS=false
else
  echo "✅ PASS: quality_ru_present = $QUALITY_RU_PRESENT"
fi

echo ""

# G2. Проверка detail endpoint
echo "G2. Проверка detail endpoint..."
APP_ID=$(echo "$LIST_RESPONSE" | jq -r '.games[0].app_id // empty')
if [ -z "$APP_ID" ]; then
  echo "⚠️  Нет игр в списке, пропускаем проверку detail"
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

echo ""
if [ "$PASS" = true ]; then
  echo "=== ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ==="
  exit 0
else
  echo "=== ❌ ЕСТЬ ОШИБКИ ==="
  exit 1
fi
