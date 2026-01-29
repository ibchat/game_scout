# Debug Deals Bootstrap Errors

## Проблема
Bootstrap возвращает `errors: 50` для всех 50 seed apps.

## Возможные причины

1. **Ошибка в `detect_steam_review_app_id_column`** - функция может падать
2. **SQL ошибка** - неправильный запрос или отсутствие таблиц
3. **Ошибка в `analyze_deal_intent`** - проблема в scoring логике

## Что добавлено

1. ✅ Детальное логирование ошибок с типом исключения
2. ✅ Логирование успешного определения `app_id_col`
3. ✅ Обработка ошибок SQL отдельно

## Как проверить

1. **Проверить логи worker:**
```bash
docker compose logs worker --tail 200 | grep deal_intent
```

2. **Запустить bootstrap снова и посмотреть логи:**
```bash
curl -X POST "http://localhost:8000/api/v1/deals/bootstrap?limit=5"
docker compose logs worker --tail 50
```

3. **Проверить, что таблицы существуют:**
```bash
docker compose exec postgres psql -U postgres -d game_scout -c "\dt deal_intent*"
```

4. **Проверить, что steam_review_daily существует и имеет правильную колонку:**
```bash
docker compose exec postgres psql -U postgres -d game_scout -c "\d steam_review_daily"
```

## Следующие шаги

После проверки логов нужно будет:
- Исправить конкретную ошибку
- Возможно, добавить fallback для отсутствующих данных
- Улучшить обработку edge cases
