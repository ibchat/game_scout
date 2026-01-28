#!/bin/bash
# Проверка Deals / Publisher Intent v1.1
# Проверяет русификацию, breakdown, и качество данных

set -e

API_URL="${API_URL:-http://localhost:8000/api/v1}"

echo "=== Проверка Deals v1.1 ==="
echo ""

# G1. Проверка API списка
echo "G1. Проверка API списка..."
LIST_RESPONSE=$(curl -sS "${API_URL}/deals/list?limit=50")
echo "$LIST_RESPONSE" | jq '{
  count: .count,
  titles_missing: ([.games[] | select(.title == null or .title == "" )] | length),
  has_snake_case_reasons: ([.games[] | .. | strings | select(test("no_publisher_on_steam|positive_ratio_"))] | length),
  intent_unique: ([.games[].intent_score] | unique | length),
  quality_unique: ([.games[].quality_score] | unique | length),
  has_intent_reasons_ru: ([.games[] | select(.intent_reasons_ru != null)] | length),
  has_quality_reasons_ru: ([.games[] | select(.quality_reasons_ru != null)] | length)
}'

# Проверка на snake_case в reasons_ru
SNAKE_CASE_COUNT=$(echo "$LIST_RESPONSE" | jq '[.games[] | select(.intent_reasons_ru != null) | .intent_reasons_ru[] | select(test("^[a-z_]+$"))] | length')
if [ "$SNAKE_CASE_COUNT" -gt 0 ]; then
  echo "⚠️  Обнаружены snake_case в intent_reasons_ru: $SNAKE_CASE_COUNT"
else
  echo "✅ Нет snake_case в intent_reasons_ru"
fi

echo ""

# G2. Проверка detail endpoint
echo "G2. Проверка detail endpoint..."
APP_ID=$(echo "$LIST_RESPONSE" | jq -r '.games[0].app_id // empty')
if [ -z "$APP_ID" ]; then
  echo "⚠️  Нет игр в списке, пропускаем проверку detail"
else
  echo "Используем app_id: $APP_ID"
  DETAIL_RESPONSE=$(curl -sS "${API_URL}/deals/${APP_ID}/detail")
  echo "$DETAIL_RESPONSE" | jq '{
    app_id: .app_id,
    title: .title,
    intent: .intent_score,
    quality: .quality_score,
    intent_breakdown: (.intent_breakdown | length),
    quality_breakdown: (.quality_breakdown | length),
    has_why_in_deals: (.why_in_deals != null),
    has_sources: (.sources != null)
  }'
  
  # Проверка на snake_case в breakdown
  INTENT_BREAKDOWN_SNAKE=$(echo "$DETAIL_RESPONSE" | jq '[.intent_breakdown[] | select(.label_ru | test("^[a-z_]+$"))] | length')
  QUALITY_BREAKDOWN_SNAKE=$(echo "$DETAIL_RESPONSE" | jq '[.quality_breakdown[] | select(.label_ru | test("^[a-z_]+$"))] | length')
  if [ "$INTENT_BREAKDOWN_SNAKE" -gt 0 ] || [ "$QUALITY_BREAKDOWN_SNAKE" -gt 0 ]; then
    echo "⚠️  Обнаружены snake_case в breakdown labels"
  else
    echo "✅ Нет snake_case в breakdown labels"
  fi
fi

echo ""
echo "=== Проверка завершена ==="
