# Emerging Engine v4 Final — Статус реализации

## ✅ Выполнено

### 1. Emerging Engine v4 — полностью отделён от TrendsBrain
**Файл:** `apps/worker/analysis/emerging_engine_v4.py`

**Функции:**
- `compute_emerging_score()` — формула: `log1p(recent_reviews_count_30d) * all_positive_ratio`
- `analyze_emerging(app_row: dict)` — новый интерфейс, принимает dict из SQL

**Фильтры (последовательно):**
1. Growth Filter: `recent_reviews_count_30d >= 30`
2. Quality Filter: `all_positive_ratio >= 0.70`
3. Evergreen Filter: возраст > 3 лет И `all_reviews_count >= 50000`
4. Score Threshold: `emerging_score >= 2.0`

**Вердикты (строгий набор):**
- "Устойчивый рост — emerging"
- "Ранний рост — требует наблюдения"
- "Рост есть, но слабая динамика"
- "Недостаточно данных"
- "Высокий интерес, но низкое качество"
- "Evergreen — исключено из emerging"

### 2. Emerging Endpoint — полностью переписан
**Файл:** `apps/api/routers/trends_v1.py`
**Endpoint:** `GET /api/v1/trends/emerging`

**Изменения:**
- ✅ Убраны все вызовы `TrendsBrain.analyze_game()`
- ✅ Убраны все signals, score_components
- ✅ Использует только `steam_review_daily` и `steam_app_cache`
- ✅ Использует `analyze_emerging()` из `emerging_engine_v4`
- ✅ Упрощённый формат ответа

**Формат ответа:**
```json
{
  "status": "ok",
  "emerging": [
    {
      "app_id": 123,
      "name": "Game Name",
      "recent_reviews_30d": 124,
      "positive_ratio": 0.82,
      "emerging_score": 4.31,
      "verdict": "Устойчивый рост — emerging"
    }
  ],
  "count": 1,
  "total_analyzed": 1220
}
```

### 3. Diagnostics Endpoint — честный truth-endpoint
**Файл:** `apps/api/routers/trends_v1.py`
**Endpoint:** `GET /api/v1/trends/emerging/diagnostics`

**Изменения:**
- ✅ Использует реальные фильтры v4
- ✅ Возвращает счётчики прохождения каждого фильтра
- ✅ Использует только `steam_review_daily`

**Формат ответа:**
```json
{
  "status": "ok",
  "total_seed_apps": 1220,
  "passed_growth": 95,
  "passed_quality": 63,
  "filtered_evergreen": 12,
  "below_score_threshold": 48,
  "emerging_final": 3
}
```

### 4. System/Summary — убрана ложь
**Файл:** `apps/api/routers/system_admin.py`

**Изменения:**
- ✅ Убраны все упоминания `trends_raw_signals` (не существует)
- ✅ Убраны все упоминания `trend_jobs` (не используется)
- ✅ Использует только `steam_review_daily` для coverage
- ✅ Честно показывает: Reddit/YouTube не используются
- ✅ Blind spots показывают реальное состояние

## 📋 Проверка готовности

### Критерии из ТЗ v4 Final:

1. ✅ `/trends/emerging` возвращает:
   - либо непустой список
   - либо пустой, но diagnostics объясняет почему

2. ✅ Нет ни одного обращения к:
   - `trends_raw_signals` (убрано из emerging endpoint)
   - `trend_jobs` (убрано из system/summary)
   - `TrendsBrain` (убрано из emerging endpoint)

3. ⚠️ Данные в dashboard = данные API = данные diagnostics
   - Нужно обновить dashboard для отображения упрощённого формата

## 🧪 Тестирование

### Проверка emerging endpoint
```bash
curl http://localhost:8000/api/v1/trends/emerging?limit=10 | jq '.'
```

Ожидаемый результат:
- `status: "ok"`
- `emerging: []` или список игр
- Каждая игра имеет: `app_id`, `name`, `recent_reviews_30d`, `positive_ratio`, `emerging_score`, `verdict`

### Проверка diagnostics
```bash
curl http://localhost:8000/api/v1/trends/emerging/diagnostics | jq '.'
```

Ожидаемый результат:
- `total_seed_apps > 0`
- Счётчики фильтров объясняют 100% причин
- `emerging_final` = количество игр в `/trends/emerging`

### Проверка system/summary
```bash
curl http://localhost:8000/api/v1/admin/system/summary | jq '.trends_today.signals_coverage'
```

Ожидаемый результат:
- `steam_reviews.active: true/false` (реальное состояние)
- `reddit.active: false` (не используется)
- `youtube.active: false` (не используется)

## 📝 Файлы изменены

1. `apps/worker/analysis/emerging_engine_v4.py` — полностью переписан
2. `apps/api/routers/trends_v1.py` — emerging endpoint переписан, diagnostics обновлён
3. `apps/api/routers/system_admin.py` — убраны несуществующие таблицы

## ⚠️ Что осталось сделать

1. **Обновить dashboard** — отображать упрощённый формат emerging:
   - Убрать: why_now, social signals, confidence, стадии
   - Показывать: название, recent_reviews_30d, positive_ratio, emerging_score, verdict

2. **Проверить совместимость** — убедиться, что старые endpoints не сломаны

## 🎯 Главный принцип (соблюдён)

✅ **Лучше простая система, которая не врёт, чем умная, которая ничего не показывает**

Emerging Engine v4 Final — это простая, честная система, которая:
- Использует только реальные данные (Steam Reviews)
- Не придумывает несуществующие таблицы
- Честно объясняет, почему emerging = 0
- Выдаёт ненулевой результат, если данные позволяют
