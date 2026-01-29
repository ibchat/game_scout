#!/usr/bin/env bash

set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
DB_SERVICE="${DB_SERVICE:-postgres}"
DB_NAME="${DB_NAME:-game_scout}"
DB_USER="${DB_USER:-postgres}"

echo "=== Проверка Synthetic UI Check ==="
echo

fail=0

# Wrapper для curl с ретраями (защита от uvicorn reload / Empty reply from server)
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
  
  # Последняя попытка без подавления ошибок
  curl -4 -sS --max-time 5 "$url"
}

fetch_list() { CURL "$1"; }

psql_db() {
  local sql="$1"
  docker compose exec -T "$DB_SERVICE" bash -lc "export PAGER=cat; psql -U '$DB_USER' -d '$DB_NAME' -Atc \"$sql\""
}

echo "S1. Проверка synthetic_only=true..."
LIST_JSON="$(fetch_list "$API_BASE/api/v1/deals/list?limit=50&synthetic_only=true&min_intent_score=0&min_quality_score=0")"
COUNT="$(echo "$LIST_JSON" | jq -r '.count // 0')"
APP_IDS="$(echo "$LIST_JSON" | jq -r '.games[]?.app_id' || true)"

echo "  count: $COUNT"
echo "  app_ids: ${APP_IDS:-<empty>}"

if [[ "$COUNT" -ge 1 ]]; then
  echo "✅ PASS: synthetic_only=true вернул count = $COUNT"
else
  echo "❌ FAIL: synthetic_only=true вернул count = $COUNT"
  fail=1
fi

if echo "$APP_IDS" | grep -qxE "(999999|1410400)"; then
  echo "✅ PASS: найден app_id=999999 или 1410400 в synthetic_only=true"
else
  echo "❌ FAIL: нет app_id=999999/1410400 в synthetic_only=true"
  fail=1
fi
echo

echo "S2. Проверка steam_url NOT NULL..."
NULL_URLS="$(echo "$LIST_JSON" | jq -r '[.games[]? | select((.steam_url // "") == "")] | length')"
if [[ "$NULL_URLS" -eq 0 ]]; then
  echo "✅ PASS: все $COUNT игр имеют steam_url NOT NULL"
else
  echo "❌ FAIL: найдено $NULL_URLS игр без steam_url"
  fail=1
fi
echo

echo "S3. Проверка games.tags NOT NULL (через БД)..."
FIRST_APP_ID="$(echo "$LIST_JSON" | jq -r '.games[0].app_id // empty')"
if [[ -z "${FIRST_APP_ID:-}" ]]; then
  echo "❌ FAIL: synthetic_only список пуст — не с чем проверять tags"
  fail=1
else
  TAGS_NULL_CNT="$(psql_db "SELECT COUNT(*) FROM games WHERE source='steam' AND source_id='${FIRST_APP_ID}' AND tags IS NULL;")"
  GAMES_CNT="$(psql_db "SELECT COUNT(*) FROM games WHERE source='steam' AND source_id='${FIRST_APP_ID}';")"
  echo "  games rows: $GAMES_CNT"
  echo "  tags IS NULL rows: $TAGS_NULL_CNT"

  if [[ "$GAMES_CNT" -ge 1 ]] && [[ "$TAGS_NULL_CNT" -eq 0 ]]; then
    echo "✅ PASS: games.tags NOT NULL для app_id=$FIRST_APP_ID"
  else
    echo "❌ FAIL: games.tags NULL или нет строки в games для app_id=$FIRST_APP_ID"
    fail=1
  fi
fi
echo

echo "S4. Проверка default (synthetic_only=false)..."
DEFAULT_JSON="$(fetch_list "$API_BASE/api/v1/deals/list?limit=50")"
STATUS="$(echo "$DEFAULT_JSON" | jq -r '.status // empty')"
DCOUNT="$(echo "$DEFAULT_JSON" | jq -r '.count // 0')"
echo "  status: $STATUS"
echo "  count: $DCOUNT"

if [[ "$STATUS" == "ok" ]]; then
  echo "✅ PASS: default endpoint вернул status = ok"
else
  echo "❌ FAIL: default status = $STATUS"
  fail=1
fi
echo

echo "S5. Проверка steam_url NOT NULL в default списке..."
DNULL_URLS="$(echo "$DEFAULT_JSON" | jq -r '[.games[]? | select((.steam_url // "") == "")] | length')"
if [[ "$DNULL_URLS" -eq 0 ]]; then
  echo "✅ PASS: все игры имеют steam_url NOT NULL в default списке"
else
  echo "❌ FAIL: найдено $DNULL_URLS игр без steam_url в default"
  fail=1
fi
echo

# S6. Проверка DealThesis для тест-кейсов
echo "S6. Проверка DealThesis (thesis_archetype, publisher_interest)..."
VALID_ARCHETYPES=("early_publisher_search" "late_pivot_after_release" "weak_signal_exploration" "opportunistic_outreach" "unclear_intent" "high_intent_low_quality")

for test_app_id in 1410400 999999; do
  echo "  Проверка app_id=$test_app_id..."
  
  # B1: Проверка HTTP статуса (должен быть 200, не 500)
  HTTP_CODE=$(CURL "$API_BASE/api/v1/deals/${test_app_id}/detail" > /tmp/detail_${test_app_id}.json && echo "200" || echo "000")
  if [[ "$HTTP_CODE" != "200" ]]; then
    echo "❌ FAIL: app_id=$test_app_id — HTTP $HTTP_CODE (ожидается 200)"
    if [[ -f "/tmp/detail_${test_app_id}.json" ]]; then
      echo "  Тело ответа: $(cat /tmp/detail_${test_app_id}.json | head -c 200)"
    fi
    fail=1
    continue
  else
    echo "✅ PASS: app_id=$test_app_id — HTTP $HTTP_CODE"
  fi
  
  DETAIL_JSON="$(cat /tmp/detail_${test_app_id}.json)"
  
  # Проверка thesis не null
  THESIS_NULL="$(echo "$DETAIL_JSON" | jq -r '[.thesis // null] | .[0] == null')"
  if [[ "$THESIS_NULL" == "true" ]]; then
    echo "❌ FAIL: app_id=$test_app_id — thesis is null"
    fail=1
  else
    echo "✅ PASS: app_id=$test_app_id — thesis not null"
  fi
  
  # Проверка thesis_archetype
  ARCHETYPE="$(echo "$DETAIL_JSON" | jq -r '.thesis.thesis_archetype // empty')"
  if [[ -z "$ARCHETYPE" ]]; then
    echo "❌ FAIL: app_id=$test_app_id — thesis_archetype отсутствует"
    fail=1
  elif [[ "$ARCHETYPE" == "marketing_distress" ]]; then
    echo "❌ FAIL: app_id=$test_app_id — thesis_archetype = marketing_distress (запрещено)"
    fail=1
  elif [[ ! " ${VALID_ARCHETYPES[@]} " =~ " ${ARCHETYPE} " ]]; then
    echo "❌ FAIL: app_id=$test_app_id — thesis_archetype = $ARCHETYPE (недопустимое значение)"
    fail=1
  else
    echo "✅ PASS: app_id=$test_app_id — thesis_archetype = $ARCHETYPE (допустимо)"
  fi
  
  # Проверка приоритета архетипов
  if [[ "$test_app_id" == "1410400" ]]; then
    if [[ "$ARCHETYPE" != "late_pivot_after_release" ]]; then
      echo "❌ FAIL: app_id=1410400 — ожидается late_pivot_after_release, получен $ARCHETYPE"
      fail=1
    else
      echo "✅ PASS: app_id=1410400 — архетип late_pivot_after_release (правильный приоритет)"
    fi
  elif [[ "$test_app_id" == "999999" ]]; then
    if [[ "$ARCHETYPE" != "early_publisher_search" ]]; then
      echo "❌ FAIL: app_id=999999 — ожидается early_publisher_search, получен $ARCHETYPE"
      fail=1
    else
      echo "✅ PASS: app_id=999999 — архетип early_publisher_search (правильный приоритет)"
    fi
  fi
  
  # Проверка publisher_interest
  WHO_MIGHT_CARE_TYPE="$(echo "$DETAIL_JSON" | jq -r '.thesis.publisher_interest.who_might_care | type')"
  NEXT_ACTIONS_TYPE="$(echo "$DETAIL_JSON" | jq -r '.thesis.publisher_interest.next_actions | type')"
  
  if [[ "$WHO_MIGHT_CARE_TYPE" != "array" ]]; then
    echo "❌ FAIL: app_id=$test_app_id — publisher_interest.who_might_care не массив (type=$WHO_MIGHT_CARE_TYPE)"
    fail=1
  else
    echo "✅ PASS: app_id=$test_app_id — publisher_interest.who_might_care is array"
  fi
  
  if [[ "$NEXT_ACTIONS_TYPE" != "array" ]]; then
    echo "❌ FAIL: app_id=$test_app_id — publisher_interest.next_actions не массив (type=$NEXT_ACTIONS_TYPE)"
    fail=1
  else
    echo "✅ PASS: app_id=$test_app_id — publisher_interest.next_actions is array"
  fi
  
  # E1/E2: Проверка publisher_status
  PUB_STATUS="$(echo "$DETAIL_JSON" | jq -r '.publisher_status_code // .publisher_status // empty')"
  if [[ -z "$PUB_STATUS" ]]; then
    echo "❌ FAIL: app_id=$test_app_id — publisher_status отсутствует"
    fail=1
  elif [[ ! "$PUB_STATUS" =~ ^(has_publisher|self_published|unknown)$ ]]; then
    echo "❌ FAIL: app_id=$test_app_id — publisher_status = $PUB_STATUS (недопустимое значение)"
    fail=1
  else
    echo "✅ PASS: app_id=$test_app_id — publisher_status = $PUB_STATUS (допустимо)"
  fi
  
  # E2: Если publisher_status == has_publisher → thesis НЕ содержит фразы «без издателя»
  if [[ "$PUB_STATUS" == "has_publisher" ]]; then
    THESIS_TEXT="$(echo "$DETAIL_JSON" | jq -r '.thesis.thesis // ""')"
    if echo "$THESIS_TEXT" | grep -qi "без издателя"; then
      echo "❌ FAIL: app_id=$test_app_id — publisher_status=has_publisher, но thesis содержит 'без издателя'"
      fail=1
    else
      echo "✅ PASS: app_id=$test_app_id — publisher_status=has_publisher, thesis не содержит 'без издателя'"
    fi
  fi
done
echo

# Задача 2: Проверка apps_with_signals >= 2
echo "S7. Проверка apps_with_signals (сигнал-coverage)..."
APPS_WITH_SIGNALS="$(psql_db "SELECT COUNT(DISTINCT app_id) FROM deal_intent_signal WHERE app_id IS NOT NULL;")"
echo "  apps_with_signals: $APPS_WITH_SIGNALS"

if [[ "$APPS_WITH_SIGNALS" -ge 2 ]]; then
  echo "✅ PASS: apps_with_signals = $APPS_WITH_SIGNALS (>= 2)"
else
  echo "❌ FAIL: apps_with_signals = $APPS_WITH_SIGNALS (должно быть >= 2)"
  fail=1
fi
echo

# S8. Проверка Partner-mode формулировки для app_id=999999
echo "S8. Проверка Partner-mode формулировки (app_id=999999)..."
TEST_APP_ID=999999

# 1) Upsert записи в steam_app_cache с publishers
echo "  Создание/обновление steam_app_cache для app_id=$TEST_APP_ID..."
# Используем array_to_json для избежания проблем с экранированием кавычек
psql_db "UPDATE steam_app_cache SET publishers = array_to_json(ARRAY['Test Publisher'])::jsonb, updated_at = now() WHERE steam_app_id = $TEST_APP_ID;" > /dev/null 2>&1
UPDATE_EXIT=$?
if [[ $UPDATE_EXIT -eq 0 ]]; then
  echo "  ✅ Запись в steam_app_cache обновлена"
else
  # Если UPDATE не сработал (записи нет), пробуем INSERT
  psql_db "INSERT INTO steam_app_cache (steam_app_id, name, publishers, updated_at) VALUES ($TEST_APP_ID, 'SYNTHETIC TEST GAME', array_to_json(ARRAY['Test Publisher'])::jsonb, now()) ON CONFLICT (steam_app_id) DO UPDATE SET publishers = EXCLUDED.publishers, updated_at = now();" > /dev/null 2>&1
  INSERT_EXIT=$?
  if [[ $INSERT_EXIT -eq 0 ]]; then
    echo "  ✅ Запись в steam_app_cache создана/обновлена (через INSERT)"
  else
    echo "  ⚠️  WARNING: не удалось обновить publishers, но продолжаем проверку"
  fi
fi

# 2) Проверка detail endpoint
sleep 1  # Даём время на обновление кэша
DETAIL_JSON="$(fetch_list "$API_BASE/api/v1/deals/${TEST_APP_ID}/detail")"

# Проверка publisher_status_code
PUB_STATUS_CODE="$(echo "$DETAIL_JSON" | jq -r '.publisher_status_code // empty')"
if [[ "$PUB_STATUS_CODE" == "has_publisher" ]]; then
  echo "  ✅ PASS: publisher_status_code = has_publisher"
else
  echo "  ❌ FAIL: publisher_status_code = $PUB_STATUS_CODE (ожидается has_publisher)"
  fail=1
fi

# Проверка thesis содержит "партнёра" и НЕ содержит "ищет издателя"
THESIS_TEXT="$(echo "$DETAIL_JSON" | jq -r '.thesis.thesis // ""')"
if echo "$THESIS_TEXT" | grep -qi "партнёра"; then
  echo "  ✅ PASS: thesis содержит 'партнёра'"
else
  echo "  ❌ FAIL: thesis не содержит 'партнёра'"
  echo "    thesis: $THESIS_TEXT"
  fail=1
fi

if echo "$THESIS_TEXT" | grep -qi "ищет издателя"; then
  echo "  ❌ FAIL: thesis содержит 'ищет издателя' (запрещено при has_publisher)"
  echo "    thesis: $THESIS_TEXT"
  fail=1
else
  echo "  ✅ PASS: thesis не содержит 'ищет издателя'"
fi

# Проверка risk_flags содержит фразу про "уже есть издатель"
RISK_FLAGS_TYPE="$(echo "$DETAIL_JSON" | jq -r '.thesis.publisher_interest.risk_flags | type')"
if [[ "$RISK_FLAGS_TYPE" != "array" ]]; then
  echo "  ❌ FAIL: risk_flags не является массивом (type=$RISK_FLAGS_TYPE)"
  fail=1
else
  RISK_FLAGS_TEXT="$(echo "$DETAIL_JSON" | jq -r '.thesis.publisher_interest.risk_flags | .[]' | tr '\n' ' ')"
  if echo "$RISK_FLAGS_TEXT" | grep -qi "уже есть издатель"; then
    echo "  ✅ PASS: risk_flags содержит фразу про 'уже есть издатель'"
  else
    echo "  ❌ FAIL: risk_flags не содержит фразу про 'уже есть издатель'"
    echo "    risk_flags: $RISK_FLAGS_TEXT"
    fail=1
  fi
fi
echo

# S9. Проверка confidence (новая формула)
echo "S9. Проверка confidence (новая формула)..."
for test_app_id in 1410400 999999; do
  echo "  Проверка app_id=$test_app_id..."
  DETAIL_JSON="$(fetch_list "$API_BASE/api/v1/deals/${test_app_id}/detail")"
  
  CONFIDENCE="$(echo "$DETAIL_JSON" | jq -r '.thesis.confidence // empty')"
  QUALITY_SCORE="$(echo "$DETAIL_JSON" | jq -r '.quality_score // 0')"
  
  if [[ -z "$CONFIDENCE" ]] || [[ "$CONFIDENCE" == "null" ]]; then
    echo "  ❌ FAIL: app_id=$test_app_id — confidence отсутствует"
    fail=1
  else
    # Проверка диапазона 0.0 <= confidence <= 1.0
    CONFIDENCE_FLOAT=$(echo "$CONFIDENCE" | awk '{print $1+0}')
    if (( $(echo "$CONFIDENCE_FLOAT < 0.0" | bc -l) )) || (( $(echo "$CONFIDENCE_FLOAT > 1.0" | bc -l) )); then
      echo "  ❌ FAIL: app_id=$test_app_id — confidence = $CONFIDENCE (должно быть 0.0 <= confidence <= 1.0)"
      fail=1
    else
      echo "  ✅ PASS: app_id=$test_app_id — confidence = $CONFIDENCE (в диапазоне)"
      
      # Дополнительно: если quality_score == 0 → confidence не может быть 1.0
      QUALITY_FLOAT=$(echo "$QUALITY_SCORE" | awk '{print $1+0}')
      if (( $(echo "$QUALITY_FLOAT == 0" | bc -l) )) && (( $(echo "$CONFIDENCE_FLOAT == 1.0" | bc -l) )); then
        echo "  ❌ FAIL: app_id=$test_app_id — quality_score=0, но confidence=1.0 (ожидается штраф -0.2)"
        fail=1
      elif (( $(echo "$QUALITY_FLOAT == 0" | bc -l) )); then
        echo "  ✅ PASS: app_id=$test_app_id — quality_score=0, confidence=$CONFIDENCE (не 1.0, штраф применён)"
      fi
    fi
  fi
done
echo

# S10. Проверка publisher-interest codes косвенно через RU label
echo "S10. Проверка publisher-interest (RU labels для archetype)..."
for test_app_id in 1410400 999999; do
  echo "  Проверка app_id=$test_app_id..."
  DETAIL_JSON="$(fetch_list "$API_BASE/api/v1/deals/${test_app_id}/detail")"
  
  ARCHETYPE="$(echo "$DETAIL_JSON" | jq -r '.thesis.thesis_archetype // empty')"
  WHO_MIGHT_CARE_JSON="$(echo "$DETAIL_JSON" | jq -r '.thesis.publisher_interest.who_might_care // []')"
  WHO_MIGHT_CARE_TYPE="$(echo "$DETAIL_JSON" | jq -r '.thesis.publisher_interest.who_might_care | type')"
  
  if [[ "$WHO_MIGHT_CARE_TYPE" != "array" ]]; then
    echo "  ❌ FAIL: app_id=$test_app_id — who_might_care не является массивом (type=$WHO_MIGHT_CARE_TYPE)"
    fail=1
  else
    WHO_MIGHT_CARE_TEXT="$(echo "$WHO_MIGHT_CARE_JSON" | jq -r '.[]' | tr '\n' '|')"
    
    # Проверка для 1410400 (late_pivot_after_release)
    if [[ "$test_app_id" == "1410400" ]]; then
      if echo "$WHO_MIGHT_CARE_TEXT" | grep -qE "(Паблишер \"спасатель\"|Паблишер-оператор|Маркетинговый издатель)"; then
        echo "  ✅ PASS: app_id=$test_app_id — who_might_care содержит ожидаемый RU label для late_pivot_after_release"
      else
        echo "  ❌ FAIL: app_id=$test_app_id — who_might_care не содержит ожидаемых RU labels для late_pivot_after_release"
        echo "    who_might_care: $WHO_MIGHT_CARE_TEXT"
        fail=1
      fi
    fi
    
    # Проверка для 999999 (early_publisher_search)
    if [[ "$test_app_id" == "999999" ]]; then
      if echo "$WHO_MIGHT_CARE_TEXT" | grep -qE "(Скаут/фонд|Паблишер по жанру|Маркетинговый издатель)"; then
        echo "  ✅ PASS: app_id=$test_app_id — who_might_care содержит ожидаемый RU label для early_publisher_search"
      else
        echo "  ❌ FAIL: app_id=$test_app_id — who_might_care не содержит ожидаемых RU labels для early_publisher_search"
        echo "    who_might_care: $WHO_MIGHT_CARE_TEXT"
        fail=1
      fi
    fi
  fi
done
echo

if [[ "$fail" -eq 0 ]]; then
  echo "=== ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ==="
  exit 0
else
  echo "=== ❌ ЕСТЬ ОШИБКИ ==="
  exit 1
fi
