# Тестирование SQL запроса для Deals

## Проблема
Все еще ошибки при bootstrap. Нужно проверить логи API.

## Команды для проверки

1. **Проверить логи API после bootstrap:**
```bash
docker compose logs api --tail 200 | grep -A 10 -B 5 "deal_intent\|bootstrap\|error\|exception"
```

2. **Проверить, что seed apps существуют:**
```bash
docker compose exec postgres psql -U postgres -d game_scout -c "SELECT COUNT(*) FROM trends_seed_apps WHERE is_active = true;"
```

3. **Проверить структуру steam_app_cache:**
```bash
docker compose exec postgres psql -U postgres -d game_scout -c "\d steam_app_cache" | head -30
```

4. **Проверить структуру steam_app_facts:**
```bash
docker compose exec postgres psql -U postgres -d game_scout -c "\d steam_app_facts" | head -30
```

5. **Проверить, есть ли данные для seed apps:**
```bash
docker compose exec postgres psql -U postgres -d game_scout -c "
SELECT 
    seed.steam_app_id,
    c.name as cache_name,
    f.name as facts_name
FROM trends_seed_apps seed
LEFT JOIN steam_app_cache c ON c.steam_app_id = seed.steam_app_id::bigint
LEFT JOIN steam_app_facts f ON f.steam_app_id = seed.steam_app_id
WHERE seed.is_active = true
LIMIT 5;
"
```

## Что исправлено

1. ✅ Убраны несуществующие колонки `c.developer_name` и `c.publisher_name`
2. ✅ Добавлен rollback при ошибках SQL
3. ✅ Улучшено логирование ошибок
4. ✅ Обработка отсутствия сигналов

## Следующие шаги

После проверки логов нужно будет:
- Исправить конкретную ошибку SQL
- Возможно, проблема в отсутствии данных в steam_app_cache или steam_app_facts
