#!/usr/bin/env bash
set -euo pipefail

# Vector #4: Seed more signals для увеличения покрытия
# Добавляет минимум 8 новых app_id с сигналами (итого ≥ 10 уникальных app_id)

DB_SERVICE="${DB_SERVICE:-postgres}"
DB_NAME="${DB_NAME:-game_scout}"
DB_USER="${DB_USER:-postgres}"

psql_db() {
  local sql="$1"
  docker compose exec -T "$DB_SERVICE" bash -lc "export PAGER=cat; psql -U '$DB_USER' -d '$DB_NAME' -Atc \"$sql\""
}

echo "=== Seed More Signals (Vector #4) ==="
echo

# Список app_id для seed (используем существующие app_id из deal_intent_game или создаём новые)
# Для простоты используем app_id от 1000000 до 1000007
SEED_APP_IDS=(1000000 1000001 1000002 1000003 1000004 1000005 1000006 1000007)

# Тексты сигналов (реалистичные, но с префиксом [SYNTHETIC])
SIGNAL_TEXTS=(
  "[SYNTHETIC] Looking for a publisher for our indie game. We have a demo ready and are seeking marketing support."
  "[SYNTHETIC] Seeking funding and publisher partnership. Our game is in early access and needs distribution help."
  "[SYNTHETIC] Need a publisher for our upcoming game. We're looking for someone who can help with marketing and reach."
  "[SYNTHETIC] Our team is actively seeking a publisher. We have a pitch deck ready and are open to discussions."
  "[SYNTHETIC] Looking for publisher support for our indie title. We need help with marketing and user acquisition."
  "[SYNTHETIC] Seeking publisher partnership. Our game is coming soon and we need distribution and marketing support."
  "[SYNTHETIC] Need a publisher for our game. We're looking for someone who can help with marketing and community building."
  "[SYNTHETIC] Actively seeking a publisher. We have a demo available and are looking for marketing and distribution help."
)

# Распределение дней назад (свежие и старые)
FRESH_DAYS_AGO=(0 1 2 3 4 5 6 7)
OLD_DAYS_AGO=(30 45 60 75 90 105 120)

inserted=0
skipped=0

for i in "${!SEED_APP_IDS[@]}"; do
  app_id="${SEED_APP_IDS[$i]}"
  signal_text="${SIGNAL_TEXTS[$i]}"
  
  # Чередуем свежие и старые сигналы
  if [ $((i % 2)) -eq 0 ]; then
    days_ago="${FRESH_DAYS_AGO[$((i % ${#FRESH_DAYS_AGO[@]}))]}"
  else
    days_ago="${OLD_DAYS_AGO[$((i % ${#OLD_DAYS_AGO[@]}))]}"
  fi
  
  # Вычисляем published_at
  published_at=$(date -u -v-${days_ago}d +"%Y-%m-%d %H:%M:%S" 2>/dev/null || date -u -d "${days_ago} days ago" +"%Y-%m-%d %H:%M:%S" 2>/dev/null || date -u +"%Y-%m-%d %H:%M:%S")
  
  # Определяем signal_type (behavioral_intent или intent_keyword)
  if echo "$signal_text" | grep -qiE "(looking for|seeking|need|actively seeking)"; then
    signal_type="behavioral_intent"
  else
    signal_type="intent_keyword"
  fi
  
  # Проверяем, существует ли уже такой сигнал (идемпотентность)
  # Используем уникальный URL для каждого app_id+days_ago, чтобы ON CONFLICT работал
  unique_url="https://reddit.com/r/gamedev/synthetic_${app_id}_${days_ago}"
  
  # Проверяем существование по (source, url) - уникальный индекс
  existing=$(psql_db "SELECT COUNT(*) FROM deal_intent_signal WHERE source = 'reddit' AND url = '$unique_url';" 2>/dev/null || echo "0")
  
  if [ "$existing" = "0" ]; then
    # Экранируем кавычки в signal_text для SQL
    signal_text_escaped=$(echo "$signal_text" | sed "s/'/''/g")
    
    # Вставляем сигнал (используем экранированный текст)
    # Используем || true чтобы set -e не падал на ON CONFLICT
    if psql_db "
      INSERT INTO deal_intent_signal (app_id, source, text, signal_type, published_at, created_at, url)
      VALUES (
        $app_id,
        'reddit',
        '$signal_text_escaped',
        '$signal_type',
        '$published_at'::timestamp,
        NOW(),
        '$unique_url'
      )
      ON CONFLICT (source, url) WHERE url IS NOT NULL DO NOTHING;
    " > /dev/null 2>&1; then
      inserted=$((inserted + 1))
      echo "  ✅ Добавлен сигнал для app_id=$app_id (days_ago=$days_ago, type=$signal_type)"
    else
      skipped=$((skipped + 1))
      echo "  ⚠️  Пропущен app_id=$app_id (возможно, уже существует)"
    fi
  else
    skipped=$((skipped + 1))
    echo "  ⚠️  Пропущен app_id=$app_id (уже существует)"
  fi
done

echo
echo "=== Результат ==="
echo "  Добавлено: $inserted сигналов"
echo "  Пропущено: $skipped сигналов"

# Проверяем итоговое количество уникальных app_id с сигналами
TOTAL_APPS=$(psql_db "SELECT COUNT(DISTINCT app_id) FROM deal_intent_signal WHERE app_id IS NOT NULL;")
echo "  Всего уникальных app_id с сигналами: $TOTAL_APPS"

if [ "$TOTAL_APPS" -ge 10 ]; then
  echo "  ✅ Цель достигнута: apps_with_signals >= 10"
  exit 0
else
  echo "  ⚠️  Цель не достигнута: apps_with_signals = $TOTAL_APPS (нужно >= 10)"
  exit 1
fi
