# TZ_SIGNAL_INGESTION_VECTOR_B_EXEC_V1.md

## 0. Статус документа

**EXECUTION TIER** (обязателен к выполнению)

Имеет приоритет над:
- `TZ_SIGNAL_INGESTION_VECTOR_B_PLAN.md`
- любыми стратегическими обсуждениями

⸻

## 1. Цель (жёсткая, измеримая)

### Основная цель

**apps_with_signals >= 100**

### Пользовательский эффект

**/api/v1/deals/list возвращает >= 200 items**

Это означает:
- дашборд визуально «живой»
- shortlist начинает быть полезным
- Brain начинает реально отбирать

⸻

## 2. Scope (ограничения — КРИТИЧЕСКИ ВАЖНО)

### РАЗРЕШЕНО
- ✅ Только YouTube
- ✅ Только уже существующие данные
- ✅ Только существующие таблицы:
  - `external_video`
  - `external_comment_sample`
  - `deal_intent_signal`
- ✅ Только сигналы с валидным app_id

### ЗАПРЕЩЕНО
- ❌ новые API-ключи
- ❌ YouTube Data API
- ❌ новые таблицы
- ❌ новые источники
- ❌ изменение Brain logic
- ❌ изменение Reddit ingestion
- ❌ изменение dashboard

**Любое отклонение = отклонение PR.**

⸻

## 3. Источник данных (YouTube only)

### Используемые таблицы
- `external_video`
- `external_comment_sample`

### Используемые поля (примерно)
- `video.title`
- `video.description`
- `comment.text`
- `published_at`
- `video.url` / `comment.url`

⸻

## 4. Извлечение app_id (строго)

### Разрешённые способы
- `store.steampowered.com/app/<app_id>`
- `steamcommunity.com/app/<app_id>`

Искать:
- в `description`
- в pinned comments
- в тексте комментариев

### Запрещено
- guessing по названию игры
- fuzzy matching
- Steam search
- любые LLM-догадки

**Нет app_id → нет сигнала.**

⸻

## 5. Типы сигналов

### Разрешённые типы:
- `behavioral_intent`
- `intent_keyword`

### Intent keywords (обязательный минимум)
- `publisher`
- `looking for publisher`
- `need publisher`
- `marketing help`
- `launch failed`
- `no visibility`
- `low sales`
- `wishlist`
- `nobody plays`

⸻

## 6. Логика извлечения сигналов

### Video-level signals

Сигнал создаётся, если:
- в `title` или `description` есть intent keyword
- **И** найден валидный Steam app_id

### Comment-level signals

Сигнал создаётся, если:
- в `comment.text` есть intent keyword
- **И** найден Steam app_id (в тексте или связанном видео)

⸻

## 7. Запись в БД

### Таблица

`deal_intent_signal`

### Обязательные поля
- `app_id`
- `source = "youtube"`
- `signal_type`
- `keyword` (если применимо)
- `url`
- `published_at`
- `snippet` (≤ 280 символов)

⸻

## 8. Идемпотентность (ОБЯЗАТЕЛЬНО)

**ON CONFLICT (source, url) DO NOTHING**

Повторный запуск:
- ❌ не дублирует сигналы
- ❌ не ломает метрики
- ❌ не увеличивает apps_with_signals бесконечно

⸻

## 9. Объём и цели

### Минимальные цели Vector B

**+40–60 новых app_id**

### Ожидаемое состояние:

**apps_with_signals >= 100**

⸻

## 10. Verify & Metrics (обязательно)

После выполнения ОБЯЗАТЕЛЬНО:

```bash
bash scripts/verify_signal_coverage.sh
bash scripts/verify_synthetic.sh
```

### Acceptance Criteria

- `apps_with_signals >= 100`
- `verify_signal_coverage.sh` → PASS
- `verify_synthetic.sh` → PASS

⸻

## 11. Инварианты (НЕ ТРОГАТЬ)
- Brain logic
- thesis / thesis_explain
- verdict / gates / scores
- `/api/v1/deals/list` (без thesis)
- dashboard HTML
- Reddit ingestion

⸻

## 12. Stop Condition

Как только:

**apps_with_signals >= 100**

➡️ ingestion останавливается
➡️ Vector B считается завершённым

⸻

## 13. Out of Scope
- YouTube API
- livestreams
- Shorts
- sentiment analysis
- ranking сигналов
- ML / embeddings
- авторитет каналов

⸻

## 14. Definition of Done (чеклист)
- [ ] `apps_with_signals >= 100`
- [ ] `verify_signal_coverage.sh` PASS
- [ ] `verify_synthetic.sh` PASS
- [ ] повторный запуск ingestion не меняет метрики
- [ ] Brain не изменён
- [ ] Reddit ingestion не затронут

⸻

## 15. Контекст
- Reddit (Vector A) → быстрый старт
- YouTube → масштаб + долгий хвост
- Brain уже готов
- ingestion — чистый upstream

⸻

🔚 **Конец документа**
