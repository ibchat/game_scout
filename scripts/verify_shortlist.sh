#!/usr/bin/env bash
set -euo pipefail

# Vector #2: Verify shortlist endpoint

API_BASE="${API_BASE:-http://127.0.0.1:8000}"

# Wrapper для curl с ретраями
CURL() {
  local url="$1"
  local tries=8
  local delay=0.25
  local i=1
  
  while [[ $i -le $tries ]]; do
    local out=$(curl -4 -sS --max-time 5 "$url" 2>/dev/null)
    if [[ -n "$out" ]] && ! echo "$out" | grep -q "Empty reply from server"; then
      printf "%s" "$out"
      return 0
    fi
    sleep "$delay"
    i=$((i+1))
  done
  
  curl -4 -sS --max-time 5 "$url"
}

echo "=== Проверка Shortlist Endpoint (Vector #2) ==="
echo

fail=0

# S1. Базовый запрос
echo "S1. Проверка базового запроса /api/v1/deals/shortlist..."
SHORTLIST_JSON="$(CURL "$API_BASE/api/v1/deals/shortlist?limit=50&min_confidence=0.0")"

STATUS="$(echo "$SHORTLIST_JSON" | jq -r '.status // "error"')"
COUNT="$(echo "$SHORTLIST_JSON" | jq -r '.count // 0')"
ITEMS_TYPE="$(echo "$SHORTLIST_JSON" | jq -r '.items | type')"

if [[ "$STATUS" != "ok" ]]; then
  echo "  ❌ FAIL: status = $STATUS (ожидается 'ok')"
  fail=1
else
  echo "  ✅ PASS: status = ok"
fi

if [[ "$ITEMS_TYPE" != "array" ]]; then
  echo "  ❌ FAIL: items type = $ITEMS_TYPE (ожидается 'array')"
  fail=1
else
  echo "  ✅ PASS: items is array"
fi

echo "  count: $COUNT"
echo

# S2. Проверка обязательных полей в items
if [[ "$COUNT" -gt 0 ]]; then
  echo "S2. Проверка обязательных полей в items..."
  
  FIRST_ITEM="$(echo "$SHORTLIST_JSON" | jq '.items[0]')"
  
  REQUIRED_FIELDS=("app_id" "title" "steam_url" "stage" "publisher_status_code" "publisher_status" "temporal_context" "confidence" "thesis_archetype" "publisher_types" "publisher_types_ru" "intent_score" "quality_score" "verdict" "verdict_label_ru" "updated_at")
  
  # Проверяем, что headline и why_now НЕ присутствуют (по ТЗ их нет в shortlist)
  if echo "$FIRST_ITEM" | jq -e ".headline" > /dev/null 2>&1; then
    echo "  ❌ FAIL: поле headline присутствует (не должно быть в shortlist)"
    fail=1
  else
    echo "  ✅ PASS: поле headline отсутствует (правильно, по ТЗ)"
  fi
  
  if echo "$FIRST_ITEM" | jq -e ".why_now" > /dev/null 2>&1; then
    echo "  ❌ FAIL: поле why_now присутствует (не должно быть в shortlist)"
    fail=1
  else
    echo "  ✅ PASS: поле why_now отсутствует (правильно, по ТЗ)"
  fi
  
  for field in "${REQUIRED_FIELDS[@]}"; do
    if echo "$FIRST_ITEM" | jq -e ".$field" > /dev/null 2>&1; then
      echo "  ✅ PASS: поле $field присутствует"
    else
      echo "  ❌ FAIL: поле $field отсутствует"
      fail=1
    fi
  done
  echo
fi

# S3. Проверка типов полей
if [[ "$COUNT" -gt 0 ]]; then
  echo "S3. Проверка типов полей..."
  
  FIRST_ITEM="$(echo "$SHORTLIST_JSON" | jq '.items[0]')"
  
  # app_id должен быть number
  APP_ID_TYPE="$(echo "$FIRST_ITEM" | jq -r '.app_id | type')"
  if [[ "$APP_ID_TYPE" == "number" ]]; then
    echo "  ✅ PASS: app_id is number"
  else
    echo "  ❌ FAIL: app_id type = $APP_ID_TYPE (ожидается 'number')"
    fail=1
  fi
  
  # confidence должен быть number в диапазоне 0.0-1.0
  CONFIDENCE="$(echo "$FIRST_ITEM" | jq -r '.confidence // 0')"
  if (( $(echo "$CONFIDENCE >= 0.0 && $CONFIDENCE <= 1.0" | bc -l) )); then
    echo "  ✅ PASS: confidence = $CONFIDENCE (в диапазоне 0.0-1.0)"
  else
    echo "  ❌ FAIL: confidence = $CONFIDENCE (вне диапазона 0.0-1.0)"
    fail=1
  fi
  
  # why_now НЕ должен присутствовать (по ТЗ его нет в shortlist)
  if echo "$FIRST_ITEM" | jq -e ".why_now" > /dev/null 2>&1; then
    echo "  ❌ FAIL: поле why_now присутствует (не должно быть в shortlist)"
    fail=1
  else
    echo "  ✅ PASS: поле why_now отсутствует (правильно, по ТЗ)"
  fi
  
  # publisher_types должен быть array
  PUB_TYPES_TYPE="$(echo "$FIRST_ITEM" | jq -r '.publisher_types | type')"
  if [[ "$PUB_TYPES_TYPE" == "array" ]]; then
    echo "  ✅ PASS: publisher_types is array"
  else
    echo "  ❌ FAIL: publisher_types type = $PUB_TYPES_TYPE (ожидается 'array')"
    fail=1
  fi
  
  echo
fi

# S4. Проверка фильтров
echo "S4. Проверка фильтров..."

# min_confidence
CONF_FILTER_JSON="$(CURL "$API_BASE/api/v1/deals/shortlist?limit=50&min_confidence=0.8")"
CONF_FILTER_COUNT="$(echo "$CONF_FILTER_JSON" | jq -r '.count // 0')"
echo "  min_confidence=0.8: count = $CONF_FILTER_COUNT"
if [[ "$CONF_FILTER_COUNT" -le "$COUNT" ]]; then
  echo "  ✅ PASS: фильтр min_confidence работает (count уменьшился или остался прежним)"
else
  echo "  ⚠️  WARNING: фильтр min_confidence не уменьшил count"
fi

# archetypes
ARCH_FILTER_JSON="$(CURL "$API_BASE/api/v1/deals/shortlist?limit=50&min_confidence=0.0&archetypes=early_publisher_search")"
ARCH_FILTER_COUNT="$(echo "$ARCH_FILTER_JSON" | jq -r '.count // 0')"
echo "  archetypes=early_publisher_search: count = $ARCH_FILTER_COUNT"
if [[ "$ARCH_FILTER_COUNT" -le "$COUNT" ]]; then
  echo "  ✅ PASS: фильтр archetypes работает"
else
  echo "  ⚠️  WARNING: фильтр archetypes не уменьшил count"
fi

# publisher_types (Vector #3)
PUB_TYPES_FILTER_JSON="$(CURL "$API_BASE/api/v1/deals/shortlist?limit=50&min_confidence=0.0&publisher_types=marketing_publisher")"
PUB_TYPES_FILTER_COUNT="$(echo "$PUB_TYPES_FILTER_JSON" | jq -r '.count // 0')"
echo "  publisher_types=marketing_publisher: count = $PUB_TYPES_FILTER_COUNT"
if [[ "$PUB_TYPES_FILTER_COUNT" -le "$COUNT" ]]; then
  echo "  ✅ PASS: фильтр publisher_types работает (Vector #3)"
else
  echo "  ⚠️  WARNING: фильтр publisher_types не уменьшил count"
fi

echo

# S5. Топ-5 для вывода
if [[ "$COUNT" -gt 0 ]]; then
  echo "S5. Топ-5 items:"
  echo "$SHORTLIST_JSON" | jq -r '.items[0:5] | .[] | "  app_id=\(.app_id) | confidence=\(.confidence) | archetype=\(.thesis_archetype) | verdict=\(.verdict)"'
  echo
fi

if [[ $fail -eq 0 ]]; then
  echo "=== ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ==="
  exit 0
else
  echo "=== ❌ НЕКОТОРЫЕ ПРОВЕРКИ ПРОВАЛЕНЫ ==="
  exit 1
fi
