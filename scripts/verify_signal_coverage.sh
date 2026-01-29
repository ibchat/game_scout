#!/usr/bin/env bash
set -euo pipefail

DB_SERVICE="${DB_SERVICE:-postgres}"
DB_NAME="${DB_NAME:-game_scout}"
DB_USER="${DB_USER:-postgres}"

echo "=== Диагностика Signal Coverage ==="
echo

psql_db() {
  local sql="$1"
  docker compose exec -T "$DB_SERVICE" bash -lc "export PAGER=cat; psql -U '$DB_USER' -d '$DB_NAME' -Atc \"$sql\""
}

# COUNT(DISTINCT app_id) в deal_intent_signal
echo "1. Общее количество уникальных app_id с сигналами:"
TOTAL_APPS="$(psql_db "SELECT COUNT(DISTINCT app_id) FROM deal_intent_signal WHERE app_id IS NOT NULL;")"
echo "   $TOTAL_APPS"
echo

# Топ-20 app_id по количеству сигналов
echo "2. Топ-20 app_id по количеству сигналов:"
psql_db "
  SELECT 
    app_id,
    COUNT(*) as signal_count,
    MAX(created_at) as last_signal
  FROM deal_intent_signal
  WHERE app_id IS NOT NULL
  GROUP BY app_id
  ORDER BY signal_count DESC
  LIMIT 20;
" | while IFS='|' read -r app_id count last_signal; do
  echo "   app_id=$app_id: $count сигналов (последний: ${last_signal:-N/A})"
done
echo

# Сколько сигналов за последние 7 дней
echo "3. Сигналы за последние 7 дней:"
SIGNALS_7D="$(psql_db "SELECT COUNT(*) FROM deal_intent_signal WHERE created_at >= CURRENT_DATE - INTERVAL '7 days';")"
echo "   $SIGNALS_7D сигналов"
echo

# Распределение по источникам
echo "4. Распределение сигналов по источникам:"
psql_db "
  SELECT 
    source,
    COUNT(*) as count,
    COUNT(DISTINCT app_id) as unique_apps
  FROM deal_intent_signal
  WHERE app_id IS NOT NULL
  GROUP BY source
  ORDER BY count DESC;
" | while IFS='|' read -r source count unique_apps; do
  echo "   $source: $count сигналов, $unique_apps уникальных app_id"
done
echo

echo "=== Диагностика завершена ==="
