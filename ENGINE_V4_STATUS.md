# Engine v4: Deep Analytics + Multi-Channel Parsing — Статус реализации

## ✅ Выполнено

### 1. Миграции БД
- ✅ `migrations/versions/002_create_trends_raw_events.py` — таблица `trends_raw_events` с полями:
  - `source`, `external_id`, `url`, `title`, `body`, `metrics_json`, `published_at`
  - `matched_steam_app_id`, `match_confidence`, `match_reason`
  - Индексы для быстрого поиска
- ✅ Таблица `steam_app_aliases` для entity matching:
  - `steam_app_id`, `alias`, `alias_type`, `weight`
  - UNIQUE constraint на (steam_app_id, alias)

### 2. Генерация алиасов
- ✅ `apps/worker/tasks/generate_aliases.py`:
  - Нормализация названий игр
  - Генерация вариантов (official, common, abbrev, short)
  - Фильтрация stop-words
  - Idempotent (ON CONFLICT DO NOTHING)

### 3. Entity Matching
- ✅ `apps/worker/tasks/entity_matcher.py`:
  - Точное совпадение по word boundaries
  - Fuzzy matching через SequenceMatcher (для длинных алиасов)
  - Confidence scoring (0.80-0.98)
  - Защита от ложных срабатываний

### 4. Steam News Collector
- ✅ `apps/worker/tasks/collect_steam_news.py`:
  - Сбор новостей из Steam Store API
  - Сохранение в `trends_raw_events`
  - Нормализация формата

### 5. Events → Signals Normalizer
- ✅ `apps/worker/tasks/events_to_signals.py`:
  - Агрегация событий по окнам (7d, 14d)
  - Генерация сигналов: `{source}_posts_7d`, `{source}_velocity`, `{source}_freshness_hours`
  - Запись в `trends_raw_signals`

## ⏳ Осталось реализовать

### 6. Обновление Scoring (trends_brain.py)
**Задача**: Добавить компоненты `score_confirmation`, `score_momentum`, `score_catalyst`

**Что нужно**:
- Разделить scoring на компоненты:
  - `score_confirmation` (0..50): Steam reviews/store как подтверждение
  - `score_momentum` (0..30): Social signals (Reddit/YouTube/Twitch) как импульс
  - `score_catalyst` (0..20): News/updates как катализатор
- Обновить `ScoreComponents` dataclass
- Обновить `compute_score_components` метод

### 7. Обновление why_now с Evidence
**Задача**: `why_now` должен ссылаться на реальные события с ссылками

**Что нужно**:
- В `trends_brain.py` добавить метод `generate_why_now_with_evidence`:
  - Запрос к `trends_raw_events` для топ-3 событий за 7 дней
  - Формирование текста: "Вышло 2 обновления за 7 дней (ссылка...)"
  - Возврат `evidence` массива со ссылками
- Обновить `EmergingAnalysis` dataclass: добавить `evidence: List[Dict]`
- Обновить API endpoint `/trends/emerging` для возврата `evidence`

### 8. Обновление Dashboard
**Задача**: Показать evidence ссылки и события в источниках

**Что нужно**:
- В `game_scout_dashboard.html`:
  - Добавить колонку "Ссылки" в таблицу Emerging (иконки источников)
  - При клике открывать топ evidence link
  - Hover показывает tooltip с 3 ссылками
- Вкладка "Источники данных":
  - Блок "События за 24 часа" с метриками matched/unmatched
  - Таблица "Top 20 событий" (source, title, игра, published_at, url)

### 9. Admin Actions
**Задача**: Добавить действия для сбора events и matching

**Что нужно**:
- В `apps/api/routers/system_admin.py`:
  - `POST /admin/system/action` с параметрами:
    - `action: "collect_events"` с `sources: ["steam_news", ...]`
    - `action: "match_events"` для запуска entity matching
    - `action: "generate_aliases"` для генерации алиасов
    - `action: "events_to_signals"` для нормализации events → signals

### 10. Verification Script
**Задача**: `scripts/verify_events_pipeline.sh`

**Что нужно**:
- Проверка наличия events в БД
- Проверка доли matched > 60% (для steam_news)
- Проверка новых signal_type в trends_raw_signals
- Проверка что emerging возвращает evidence

## 📝 Команды для применения миграций

```bash
# Применить миграции
docker compose exec -T postgres psql -U postgres -d game_scout -f migrations/versions/002_create_trends_raw_events.py

# Или через alembic (если настроен)
cd migrations && alembic upgrade head
```

## 📝 Команды для запуска pipeline

```bash
# 1. Генерация алиасов
python3 apps/worker/tasks/generate_aliases.py

# 2. Сбор Steam News events
python3 apps/worker/tasks/collect_steam_news.py

# 3. Entity matching
python3 -c "
from apps.db.session import get_db_session
from apps.worker.tasks.entity_matcher import match_events_batch
from sqlalchemy import text

db = get_db_session()
events = db.execute(text('SELECT id, title, body FROM trends_raw_events WHERE matched_steam_app_id IS NULL LIMIT 100')).mappings().all()
stats = match_events_batch([dict(e) for e in events], db)
print(stats)
db.close()
"

# 4. Events → Signals
python3 -c "
from apps.db.session import get_db_session
from apps.worker.tasks.events_to_signals import aggregate_events_to_signals

db = get_db_session()
stats = aggregate_events_to_signals(db, 'steam_news')
print(stats)
db.close()
"
```

## 🔧 Следующие шаги

1. **Применить миграции** (если БД запущена)
2. **Запустить генерацию алиасов** для существующих игр
3. **Протестировать entity matching** на небольшой выборке
4. **Доработать Steam News collector** (парсинг HTML/JSON если нужно)
5. **Обновить scoring в trends_brain.py** (компоненты)
6. **Обновить why_now с evidence**
7. **Обновить dashboard**
8. **Добавить admin actions**
9. **Создать verification script**

## ⚠️ Замечания

- Steam News API может возвращать HTML вместо JSON — нужен парсер
- Entity matching требует тестирования на реальных данных для настройки confidence thresholds
- Twitch collector не реализован (опционально, требует API ключ или парсинг)
- Миграция должна быть протестирована на dev окружении перед применением на prod
