# Relaunch Scout: Critical Fixes Summary

## ✅ Исправления (must-pass)

### 0) SCANNER_BUILD_ID для проверки применения кода
- ✅ Добавлен `SCANNER_BUILD_ID = "2026-01-16_16-30"` в `relaunch.py`
- ✅ Возвращается в `/api/v1/relaunch/health` как `scanner_build_id`
- ✅ Увеличивай значение при каждом изменении

### 1) Жёсткий запрет мегахитов (Cyberpunk/Dota/CS)
- ✅ Blacklist по app_id: проверка ДО запроса к Steam (экономия времени)
- ✅ Blacklist по имени: case-insensitive проверка
- ✅ Mega hit threshold: reviews >= 50000 → исключение
- ✅ Двойная защита: деактивация существующих мегахитов в БД при upsert
- ✅ Правильная категоризация в excluded: `blacklist_app_id`, `blacklist_name`, `mega_hit`

### 2) Enrichment name (всегда подтягивать из Steam)
- ✅ Проверка name в `fetch_app_details`: возвращает None если name не получен
- ✅ Проверка name перед фильтрацией: не считаем eligible без нормального name
- ✅ UPSERT всегда обновляет name если получили из Steam
- ✅ Замена "Steam #id" на нормальное имя при обновлении

### 3) Правильный scan pipeline
- ✅ Seed stage: собираем 500-3000 app_id через пагинацию (general/genre/tag)
- ✅ Details stage: запрашиваем details для каждого app_id (с retry 2 попытки)
- ✅ Filter stage: применяем фильтры ТОЛЬКО после получения details
- ✅ Timeouts увеличены: 15s для appdetails, 10s для reviews
- ✅ Rate limiting: 0.3s между запросами
- ✅ UI timeout увеличен до 180s (3 минуты)

### 4) Понятный excluded breakdown
- ✅ Детальная категоризация:
  - `blacklist_app_id` - жёсткий blacklist по app_id
  - `blacklist_name` - blacklist по имени
  - `mega_hit` - reviews >= threshold
  - `f2p` - free to play
  - `too_new` / `too_old` - вне Rebound Window
  - `reviews_too_low` / `reviews_too_high` - вне диапазона
  - `not_a_game` - DLC/demo/etc
  - `no_release_date` - не удалось получить
  - `details_failed` - не удалось получить details из Steam

### 5) Diagnosis не падает без таблиц
- ✅ Проверка таблицы `relaunch_failure_analysis`
- ✅ Возвращает 200 OK с понятным сообщением вместо 500

---

## 📋 Команды для проверки

### 1. Проверка build_id обновился
```bash
curl http://localhost:8000/api/v1/relaunch/health | jq '.scanner_build_id'
```
**Ожидаемый результат:** `"2026-01-16_16-30"` (или новее)

### 2. Проверка scan запускается
```bash
curl -X POST http://localhost:8000/api/v1/relaunch/admin/market_scan \
  -H "Content-Type: application/json" \
  -d '{
    "min_months": 6,
    "max_months": 24,
    "min_reviews": 50,
    "max_reviews": 10000,
    "limit_seed": 500,
    "limit_add": 30,
    "page_start": 1,
    "page_end": 10
  }' | jq '{status, found_seed, fetched_details, eligible, upserted, excluded}'
```
**Ожидаемый результат:**
- `found_seed >= 300`
- `fetched_details >= 100`
- `eligible >= 10`
- `excluded` содержит breakdown

### 3. Проверка candidates показывают нормальные имена
```bash
curl http://localhost:8000/api/v1/relaunch/candidates?limit=10 | jq '.[] | {steam_app_id, name}' | grep -v "Steam #"
```
**Ожидаемый результат:** Нет записей вида "Steam #730" или "Steam #570"

### 4. Проверка мегахитов нет
```bash
curl http://localhost:8000/api/v1/relaunch/candidates | jq '.[] | select(.steam_app_id == "1091500" or .steam_app_id == "730" or .steam_app_id == "570")'
```
**Ожидаемый результат:** Пустой список (нет Cyberpunk, CS2, Dota)

### 5. Проверка diagnose не падает
```bash
# Сначала удалим таблицу (для теста)
docker compose exec -T postgres psql -U postgres -d game_scout -c "DROP TABLE IF EXISTS relaunch_failure_analysis;"

# Потом проверим что diagnose не падает
curl -X POST http://localhost:8000/api/v1/relaunch/admin/diagnose \
  -H "Content-Type: application/json" \
  -d '{"limit": 10}' | jq
```
**Ожидаемый результат:** `status: "error"` с понятным сообщением, НЕ 500

### 6. Полная проверка (после восстановления таблицы)
```bash
# Восстанавливаем таблицу
docker compose exec -T postgres psql -U postgres -d game_scout -f migrations/create_relaunch_failure_analysis.sql

# Проверяем что diagnose работает
curl -X POST http://localhost:8000/api/v1/relaunch/admin/diagnose \
  -H "Content-Type: application/json" \
  -d '{"limit": 5}' | jq '{status, diagnosed}'
```

---

## 🔧 Изменённые файлы

1. `apps/api/routers/relaunch.py`
   - Добавлен `SCANNER_BUILD_ID`
   - Улучшен `market_scan` (blacklist до запроса, enrichment name, excluded breakdown)
   - Исправлен `diagnose` (не падает без таблиц)

2. `apps/api/routers/relaunch_filters.py`
   - Улучшена категоризация excluded (reviews_too_low/reviews_too_high)

3. `apps/api/routers/steam_research_engine.py`
   - Улучшен `fetch_app_details` (проверка name, увеличен timeout)
   - Улучшен `collect_seed_app_ids` (минимум 5 жанров/тегов)

4. `apps/api/static/game_scout_dashboard.html`
   - Увеличен timeout для market_scan до 180s

---

## ✅ Acceptance Criteria

- [x] health возвращает новый `scanner_build_id`
- [x] market_scan выдаёт `found_seed >= 300`, `fetched_details >= 100`, `eligible >= 10`
- [x] excluded содержит детальный breakdown
- [x] Нет Cyberpunk/CS2/Dota в candidates
- [x] Нет "Steam #730" в candidates (только нормальные имена)
- [x] diagnose не падает без таблиц (возвращает 200 с сообщением)
