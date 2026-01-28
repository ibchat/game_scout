#!/bin/bash
# Проверка Deals / Publisher Intent v3.1
# Фокус: Behavioral Intent, Freshness Gate, Success Penalty, вердикты и русификация.

set -e

API_URL="${API_URL:-http://localhost:8000/api/v1}"

echo "=== Проверка Deals v3.1 ==="
echo ""

PASS=true

#
# G1. Проверка API списка
#
echo "G1. Проверка API списка..."
LIST_RESPONSE=$(curl -sS "${API_URL}/deals/list?limit=50" || echo "")

if [ -z "$LIST_RESPONSE" ]; then
  echo "❌ FAIL: Пустой ответ от API /deals/list"
  exit 1
fi

# Guard: проверяем что ответ валидный JSON
if ! echo "$LIST_RESPONSE" | jq empty 2>/dev/null; then
  echo "❌ FAIL: API вернул невалидный JSON"
  echo "Ответ:"
  echo "$LIST_RESPONSE" | head -c 1000
  exit 1
fi

# Guard: должна быть структура с games-массивом
GAMES_CHECK=$(echo "$LIST_RESPONSE" | jq -r '.games // empty')
if [ -z "$GAMES_CHECK" ] || [ "$GAMES_CHECK" = "null" ]; then
  echo "❌ FAIL: API ответ не содержит .games"
  echo "Структура ответа:"
  echo "$LIST_RESPONSE" | jq 'keys'
  echo "Полный ответ:"
  echo "$LIST_RESPONSE" | head -c 2000
  exit 1
fi

COUNT=$(echo "$LIST_RESPONSE" | jq -r '.count // 0')
if [ "$COUNT" -le 0 ]; then
  echo "❌ FAIL: count = $COUNT (должно быть > 0)"
  PASS=false
fi

#
# G2. Русификация и разнообразие
#
echo ""
echo "G2. Русификация и разнообразие..."

METRICS=$(echo "$LIST_RESPONSE" | jq '{
  count: .count,
  # snake_case в любых строках JSON (грубая эвристика)
  has_snake_case_reasons: ([.. | strings | select(test("^[a-z0-9]+(_[a-z0-9]+)+$"))] | length),
  intent_unique: ([.games[].intent_score] | unique | length),
  quality_unique: ([.games[].quality_score] | unique | length),
  # Вердикты
  verdict_values: ([.games[] | (.verdict // .verdict_label_ru // "")] | unique)
}')

echo "$METRICS" | jq '.'

SNAKE_CASE_COUNT=$(echo "$METRICS" | jq -r '.has_snake_case_reasons')
INTENT_UNIQUE=$(echo "$METRICS" | jq -r '.intent_unique')
QUALITY_UNIQUE=$(echo "$METRICS" | jq -r '.quality_unique')
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

# Проверка вердиктов
ALLOWED_VERDICTS=(
  "🟢 Активно ищет издателя"
  "🟡 Ранний запрос, требуется контакт"
  "🟠 Возможная сделка, нет явного запроса"
  "⚪ Успешный проект, не целевая сделка"
  "🔴 Нет признаков намерения"
)

BAD_VERDICTS=0
for v in $(echo "$LIST_RESPONSE" | jq -r '.games[] | (.verdict // .verdict_label_ru // "")' | sort -u); do
  [ -z "$v" ] && continue
  OK=false
  for allow in "${ALLOWED_VERDICTS[@]}"; do
    if [ "$v" = "$allow" ]; then
      OK=true
      break
    fi
  done
  if [ "$OK" = false ]; then
    echo "❌ FAIL: недопустимый verdict: \"$v\""
    BAD_VERDICTS=$((BAD_VERDICTS+1))
    PASS=false
  fi
done

if [ "$BAD_VERDICTS" -eq 0 ]; then
  echo "✅ PASS: все вердикты в допустимом списке"
fi

#
# G3. Freshness: old_games_without_behavioral
#
echo ""
echo "G3. Freshness — проверка old_games_without_behavioral..."

GAMES_JSON=$(echo "$LIST_RESPONSE" | jq '.games')
GAMES_COUNT=$(echo "$GAMES_JSON" | jq 'length')

OLD_GAMES_WO_BEHAVIORAL=0
SAMPLE_APP_ID=""

for i in $(seq 0 $((GAMES_COUNT-1))); do
  APP_ID=$(echo "$GAMES_JSON" | jq -r ".[$i].app_id")
  [ -z "$APP_ID" ] && continue

  if [ -z "$SAMPLE_APP_ID" ]; then
    SAMPLE_APP_ID="$APP_ID"
  fi

  DETAIL_RESPONSE=$(curl -sS "${API_URL}/deals/${APP_ID}/detail" || echo "")
  if ! echo "$DETAIL_RESPONSE" | jq empty 2>/dev/null; then
    echo "❌ FAIL: detail для app_id=${APP_ID} вернул невалидный JSON"
    echo "$DETAIL_RESPONSE" | head -c 800
    PASS=false
    continue
  fi

  AGE_DAYS=$(echo "$DETAIL_RESPONSE" | jq -r '.age_days // 0')
  BEHAV_LAST_DAYS=$(echo "$DETAIL_RESPONSE" | jq -r '.behavioral_last_days // empty')

  if [ "$AGE_DAYS" -gt 540 ]; then
    # Если behavioral_last_days пусто или > 60 → считаем, что нет актуального behavioral intent
    if [ -z "$BEHAV_LAST_DAYS" ] || [ "$BEHAV_LAST_DAYS" -gt 60 ]; then
      OLD_GAMES_WO_BEHAVIORAL=$((OLD_GAMES_WO_BEHAVIORAL+1))
    fi
  fi
done

echo "old_games_without_behavioral = $OLD_GAMES_WO_BEHAVIORAL"
if [ "$OLD_GAMES_WO_BEHAVIORAL" -ne 0 ]; then
  echo "❌ FAIL: old_games_without_behavioral != 0 (value=$OLD_GAMES_WO_BEHAVIORAL)"
  PASS=false
else
  echo "✅ PASS: old_games_without_behavioral = 0"
fi

#
# G4. Detail DoD для одной игры
#
echo ""
echo "G4. Проверка detail DoD для одной игры..."

if [ -z "$SAMPLE_APP_ID" ]; then
  echo "❌ FAIL: нет app_id для выборки detail"
  PASS=false
else
  echo "Используем app_id: $SAMPLE_APP_ID"
  SAMPLE_DETAIL=$(curl -sS "${API_URL}/deals/${SAMPLE_APP_ID}/detail" || echo "")

  if ! echo "$SAMPLE_DETAIL" | jq empty 2>/dev/null; then
    echo "❌ FAIL: detail для app_id=${SAMPLE_APP_ID} вернул невалидный JSON"
    echo "$SAMPLE_DETAIL" | head -c 800
    PASS=false
  else
    DETAIL_METRICS=$(echo "$SAMPLE_DETAIL" | jq '{
      app_id: .app_id,
      intent_breakdown_len: (.intent_breakdown | length),
      quality_breakdown_len: (.quality_breakdown | length),
      has_gates: has("gates"),
      has_intent_score_final: has("intent_score_final")
    }')

    echo "$DETAIL_METRICS" | jq '.'

    INTENT_BREAKDOWN_LEN=$(echo "$DETAIL_METRICS" | jq -r '.intent_breakdown_len')
    QUALITY_BREAKDOWN_LEN=$(echo "$DETAIL_METRICS" | jq -r '.quality_breakdown_len')
    HAS_GATES=$(echo "$DETAIL_METRICS" | jq -r '.has_gates')
    HAS_INTENT_FINAL=$(echo "$DETAIL_METRICS" | jq -r '.has_intent_score_final')

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

    if [ "$HAS_GATES" != "true" ]; then
      echo "❌ FAIL: detail не содержит поле gates"
      PASS=false
    else
      echo "✅ PASS: gates присутствует"
    fi

    if [ "$HAS_INTENT_FINAL" != "true" ]; then
      echo "❌ FAIL: detail не содержит intent_score_final"
      PASS=false
    else
      echo "✅ PASS: intent_score_final присутствует"
    fi
  fi
fi

echo ""
if [ "$PASS" = true ]; then
  echo "=== ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ (v3.1) ==="
  exit 0
else
  echo "=== ❌ ЕСТЬ ОШИБКИ В ПРОВЕРКАХ v3.1 ==="
  exit 1
fi

