# Быстрый старт для проверки Deals / Intent

## Запуск API

### Вариант 1: В фоновом режиме (рекомендуется)
```bash
# Запуск в фоне
docker-compose up -d api

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f api
```

### Вариант 2: Через скрипт
```bash
bash scripts/start_api.sh
```

### Вариант 3: В интерактивном режиме (для отладки)
```bash
docker-compose up api
# Нажмите Ctrl+C для остановки
```

## Проверка данных

### Через API (быстро)
```bash
curl -sS "http://localhost:8000/api/v1/deals/list?limit=50" | jq '{
  total: .count,
  with_real_names: [.games[] | select(.title | test("^App ") | not)] | length,
  with_release_date: [.games[] | select(.release_date != null)] | length,
  old_games: [.games[] | select(.release_date != null and (.release_date | split("-")[0] | tonumber) < 2020)] | length
}'
```

### Через verify-скрипт
```bash
bash scripts/verify_deals_intent.sh
```

## Обновление данных

Если нужно обновить данные в `deal_intent_game`:
```bash
curl -X POST "http://localhost:8000/api/v1/deals/bootstrap?limit=100"
```

## Остановка

```bash
docker-compose stop api
# или
docker-compose down
```
