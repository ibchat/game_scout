# Relaunch Scout: Critical Fixes - Checklist

## ✅ Все исправления применены

### Изменённые файлы:
1. `apps/api/routers/relaunch.py` - SCANNER_BUILD_ID, улучшен market_scan, исправлен diagnose
2. `apps/api/routers/relaunch_filters.py` - улучшена категоризация excluded
3. `apps/api/routers/steam_research_engine.py` - проверка name, увеличен timeout
4. `apps/api/static/game_scout_dashboard.html` - увеличен timeout до 180s

---

## 🔍 6 команд для проверки (выполни по порядку)

### 1. Проверка build_id обновился
```bash
curl http://localhost:8000/api/v1/relaunch/health | jq '.scanner_build_id'
```
**Ожидаемый результат:** `"2026-01-16_16-30"` (или новее)  
**Если не обновился:** `docker compose restart api` и проверь снова

---

### 2. Проверка scan запускается и даёт результаты
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
- `status: "ok"`
- `found_seed >= 300`
- `fetched_details >= 100`
- `eligible >= 10`
- `excluded` содержит детальный breakdown (blacklist_app_id, blacklist_name, mega_hit, etc.)

---

### 3. Проверка candidates показывают нормальные имена
```bash
curl http://localhost:8000/api/v1/relaunch/candidates?limit=20 | jq '.[] | {steam_app_id, name}' | head -40
```
**Ожидаемый результат:** Нет записей вида `"name": "Steam #730"` или `"name": "Steam #570"`  
**Должны быть:** нормальные названия игр

---

### 4. Проверка мегахитов нет в candidates
```bash
curl http://localhost:8000/api/v1/relaunch/candidates | jq '.[] | select(.steam_app_id == "1091500" or .steam_app_id == "730" or .steam_app_id == "570")'
```
**Ожидаемый результат:** Пустой вывод (нет Cyberpunk 2077, CS2, Dota 2)

---

### 5. Проверка diagnose не падает без таблиц
```bash
# Временно удаляем таблицу для теста
docker compose exec -T postgres psql -U postgres -d game_scout -c "DROP TABLE IF EXISTS relaunch_failure_analysis;"

# Проверяем что diagnose не падает
curl -X POST http://localhost:8000/api/v1/relaunch/admin/diagnose \
  -H "Content-Type: application/json" \
  -d '{"limit": 10}' | jq
```
**Ожидаемый результат:**
- `status: "error"` (не 500!)
- `note` содержит понятное сообщение про миграцию

**Восстановление таблицы:**
```bash
docker compose exec -T postgres psql -U postgres -d game_scout -f migrations/create_relaunch_failure_analysis.sql
```

---

### 6. Проверка diagnose работает с таблицей
```bash
curl -X POST http://localhost:8000/api/v1/relaunch/admin/diagnose \
  -H "Content-Type: application/json" \
  -d '{"limit": 5}' | jq '{status, diagnosed, note}'
```
**Ожидаемый результат:**
- `status: "ok"`
- `diagnosed >= 0` (может быть 0 если нет активных игр)

---

## 📊 Дополнительные проверки

### Проверка excluded breakdown детальный
```bash
curl -X POST http://localhost:8000/api/v1/relaunch/admin/market_scan \
  -H "Content-Type: application/json" \
  -d '{"limit_seed": 200, "limit_add": 10, "page_start": 1, "page_end": 5}' | jq '.excluded'
```
**Ожидаемый результат:** JSON объект с ключами:
- `blacklist_app_id`
- `blacklist_name`
- `mega_hit`
- `f2p`
- `too_new`
- `too_old`
- `reviews_too_low`
- `reviews_too_high`
- `not_a_game`
- `no_release_date`
- `details_failed`

---

## 🚨 Если что-то не работает

### build_id не обновился
```bash
# Проверь что контейнер перезапущен
docker compose restart api
sleep 5
curl http://localhost:8000/api/v1/relaunch/health | jq '.scanner_build_id'
```

### scan находит 0 seed
- Проверь интернет-соединение
- Проверь логи: `docker compose logs api | grep "Steam Research"`
- Попробуй увеличить `page_end` до 15

### Мегахиты всё ещё попадают
- Проверь что blacklist применяется: `docker compose logs api | grep "blacklisted"`
- Проверь excluded breakdown: должно быть `blacklist_app_id > 0`

### Имена остаются "Steam #id"
- Проверь что `fetch_app_details` возвращает name
- Проверь логи: `docker compose logs api | grep "Enriching name"`

---

## ✅ Acceptance Criteria (финальная проверка)

- [ ] health возвращает `scanner_build_id: "2026-01-16_16-30"` (или новее)
- [ ] market_scan: `found_seed >= 300`, `fetched_details >= 100`, `eligible >= 10`
- [ ] excluded содержит детальный breakdown
- [ ] Нет Cyberpunk/CS2/Dota в candidates
- [ ] Нет "Steam #730" в candidates
- [ ] diagnose не падает без таблиц (200 OK с сообщением)
