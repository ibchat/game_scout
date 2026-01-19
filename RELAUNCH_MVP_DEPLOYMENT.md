# Relaunch Scout MVP - Инструкция по развертыванию

## ✅ Что было реализовано

### PR1: Фиксы market_scan + scan_runs
- ✅ Исправлен response формат (`scan_run_id`, `found_seed`, `fetched_details`, `upserted`)
- ✅ Улучшен парсинг Steam Search (3 метода извлечения app_id)
- ✅ Обновлена SQL миграция для `relaunch_scan_runs`

### PR2: Failure Diagnosis Engine
- ✅ Создан `relaunch_diagnosis.py` с 7 категориями провала (rule-based)
- ✅ Создана таблица `relaunch_failure_analysis`
- ✅ Добавлен endpoint `POST /admin/diagnose`
- ✅ Обновлен `/candidates` (failure_categories, suggested_angles, steam_url)
- ✅ Обновлен `/health` (scanner_version, last_scan)

### PR3: UI Updates
- ✅ Внутренние вкладки в Relaunch Scout: Scan, Candidates, Diagnosis, Research
- ✅ Обновлен `renderRelaunch` для отображения failure_categories и suggested_angles
- ✅ Имена игр кликабельны (steam_url)

---

## 🚀 Быстрое обновление

```bash
# Автоматическое обновление (рекомендуется)
./scripts/update_relaunch_mvp.sh
```

Или вручную:

```bash
# 1. Создать таблицы
docker compose exec -T postgres psql -U postgres -d game_scout -f migrations/create_relaunch_scan_runs.sql
docker compose exec -T postgres psql -U postgres -d game_scout -f migrations/create_relaunch_failure_analysis.sql

# 2. Перезапустить API
docker compose restart api

# 3. Проверить health
curl http://localhost:8000/api/v1/relaunch/health | jq
```

---

## 🧪 Тестирование

### 1. Market Scan
```bash
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
  }' | jq
```

**Ожидаемый результат:**
- `found_seed >= 200`
- `eligible >= 20`
- `upserted >= 10`
- В `excluded` есть breakdown (mega_hit, f2p, too_new, etc.)

### 2. Diagnosis
```bash
curl -X POST http://localhost:8000/api/v1/relaunch/admin/diagnose \
  -H "Content-Type: application/json" \
  -d '{"limit": 10}' | jq
```

**Ожидаемый результат:**
- `diagnosed >= 1`
- У каждой игры есть `failure_categories` и `suggested_angles`

### 3. Candidates
```bash
curl http://localhost:8000/api/v1/relaunch/candidates | jq '.[0]'
```

**Ожидаемый результат:**
- `steam_url` присутствует
- `failure_categories` - массив
- `suggested_angles` - массив
- `name` не "Steam #ID"

### 4. Проверка отсутствия мега-хитов
```bash
curl http://localhost:8000/api/v1/relaunch/candidates | jq '.[] | select(.steam_app_id == "1091500" or .steam_app_id == "730" or .steam_app_id == "570")'
```

**Ожидаемый результат:** пустой список (Cyberpunk, CS2, Dota не должны быть в кандидатах)

---

## 📋 Критерии приёмки

- [x] После market_scan в кандидаты не попадают Cyberpunk/CS2/Dota
- [x] candidates показывает минимум 20-50 релевантных игр
- [x] Имена нормальные, кликабельные, ведут в Steam
- [x] После diagnose у каждой игры есть failure_category и relaunch_angle
- [x] Docker compose restart api → сервис стартует без traceback
- [x] Нет двойных префиксов /relaunch/relaunch

---

## 📁 Структура файлов

```
apps/api/routers/
  ├── relaunch.py                    # Основной router (обновлён)
  ├── relaunch_config.py            # Конфигурация
  ├── relaunch_filters.py           # Фильтры
  ├── relaunch_diagnosis.py         # Diagnosis Engine (новый)
  └── steam_research_engine.py      # Steam Research Engine

migrations/
  ├── create_relaunch_scan_runs.sql
  └── create_relaunch_failure_analysis.sql

apps/api/static/
  └── game_scout_dashboard.html      # Обновлён UI
```

---

## 🔧 Troubleshooting

### API не стартует
```bash
docker compose logs api --tail 50
```

### Таблицы не создаются
```bash
docker compose exec -T postgres psql -U postgres -d game_scout -c "\dt relaunch*"
```

### Market scan находит 0 игр
- Проверь интернет-соединение
- Убедись, что Steam доступен
- Попробуй увеличить `page_end` (например, до 10)
- Проверь логи: `docker compose logs api | grep "Steam Research"`

### Diagnosis не работает
- Убедись, что таблица `relaunch_failure_analysis` создана
- Проверь, что есть активные игры в `relaunch_apps`
- Проверь логи на ошибки Steam API

---

## 📝 Следующие шаги (опционально)

1. **Asia Fit Score** - добавить вычисление для азиатского рынка
2. **Research Endpoints** - YouTube/Reddit/TikTok для диагностики провала
3. **История reviews** - для более точной диагностики timing failure
4. **Автоматизация** - Celery задачи для периодического сканирования
