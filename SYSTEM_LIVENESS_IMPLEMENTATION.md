# Реализация "Оживления системы" Game Scout

## ✅ Выполнено

### 1️⃣ Worker Heartbeat через Redis
- ✅ Создан модуль `apps/worker/tasks/heartbeat.py` с функциями:
  - `send_heartbeat()` - отправка heartbeat в Redis
  - `check_heartbeat()` - проверка статуса воркера
  - `start_heartbeat_loop()` - бесконечный цикл heartbeat
- ✅ Интегрирован в `apps/worker/celery_app.py` через Celery signals (`worker_ready`, `worker_shutting_down`)
- ✅ Интегрирован в `apps/worker/tasks/trends_jobs.py` через отдельный поток
- ✅ Обновлён `apps/api/routers/system_admin.py` для чтения heartbeat из Redis
- ✅ Статус воркера: `OK` / `DOWN` / `UNKNOWN` (только если Redis недоступен)

### 2️⃣ Пайплайн данных: контроль обновлений
- ✅ Добавлены метрики в `system/summary`:
  - `daily_updated_today` - сколько игр обновлено в `trends_game_daily` сегодня
  - `reviews_updated_today` - сколько игр обновлено в `steam_review_daily` сегодня
  - `errors_today` - ошибки в `trend_jobs` за сегодня
  - `coverage_daily_pct` - процент обновленных игр (daily)
  - `coverage_reviews_pct` - процент обновленных игр (reviews)
- ✅ Добавлен admin action `run_daily_refresh`:
  - Обновляет reviews и appdetails по seed apps батчами
  - Логирует прогресс
  - Опционально запускает агрегацию

### 3A: Диагностика Emerging
- ✅ Создан endpoint `/trends/emerging/diagnostics`:
  - Возвращает причины исключения игр:
    - `no_daily_data` - нет данных в trends_game_daily
    - `below_min_score` - score ниже порога (30)
    - `evergreen_filtered` - отфильтровано как evergreen
    - `insufficient_signals` - недостаточно сигналов
    - `steam_negative` - отрицательная динамика Steam
    - `low_quality` - низкое качество (positive_ratio < 0.70)
  - Возвращает топ-10 "почти emerging" (score >= 20, но < 30)

### 3B: Steam-only Emerging
- ✅ Обновлён `make_verdict()` в `trends_brain.py`:
  - Добавлен вердикт: "Рост отзывов без социального подтверждения (Steam-only)"
  - Работает для игр с `steam_confirmed=True` и `reddit_valid=False` и `youtube_valid=False`
  - Пониженный confidence для Steam-only emerging

### 4️⃣ Источники данных: реальное участие
- ✅ `system/summary` уже показывает реальное покрытие источников:
  - `signals_coverage` - покрытие по источникам (apps_with_signals, signals_total, pct)
  - `signals_freshness` - свежесть данных (last_captured_at, age_minutes)
- ⚠️ TODO: Добавить информацию о том, используется ли источник в скоринге (нужно анализировать `signals_used` в emerging games)

### 5️⃣ Вшивание логики
- ✅ Все методы интерпретации в TrendsBrain вызываются в `analyze_game()`:
  - `detect_context()` - определение контекста игры
  - `interpret_steam()`, `interpret_reddit()`, `interpret_youtube()`, `interpret_news()` - интерпретация сигналов
  - `combine_scores()` - комбинирование скоров
  - `make_verdict()` - формирование вердикта
  - `build_explanation()` - построение объяснения
  - `build_why_now()` - формирование "why_now"
- ✅ Результаты видны в API:
  - `verdict` - вердикт на русском
  - `explanation` - список объяснений
  - `why_now` - краткое объяснение
  - `signals_used` - список использованных источников
  - `score_components` - компоненты скора

## 📋 Что осталось сделать

### 4️⃣ Источники данных: реальное участие (доработка)
Нужно добавить в `system/summary` блок "Влияние источников на Emerging":
- Анализировать `signals_used` в emerging games
- Показывать, сколько игр используют каждый источник
- Показывать причину, если источник не участвует (например, "нет Steam-confirmation")

### 5️⃣ Вшивание логики (проверка)
Нужно убедиться, что:
- Все ошибки логируются через `logger.debug()` / `logger.error()`
- Ошибка одного источника не валит endpoint
- Все функции <= 50 строк (проверить)

## 🧪 Тестирование

### Проверка heartbeat
```bash
# Проверить статус воркеров
curl http://localhost:8000/api/v1/admin/system/summary | jq '.health.worker'
curl http://localhost:8000/api/v1/admin/system/summary | jq '.health.worker_trends'
```

### Проверка метрик пайплайна
```bash
curl http://localhost:8000/api/v1/admin/system/summary | jq '.trends_today | {seed_total, daily_updated_today, reviews_updated_today, errors_today, coverage_daily_pct, coverage_reviews_pct}'
```

### Проверка диагностики emerging
```bash
curl http://localhost:8000/api/v1/trends/emerging/diagnostics | jq '.'
```

### Проверка Steam-only emerging
```bash
# Запустить refresh
curl -X POST http://localhost:8000/api/v1/admin/system/action \
  -H "Content-Type: application/json" \
  -d '{"action": "run_daily_refresh", "batch_size": 100, "limit_apps": 50}'

# Проверить emerging
curl http://localhost:8000/api/v1/trends/games/emerging?limit=10 | jq '.games[] | select(.verdict | contains("Steam-only"))'
```

## 📝 Коммиты

1. `feat: worker heartbeat через Redis`
   - `apps/worker/tasks/heartbeat.py` (новый)
   - `apps/worker/celery_app.py` (обновлён)
   - `apps/worker/tasks/trends_jobs.py` (обновлён)
   - `apps/api/routers/system_admin.py` (обновлён)

2. `feat: пайплайн данных - метрики и контроль`
   - `apps/api/routers/system_admin.py` (метрики + admin action)

3. `feat: диагностика emerging и Steam-only поддержка`
   - `apps/api/routers/trends_v1.py` (endpoint diagnostics)
   - `apps/worker/analysis/trends_brain.py` (Steam-only вердикт)
