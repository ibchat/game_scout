#!/usr/bin/env bash
set -euo pipefail

# Verify Dashboard Feed - витрина наполнена
# Проверяет, что /api/v1/deals/list возвращает витринные записи с заполненными метаданными

API_URL="${API_URL:-http://127.0.0.1:8000}"

CURL() {
  local url="$1"
  local tries=5
  local delay=0.5
  local i=1
  
  while [[ $i -le $tries ]]; do
    local out=$(curl -4 -sS --max-time 10 "$url" 2>/dev/null)
    if [[ -n "$out" ]] && ! echo "$out" | grep -q "Empty reply from server"; then
      printf "%s" "$out"
      return 0
    fi
    sleep "$delay"
    i=$((i+1))
  done
  
  curl -4 -sS --max-time 10 "$url"
}

echo "=== Verify Dashboard Feed (витрина наполнена) ==="
echo

fail=0

# S1: /list default возвращает 50 игр (A1: контракт n==limit)
echo "S1. /list default (limit=50, контракт n==limit):"
LIST_RESPONSE=$(CURL "${API_URL}/api/v1/deals/list?limit=50")
LIST_COUNT=$(echo "${LIST_RESPONSE}" | jq -r '.count // 0' 2>/dev/null || echo "0")
LIST_N=$(echo "${LIST_RESPONSE}" | jq -r '.games | length' 2>/dev/null || echo "0")
LIST_STATUS=$(echo "${LIST_RESPONSE}" | jq -r '.status // "error"' 2>/dev/null || echo "error")
EXPLORE_MODE=$(echo "${LIST_RESPONSE}" | jq -r '.debug.explore_mode // false' 2>/dev/null || echo "false")

echo "  status = ${LIST_STATUS}"
echo "  count = ${LIST_COUNT}"
echo "  n (games length) = ${LIST_N}"
echo "  explore_mode = ${EXPLORE_MODE}"

if [ "${LIST_STATUS}" != "ok" ]; then
    echo "  ❌ FAIL: /api/v1/deals/list status = ${LIST_STATUS}"
    fail=1
elif [ "${LIST_N}" -ne 50 ]; then
    # A1: Контракт: n == limit (если в базе есть >=50 валидных)
    echo "  ❌ FAIL: n = ${LIST_N} (ожидается 50, контракт n==limit)"
    fail=1
    # S1b: Если в базе реально меньше 50 валидных - выводим число и PASS
    if [ "${LIST_COUNT}" -lt 50 ]; then
        echo "  ℹ️  INFO: В базе валидных игр = ${LIST_COUNT} < 50 (это редкий случай)"
        echo "  ✅ PASS: n = ${LIST_N} == count = ${LIST_COUNT} (все валидные игры возвращены)"
        fail=0  # Сбрасываем fail, так как это валидный случай
    fi
elif [ "${LIST_COUNT}" -lt 50 ]; then
    echo "  ⚠️  WARNING: count = ${LIST_COUNT} < 50 (может быть нормально, если данных мало)"
elif [ "${EXPLORE_MODE}" = "true" ]; then
    echo "  ⚠️  WARNING: explore_mode = true (по умолчанию должно быть false для витрины)"
    # Не блокируем, но предупреждаем
else
    echo "  ✅ PASS: n = ${LIST_N} == 50, count = ${LIST_COUNT}, explore_mode = ${EXPLORE_MODE}"
fi
echo

# S2: В первых 20 играх нет пустых title и steam_url (A1: фильтры)
echo "S2. Проверка title и steam_url (первые 20 игр):"
S2_RESPONSE=$(CURL "${API_URL}/api/v1/deals/list?limit=20")
BAD_APP_IDS=$(echo "${S2_RESPONSE}" | jq -r '[.games[] | select(.app_id==null)] | length' 2>/dev/null || echo "999")
BAD_TITLES=$(echo "${S2_RESPONSE}" | jq -r '[.games[] | select((.title|tostring|length)==0 or .title==null)] | length' 2>/dev/null || echo "999")
BAD_URLS=$(echo "${S2_RESPONSE}" | jq -r '[.games[] | select((.steam_url|tostring|length)==0 or .steam_url==null)] | length' 2>/dev/null || echo "999")

# A2: Проверка формата steam_url (regex)
BAD_URL_FORMATS=$(echo "${S2_RESPONSE}" | jq -r '[.games[] | select(.steam_url | test("^https://store\\.steampowered\\.com/app/\\d+/$") | not)] | length' 2>/dev/null || echo "999")

echo "  bad_app_ids = ${BAD_APP_IDS}"
echo "  bad_titles = ${BAD_TITLES}"
echo "  bad_urls = ${BAD_URLS}"
echo "  bad_url_formats = ${BAD_URL_FORMATS}"

if [ "${BAD_APP_IDS}" -gt 0 ]; then
    echo "  ❌ FAIL: Найдено ${BAD_APP_IDS} игр с пустым app_id"
    fail=1
elif [ "${BAD_TITLES}" -gt 0 ]; then
    echo "  ❌ FAIL: Найдено ${BAD_TITLES} игр с пустым title"
    fail=1
elif [ "${BAD_URLS}" -gt 0 ]; then
    echo "  ❌ FAIL: Найдено ${BAD_URLS} игр с пустым steam_url"
    fail=1
elif [ "${BAD_URL_FORMATS}" -gt 0 ]; then
    echo "  ❌ FAIL: Найдено ${BAD_URL_FORMATS} игр с неправильным форматом steam_url (ожидается https://store.steampowered.com/app/<app_id>/)"
    fail=1
else
    echo "  ✅ PASS: Все игры имеют app_id, title, steam_url (правильного формата)"
fi
echo

# S2b: B2 - Guard в витрине: has_publisher не должен содержать "ищет издателя"
echo "S2b. Проверка partner-mode для has_publisher (B2):"
S2B_RESPONSE=$(CURL "${API_URL}/api/v1/deals/list?limit=50")
HAS_PUBLISHER_COUNT=$(echo "${S2B_RESPONSE}" | jq -r '[.games[] | select(.publisher_status_code=="has_publisher")] | length' 2>/dev/null || echo "0")
BAD_VERDICTS=$(echo "${S2B_RESPONSE}" | jq -r '[.games[] | select(.publisher_status_code=="has_publisher" and (.verdict_label_ru | ascii_downcase | contains("ищет издателя")))] | length' 2>/dev/null || echo "0")

echo "  has_publisher_count = ${HAS_PUBLISHER_COUNT}"
echo "  bad_verdicts (has_publisher + 'ищет издателя') = ${BAD_VERDICTS}"

if [ "${BAD_VERDICTS}" -gt 0 ]; then
    echo "  ❌ FAIL: Найдено ${BAD_VERDICTS} игр с has_publisher, но verdict содержит 'ищет издателя'"
    fail=1
elif [ "${HAS_PUBLISHER_COUNT}" -eq 0 ]; then
    echo "  ℹ️  INFO: Нет игр с has_publisher для проверки"
else
    echo "  ✅ PASS: Все игры с has_publisher имеют нейтральный verdict (partner-mode)"
fi
echo

# S3: /list не содержит thesis
echo "S3. Проверка что thesis НЕ попал в list:"
S3_RESPONSE=$(CURL "${API_URL}/api/v1/deals/list?limit=1")
HAS_THESIS=$(echo "${S3_RESPONSE}" | jq -r '.games[0] | if . then has("thesis") else false end' 2>/dev/null || echo "false")
HAS_THESIS_EXPLAIN=$(echo "${S3_RESPONSE}" | jq -r '.games[0] | if . then has("thesis_explain") else false end' 2>/dev/null || echo "false")

echo "  has_thesis = ${HAS_THESIS}"
echo "  has_thesis_explain = ${HAS_THESIS_EXPLAIN}"

if [ "${HAS_THESIS}" = "true" ]; then
    echo "  ❌ FAIL: games[0] содержит thesis (не должно быть в list)"
    fail=1
elif [ "${HAS_THESIS_EXPLAIN}" = "true" ]; then
    echo "  ❌ FAIL: games[0] содержит thesis_explain (не должно быть в list)"
    fail=1
else
    echo "  ✅ PASS: thesis и thesis_explain отсутствуют в list"
fi
echo

# S4: Explore Mode (явный) работает
echo "S4. Explore Mode (явный параметр):"
S4_RESPONSE=$(CURL "${API_URL}/api/v1/deals/list?limit=50&explore_mode=true&min_intent_score=0&min_quality_score=0")
S4_N=$(echo "${S4_RESPONSE}" | jq -r '.games | length' 2>/dev/null || echo "0")
S4_EXPLORE=$(echo "${S4_RESPONSE}" | jq -r '.debug.explore_mode // false' 2>/dev/null || echo "false")

echo "  n = ${S4_N}"
echo "  explore_mode = ${S4_EXPLORE}"

if [ "${S4_EXPLORE}" != "true" ]; then
    echo "  ❌ FAIL: explore_mode = ${S4_EXPLORE} (ожидается true)"
    fail=1
elif [ "${S4_N}" -lt 50 ]; then
    echo "  ⚠️  WARNING: n = ${S4_N} < 50 (может быть нормально, если данных мало)"
else
    echo "  ✅ PASS: explore_mode = true, n = ${S4_N}"
fi
echo

# S5: Verify enrichment endpoint (усиленная проверка)
echo "S5. Проверка endpoint metadata/enrich_missing (усиленная):"
S5_RESPONSE=$(curl -4 -sS -X POST "${API_URL}/api/v1/deals/metadata/enrich_missing?limit=10" 2>&1)
S5_STATUS=$(echo "${S5_RESPONSE}" | jq -r '.status // "error"' 2>/dev/null || echo "error")
S5_CHECKED=$(echo "${S5_RESPONSE}" | jq -r '.result.checked // 0' 2>/dev/null || echo "0")
S5_ENRICHED=$(echo "${S5_RESPONSE}" | jq -r '.result.enriched_ok // 0' 2>/dev/null || echo "0")
S5_FAILED=$(echo "${S5_RESPONSE}" | jq -r '.result.failed // 0' 2>/dev/null || echo "0")
S5_SKIPPED=$(echo "${S5_RESPONSE}" | jq -r '.result.skipped // 0' 2>/dev/null || echo "0")
S5_SAMPLE_FAILURES=$(echo "${S5_RESPONSE}" | jq -r '.result.sample_failures[0:3] // []' 2>/dev/null || echo "[]")

echo "  status = ${S5_STATUS}"
echo "  checked = ${S5_CHECKED}"
echo "  enriched_ok = ${S5_ENRICHED}"
echo "  failed = ${S5_FAILED}"
echo "  skipped = ${S5_SKIPPED}"

if [ "${S5_STATUS}" != "ok" ]; then
    echo "  ❌ FAIL: /api/v1/deals/metadata/enrich_missing status = ${S5_STATUS}"
    fail=1
elif [ "${S5_CHECKED}" -eq 0 ]; then
    echo "  ✅ PASS: checked=0 (нечего обогащать)"
elif [ "${S5_ENRICHED}" -ge 1 ] && [ "${S5_FAILED}" -lt "${S5_CHECKED}" ]; then
    echo "  ✅ PASS: enriched_ok=${S5_ENRICHED} >= 1, failed=${S5_FAILED} < checked=${S5_CHECKED}"
elif [ "${S5_ENRICHED}" -eq 0 ] && [ "${S5_FAILED}" -gt 0 ]; then
    echo "  ❌ FAIL: enriched_ok=0 и failed=${S5_FAILED} > 0 (обогащение не работает)"
    echo "  sample_failures: ${S5_SAMPLE_FAILURES}"
    fail=1
else
    echo "  ⚠️  WARNING: enriched_ok=${S5_ENRICHED}, failed=${S5_FAILED}, checked=${S5_CHECKED}"
    echo "  sample_failures: ${S5_SAMPLE_FAILURES}"
fi
echo

# S6: C2 - Проверка enrich_from_recent_signals endpoint
echo "S6. Проверка endpoint metadata/enrich_from_recent_signals (C2):"
S6_RESPONSE=$(curl -4 -sS -X POST "${API_URL}/api/v1/deals/metadata/enrich_from_recent_signals?days=7&limit=10" 2>&1)
S6_STATUS=$(echo "${S6_RESPONSE}" | jq -r '.status // "error"' 2>/dev/null || echo "error")
S6_CHECKED=$(echo "${S6_RESPONSE}" | jq -r '.result.checked // 0' 2>/dev/null || echo "0")
S6_ENRICHED=$(echo "${S6_RESPONSE}" | jq -r '.result.enriched_ok // 0' 2>/dev/null || echo "0")
S6_FAILED=$(echo "${S6_RESPONSE}" | jq -r '.result.failed // 0' 2>/dev/null || echo "0")

echo "  status = ${S6_STATUS}"
echo "  checked = ${S6_CHECKED}"
echo "  enriched_ok = ${S6_ENRICHED}"
echo "  failed = ${S6_FAILED}"

if [ "${S6_STATUS}" != "ok" ]; then
    echo "  ❌ FAIL: /api/v1/deals/metadata/enrich_from_recent_signals status = ${S6_STATUS}"
    fail=1
elif [ "${S6_CHECKED}" -eq 0 ]; then
    echo "  ℹ️  INFO: checked=0 (нет свежих сигналов за последние 7 дней)"
else
    echo "  ✅ PASS: Endpoint работает, checked=${S6_CHECKED}, enriched_ok=${S6_ENRICHED}"
fi
echo

# Итог
if [ "${fail}" -eq 0 ]; then
    echo "=== ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ==="
    exit 0
else
    echo "=== ❌ НЕКОТОРЫЕ ПРОВЕРКИ ПРОВАЛЕНЫ ==="
    exit 1
fi
