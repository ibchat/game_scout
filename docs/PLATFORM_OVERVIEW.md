# Game Scout Platform Overview

## Architecture: Two Contours

Game Scout состоит из двух независимых контуров, которые решают разные задачи:

---

## Contour A: Deal Intent (Запросы "ищу издателя/паблишера")

### Назначение
Собирать сигналы из внешних источников, определять игру на Steam (через app_id) и выдавать результат в таблицу/листинг для поиска издательских возможностей.

### Поток данных

1. **Ingestion** (сбор сигналов):
   - Источники: Reddit, Discord, YouTube, TikTok, Twitter
   - Endpoint: `POST /api/v1/deals/signals/collect_discord?days=...&limit=...`
   - Endpoint: `POST /api/v1/deals/signals/collect_reddit?days=...&limit=...`
   - Celery tasks: `collect_discord_signals_task`, `collect_deal_intent_signals_reddit_task`

2. **Processing** (обработка):
   - Извлечение Steam app_id из URL (store.steampowered.com/app/{id})
   - Матчинг фраз "looking for publisher" / "seeking publisher" / etc.
   - Scoring: `publisher_intent_score`, `confidence`

3. **Storage** (хранение):
   - Таблица: `public.deal_intent_signal`
   - Ключевые поля:
     - `id` (uuid pk)
     - `app_id` (int, Steam app ID)
     - `source` (text: reddit, discord, synthetic)
     - `source_subtype` (text: discord, test_inject, etc.)
     - `url`, `text`, `signal_type`
     - `publisher_intent_score`, `publisher_phrase`
     - `published_at`, `created_at`
     - `channel_name`, `server_name` (для Discord)

4. **API** (выдача):
   - Endpoint: `GET /api/v1/deals/signals/list?min_intent_score=...&min_quality_score=...&limit=...`
   - Возвращает список сигналов с фильтрацией по score

### Что считается успехом
- ✅ В таблице `deal_intent_signal` есть записи с `source IN ('reddit', 'discord')`
- ✅ Есть записи с `app_id IS NOT NULL` (Steam игры определены)
- ✅ Endpoint `/api/v1/deals/signals/list` возвращает `count > 0`
- ✅ Discord ingestion работает: `channels_visible >= 1`, `messages_matched >= 1`

---

## Contour B: Trends (Тренды на ближайшие годы)

### Назначение
Собирать тренды "по всем возможным источникам" и выдавать в систему для анализа emerging games и трендовых тегов.

### Поток данных

1. **Events Collection** (сбор событий):
   - Источники: Reddit, YouTube, TikTok, Twitter
   - Celery tasks: `collect_reddit_events_task`, `collect_youtube_events_task`
   - Таблица: `trends_raw_events`
   - Поля: `source`, `external_id`, `url`, `title`, `body`, `published_at`, `matched_steam_app_id`

2. **Signals Processing** (обработка сигналов):
   - Таблица: `trends_raw_signals`
   - Агрегация событий в сигналы
   - Матчинг с Steam app_id

3. **Daily Aggregation** (дневная агрегация):
   - Таблица: `trends_game_daily` (по играм)
   - Таблица: `trends_tags_daily` (по тегам)
   - Метрики: reviews, discussions, positive_ratio, tags

4. **Emerging Games** (emerging engine):
   - Endpoint: `GET /api/v1/trends/emerging`
   - Endpoint: `GET /api/v1/trends/tags/emerging`
   - Scoring: `emerging_score`, `growth_type`, `verdict`

5. **Worker Trends** (фоновый процессор):
   - Контейнер: `worker_trends`
   - Скрипт: `apps/worker/tasks/trends_jobs.py`
   - Обрабатывает `trend_jobs` таблицу
   - Записывает в `steam_app_facts`, `steam_review_daily`

### Что считается успехом
- ✅ В таблице `trends_raw_events` есть записи за последние 24 часа
- ✅ В таблице `trends_game_daily` есть записи
- ✅ Endpoint `/api/v1/trends/emerging` возвращает `count > 0` (или объясняет почему 0)
- ✅ Worker `worker_trends` запущен и пишет в БД

---

## Infrastructure Services

### Required Services
- **postgres**: PostgreSQL database
- **redis**: Redis cache and Celery message broker
- **api**: FastAPI web server (REST API + Dashboard)
- **worker**: Celery worker (processes Deal Intent tasks)
- **beat**: Celery beat scheduler (runs scheduled tasks)
- **worker_trends**: Trends processor (continuous loop)

### Dashboard
- Endpoint: `GET /dashboard`
- File: `apps/api/static/game_scout_dashboard.html`
- Served by: `api` service (no separate container)

---

## Verification Scripts

- `scripts/verify_stack.sh` - Infrastructure health
- `scripts/verify_deal_intent_e2e.sh` - Deal Intent contour E2E
- `scripts/verify_discord_e2e.sh` - Discord ingestion E2E
- `scripts/verify_trends_e2e.sh` - Trends contour E2E
- `scripts/verify_dashboard.sh` - Dashboard accessibility

---

## Key Endpoints

### Deal Intent
- `POST /api/v1/deals/signals/collect_discord?days=7&limit=50&debug=1`
- `GET /api/v1/deals/signals/list?min_intent_score=0&min_quality_score=0&limit=5`

### Trends
- `GET /api/v1/trends/health`
- `GET /api/v1/trends/emerging`
- `GET /api/v1/trends/tags/emerging`
- `GET /api/v1/admin/system/events_24h`

### System
- `GET /api/v1/health`
- `GET /dashboard`
