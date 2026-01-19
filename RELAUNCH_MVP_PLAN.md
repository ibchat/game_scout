# План реализации Relaunch Scout MVP

## Текущее состояние

✅ Уже реализовано:
- `relaunch_config.py` - конфигурация, blacklist, жанры/теги
- `steam_research_engine.py` - пагинация Steam Search
- `relaunch_filters.py` - фильтры Rebound Window
- `market_scan` endpoint с пагинацией
- SQL миграция для `relaunch_scan_runs`

❌ Нужно доработать:
- Исправить баги в `market_scan` (правильная работа с деталями)
- Создать `relaunch_failure_analysis` таблицу
- Реализовать Failure Diagnosis Engine
- Добавить endpoint `/admin/diagnose`
- Обновить `/candidates` с новыми полями
- Обновить UI (внутренние вкладки в Relaunch Scout)

---

## PR1: Фиксы market_scan + scan_runs

### Файлы для изменения:

1. **`apps/api/routers/relaunch.py`**
   - Исправить логику `market_scan` (правильная обработка деталей)
   - Убедиться что `scan_batch_id` сохраняется в `relaunch_scan_runs`
   - Исправить response формат (scan_run_id вместо scan_batch_id)

2. **`migrations/create_relaunch_scan_runs.sql`**
   - Проверить что таблица создаётся правильно
   - Добавить индексы

3. **`apps/api/routers/steam_research_engine.py`**
   - Улучшить парсинг Steam Search (правильное извлечение app_id)
   - Добавить fallback если BeautifulSoup не находит ссылки

### Команды проверки PR1:
```bash
# 1. Создать таблицу
docker compose exec -T postgres psql -U postgres -d game_scout -f migrations/create_relaunch_scan_runs.sql

# 2. Проверить что API стартует
docker compose restart api
docker compose logs api | tail -20

# 3. Тест market_scan
curl -X POST http://localhost:8000/api/v1/relaunch/admin/market_scan \
  -H "Content-Type: application/json" \
  -d '{
    "min_months": 6,
    "max_months": 24,
    "min_reviews": 50,
    "max_reviews": 10000,
    "limit_seed": 200,
    "limit_add": 20,
    "page_start": 1,
    "page_end": 5
  }'

# 4. Проверить что нет Cyberpunk/CS2/Dota
curl http://localhost:8000/api/v1/relaunch/candidates | jq '.[] | select(.steam_app_id == 1091500 or .steam_app_id == 730 or .steam_app_id == 570)'
```

---

## PR2: Diagnosis Engine + таблица

### Новые файлы:

1. **`apps/api/routers/relaunch_diagnosis.py`** (новый)
   - Rule-based диагностика провала
   - 7 категорий failure
   - Mapping failure → relaunch angles
   - Функция `diagnose_game(app_id, steam_data) -> diagnosis_result`

2. **`migrations/create_relaunch_failure_analysis.sql`** (новый)
   - Таблица `relaunch_failure_analysis`
   - Индексы и foreign key

### Файлы для изменения:

3. **`apps/api/routers/relaunch.py`**
   - Добавить endpoint `POST /admin/diagnose`
   - Обновить `GET /candidates` (добавить failure_categories, suggested_angles, key_signals)
   - Добавить steam_url в candidates

### Команды проверки PR2:
```bash
# 1. Создать таблицу
docker compose exec -T postgres psql -U postgres -d game_scout -f migrations/create_relaunch_failure_analysis.sql

# 2. Запустить диагностику
curl -X POST http://localhost:8000/api/v1/relaunch/admin/diagnose \
  -H "Content-Type: application/json" \
  -d '{"limit": 50}'

# 3. Проверить candidates с новыми полями
curl http://localhost:8000/api/v1/relaunch/candidates | jq '.[0] | {steam_app_id, name, steam_url, failure_categories, suggested_angles}'
```

---

## PR3: UI Updates (Relaunch Scout tab)

### Файлы для изменения:

1. **`apps/api/static/game_scout_dashboard.html`**
   - Добавить внутренние вкладки в Relaunch Scout:
     - Scan (market_scan форма)
     - Candidates (таблица с новыми полями)
     - Diagnosis (кнопка diagnose + вывод)
     - Research (заглушки для YouTube/Reddit/TikTok)
   - Сделать name кликабельным (ссылка на Steam)
   - Показать failure_categories, suggested_angles
   - **ВАЖНО**: Не трогать другие вкладки (Analytics, YouTube, Reddit, Games, Yearly)

### Команды проверки PR3:
```bash
# 1. Проверить что все вкладки работают
# Открыть http://localhost:8000/dashboard
# Проверить что открываются: Analytics, YouTube, Reddit, Games, Yearly, Relaunch Scout

# 2. Проверить что в Relaunch Scout есть подвкладки
# Проверить что name кликабелен и ведёт на Steam

# 3. Проверить что market_scan работает из UI
# Нажать "Сканировать рынок" и проверить результат
```

---

## Структура файлов после всех PR

```
apps/api/routers/
  ├── relaunch.py                    # Основной router (обновлён)
  ├── relaunch_config.py            # ✅ Готов
  ├── relaunch_filters.py           # ✅ Готов
  ├── relaunch_diagnosis.py         # 🆕 PR2
  └── steam_research_engine.py      # ✅ Готов

migrations/
  ├── create_relaunch_scan_runs.sql           # ✅ Готов
  └── create_relaunch_failure_analysis.sql    # 🆕 PR2

apps/api/static/
  └── game_scout_dashboard.html      # Обновлён PR3
```

---

## Критерии приёмки (финальные)

1. ✅ market_scan находит 300-1500 seed, 20-80 eligible
2. ✅ Нет Cyberpunk/CS2/Dota в candidates
3. ✅ Имена нормальные, кликабельные, ведут в Steam
4. ✅ После diagnose у каждой игры есть failure_category и angle
5. ✅ Docker compose restart api → стартует без ошибок
6. ✅ Все вкладки dashboard работают
7. ✅ Нет двойных префиксов /relaunch/relaunch

---

## Следующие шаги

Начинаю с PR1: фиксы market_scan + scan_runs
