# Fix Deals Routing & Migration

## Проблемы

1. **Таблица `deal_intent_game` не существует** - миграция не применена
2. **Ошибка роутинга** - `/diagnostics` конфликтует с `/{app_id}` (FastAPI интерпретирует "diagnostics" как app_id)

## Решение

### 1. Порядок роутов исправлен
Специфичные пути теперь ДО параметризованных:
- `/list` ✅
- `/diagnostics` ✅ (перед `/{app_id}`)
- `/bootstrap` ✅ (перед `/{app_id}`)
- `/{app_id}` ✅
- `/{app_id}/action` ✅
- `/signals/import` ✅

### 2. Дубликаты удалены
Удалены дубликаты `/diagnostics` и `/bootstrap` endpoints.

## Следующие шаги

### 1. Применить миграцию
```bash
docker compose exec api alembic upgrade head
```

### 2. Проверить таблицы
```bash
docker compose exec postgres psql -U postgres -d game_scout -c "\dt deal_intent*"
```

### 3. Запустить bootstrap
```bash
curl -X POST "http://localhost:8000/api/v1/deals/bootstrap?limit=50"
```

### 4. Проверить diagnostics
```bash
curl "http://localhost:8000/api/v1/deals/diagnostics" | jq '.'
```
