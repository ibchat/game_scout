# 🚨 Немедленные команды для исправления проблем

## Проблемы на скриншотах:
1. Cyberpunk 2077 (#1091500) в списке
2. Steam #730 и Steam #570 (CS2 и Dota) в списке
3. Имена не обогащены ("Steam #730")

## ✅ Что исправлено в коде:
1. ✅ Фильтрация blacklist в `/candidates` endpoint
2. ✅ Новый endpoint `/admin/cleanup_blacklist` для деактивации существующих мегахитов
3. ✅ SCANNER_BUILD_ID обновлён: "2026-01-16_16-45"

---

## 🔧 Команды (выполни по порядку):

### 1. Перезапустить API (чтобы применить изменения)
```bash
docker compose restart api
sleep 5
```

### 2. Проверить что build_id обновился
```bash
curl http://localhost:8000/api/v1/relaunch/health | jq '.scanner_build_id'
```
**Ожидаемый результат:** `"2026-01-16_16-45"`

### 3. Деактивировать существующие мегахиты
```bash
curl -X POST http://localhost:8000/api/v1/relaunch/admin/cleanup_blacklist | jq
```
**Ожидаемый результат:**
```json
{
  "status": "ok",
  "deactivated_by_app_id": 3,
  "deactivated_by_name": 0,
  "total_deactivated": 3,
  "note": "Деактивировано 3 игр из blacklist."
}
```

### 4. Проверить что мегахиты исчезли
```bash
curl http://localhost:8000/api/v1/relaunch/candidates | jq '.[] | select(.steam_app_id == "1091500" or .steam_app_id == "730" or .steam_app_id == "570")'
```
**Ожидаемый результат:** Пустой вывод (нет результатов)

### 5. Обновить страницу в браузере
- Нажми **Ctrl+F5** (Windows/Linux) или **Cmd+Shift+R** (Mac)
- Или закрой и открой вкладку заново

### 6. Проверить что список обновился
- Открой вкладку "Candidates"
- Проверь что Cyberpunk, CS2 и Dota исчезли

---

## 📝 Если имена всё ещё "Steam #id":

Запусти новый scan - он обогатит имена:
```bash
curl -X POST http://localhost:8000/api/v1/relaunch/admin/market_scan \
  -H "Content-Type: application/json" \
  -d '{
    "min_months": 6,
    "max_months": 24,
    "min_reviews": 50,
    "max_reviews": 10000,
    "limit_seed": 300,
    "limit_add": 20,
    "page_start": 1,
    "page_end": 10
  }' | jq '{status, found_seed, fetched_details, eligible, upserted}'
```

После scan имена должны обновиться автоматически.

---

## ✅ Финальная проверка:

```bash
# 1. build_id
curl http://localhost:8000/api/v1/relaunch/health | jq '.scanner_build_id'

# 2. Нет мегахитов
curl http://localhost:8000/api/v1/relaunch/candidates | jq '.[] | select(.steam_app_id == "1091500" or .steam_app_id == "730" or .steam_app_id == "570")'

# 3. Нет "Steam #" в именах
curl http://localhost:8000/api/v1/relaunch/candidates?limit=20 | jq '.[] | .name' | grep -i "steam #"
```

Все три проверки должны вернуть пустой результат или нормальные имена.
