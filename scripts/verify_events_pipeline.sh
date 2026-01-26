#!/bin/bash

echo "=== Запуск верификации Events Pipeline (Engine v4) ==="

API_URL="http://localhost:8000/api/v1"

# 1. Проверка наличия таблиц
echo "1. Проверка таблиц БД..."
TABLES_CHECK=$(docker compose exec -T postgres psql -U postgres -d game_scout -c "
SELECT 
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'trends_raw_events') THEN 'OK' ELSE 'MISSING' END as events_table,
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'steam_app_aliases') THEN 'OK' ELSE 'MISSING' END as aliases_table;
" 2>&1 | grep -E "OK|MISSING" | head -2)

if echo "${TABLES_CHECK}" | grep -q "MISSING"; then
    echo "   ❌ Таблицы отсутствуют. Нужно применить миграции."
    exit 1
else
    echo "   ✅ Таблицы trends_raw_events и steam_app_aliases существуют"
fi

# 2. Проверка наличия events в БД
echo "2. Проверка событий в trends_raw_events..."
EVENTS_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
SELECT COUNT(*) FROM trends_raw_events WHERE captured_at >= now() - interval '24 hours';
" 2>&1 | grep -v "warning\|level\|time=" | tr -d ' ')

if [ "${EVENTS_COUNT}" -gt 0 ]; then
    echo "   ✅ Найдено событий за 24ч: ${EVENTS_COUNT}"
else
    echo "   ⚠️ Событий за 24ч не найдено. Запустите collect_events."
fi

# 3. Проверка доли matched событий
echo "3. Проверка доли matched событий..."
MATCHED_STATS=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
SELECT 
    source,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE matched_steam_app_id IS NOT NULL) as matched,
    ROUND(100.0 * COUNT(*) FILTER (WHERE matched_steam_app_id IS NOT NULL) / NULLIF(COUNT(*), 0), 1) as match_pct
FROM trends_raw_events
WHERE captured_at >= now() - interval '24 hours'
GROUP BY source;
" 2>&1 | grep -v "warning\|level\|time=")

if [ -n "${MATCHED_STATS}" ]; then
    echo "   Статистика по источникам:"
    echo "${MATCHED_STATS}" | while read line; do
        if [ -n "${line}" ]; then
            echo "   ${line}"
        fi
    done
else
    echo "   ⚠️ Нет данных для анализа"
fi

# 4. Проверка новых signal_type в trends_raw_signals
echo "4. Проверка новых signal_type (steam_news)..."
NEW_SIGNALS=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
SELECT COUNT(*) FROM trends_raw_signals 
WHERE source = 'steam_news' 
  AND captured_at >= now() - interval '24 hours';
" 2>&1 | grep -v "warning\|level\|time=" | tr -d ' ')

if [ "${NEW_SIGNALS}" -gt 0 ]; then
    echo "   ✅ Найдено steam_news сигналов: ${NEW_SIGNALS}"
else
    echo "   ⚠️ steam_news сигналов не найдено. Запустите events_to_signals."
fi

# 5. Проверка emerging endpoint на evidence
echo "5. Проверка API /trends/games/emerging на evidence..."
API_RESPONSE=$(curl -s "${API_URL}/trends/games/emerging?limit=1")

if echo "${API_RESPONSE}" | jq -e '.games[0].evidence' > /dev/null 2>&1; then
    EVIDENCE_COUNT=$(echo "${API_RESPONSE}" | jq '.games[0].evidence | length')
    echo "   ✅ API возвращает evidence. Количество ссылок в первой игре: ${EVIDENCE_COUNT}"
else
    echo "   ⚠️ API не возвращает evidence (может быть пустым массивом)"
fi

# 6. Проверка новых компонентов scoring
echo "6. Проверка новых компонентов scoring (Engine v4)..."
if echo "${API_RESPONSE}" | jq -e '.games[0].score_components.score_confirmation' > /dev/null 2>&1; then
    CONFIRMATION=$(echo "${API_RESPONSE}" | jq -r '.games[0].score_components.score_confirmation // 0')
    MOMENTUM=$(echo "${API_RESPONSE}" | jq -r '.games[0].score_components.score_momentum // 0')
    CATALYST=$(echo "${API_RESPONSE}" | jq -r '.games[0].score_components.score_catalyst // 0')
    echo "   ✅ Новые компоненты присутствуют:"
    echo "      confirmation=${CONFIRMATION}, momentum=${MOMENTUM}, catalyst=${CATALYST}"
else
    echo "   ⚠️ Новые компоненты scoring отсутствуют (возможно legacy режим)"
fi

# 7. Проверка why_now
echo "7. Проверка why_now..."
WHY_NOW=$(echo "${API_RESPONSE}" | jq -r '.games[0].why_now // "N/A"')
if [ "${WHY_NOW}" != "N/A" ] && [ "${WHY_NOW}" != "Недостаточно данных для объяснения" ]; then
    echo "   ✅ why_now заполнен: ${WHY_NOW:0:60}..."
else
    echo "   ⚠️ why_now пуст или fallback"
fi

echo ""
echo "=== Верификация Events Pipeline ЗАВЕРШЕНА ==="
echo ""
echo "📝 Следующие шаги:"
echo "   1. Если событий нет: POST ${API_URL}/admin/system/action {\"action\": \"collect_events\"}"
echo "   2. Если matched < 60%: POST ${API_URL}/admin/system/action {\"action\": \"generate_aliases\"}"
echo "   3. Если matched < 60%: POST ${API_URL}/admin/system/action {\"action\": \"match_events\"}"
echo "   4. Если сигналов нет: POST ${API_URL}/admin/system/action {\"action\": \"events_to_signals\"}"
