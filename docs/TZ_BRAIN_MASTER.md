# Game Scout — Brain System (v1.0 → v1.2)

## 0. Цель системы (НЕ менять)

Brain — это аналитический слой Game Scout, который:
- интерпретирует сигналы интереса вокруг игр
- формирует инвестиционную / издательскую гипотезу
- НЕ влияет на базовые scoring / verdict / list logic
- добавляет объяснимость и действие, а не «умный текст»

⸻

## 1. Базовые инварианты (КРИТИЧЕСКИ ВАЖНО)

### 1.1 Что ЗАПРЕЩЕНО
- ❌ Добавлять thesis или thesis_explain в `/api/v1/deals/list`
- ❌ Менять:
  - verdict
  - verdict_label_ru
  - intent_score
  - quality_score
  - gates
  - dashboard HTML
- ❌ Добавлять миграции БД
- ❌ Менять существующие фильтры list endpoint

### 1.2 Где что разрешено

| Endpoint | Можно |
|----------|-------|
| `/api/v1/deals/list` | только lightweight поля |
| `/api/v1/deals/{app_id}/detail` | DealThesis + Explainability |
| `/api/v1/deals/shortlist` | агрегированный decision view |

⸻

## 2. Brain v1.0–v1.1 — Deal Thesis (ОБЯЗАТЕЛЬНО)

### 2.1 DealThesis возвращается ТОЛЬКО в /detail

```json
thesis: {
  thesis: string,
  thesis_archetype: enum,
  temporal_context: enum,
  confidence: float (0.0–1.0),
  supporting_facts: string[],
  counter_facts: string[],
  publisher_interest: object
}
```

⸻

### 2.2 Archetypes (строго фиксированы)

- `early_publisher_search`
- `late_pivot_after_release`
- `weak_signal_exploration`
- `high_intent_low_quality` (ТОЛЬКО fallback)
- `opportunistic_outreach`
- `unclear_intent`

❌ `marketing_distress` — запрещён

⸻

### 2.3 Temporal Context

- `recent_interest` (≤ 60 дней)
- `stale_interest` (61–90)
- `old_interest` (> 90)

**Константы:**

```python
FRESH_DAYS = 60
WEAK_DAYS = 90
```

⸻

## 3. Publisher Status (v1.1)

### 3.1 Источник истины

`steam_app_cache.publishers`

### 3.2 Нормализация

- `has_publisher`
- `self_published`
- `unknown`

Возвращается:
- в `/list`
- в `/detail`
- в `/shortlist`

⸻

### 3.3 Partner-mode (ОБЯЗАТЕЛЬНО)

Если `publisher_status_code == has_publisher`:
- ❌ НЕЛЬЗЯ писать «ищет издателя»
- ✅ Использовать:
  - «партнёр»
  - «co-publishing»
  - «маркетинговый партнёр»

**Обязательный risk_flag:**

```
"У игры уже есть издатель — запрос может означать co-pub, маркетинг или рестарт релиза"
```

⸻

## 4. Confidence Formula (v1.1, ЖЁСТКО)

```
base = 0.0
+0.3 если свежие behavioral_intent ≤ 60 дней
+0.2 если stage согласуется с archetype
+0.1 если intent_score > 0
-0.2 если quality_score == 0
-0.2 если latest_signal_days > 90
clamp 0.0–1.0
```

Также сохраняется:

```json
confidence_breakdown: [
  {rule, delta, applied}
]
```

⸻

## 5. Brain v1.2 — 4 ВЕКТОРА (НОВОЕ)

⸻

### VECTOR #1 — Explainability UI

#### 5.1 Добавляется ТОЛЬКО в /detail

```json
thesis_explain: {
  headline: string,
  why: string[] (1–6),
  signals: [{source, days_ago, snippet}] (≤3),
  publisher_context: {
    publisher_status_ru,
    note
  },
  confidence_breakdown: array (5 правил),
  next_step: string
}
```

**Правила:**
- `snippet ≤ 140` символов
- `[SYNTHETIC]` удаляется
- `signals.days_ago` — ОБЯЗАТЕЛЬНО (НЕ `published_at`)

⸻

### VECTOR #2 — Auto-Shortlist

#### 5.2 Endpoint

`GET /api/v1/deals/shortlist`

**Параметры:**
- `limit` (default 30, max 200)
- `min_confidence`
- `archetypes`
- `publisher_status`
- `temporal_context`
- `publisher_types`

**Response item (СТРОГО):**

```json
{
  app_id,
  title,
  steam_url,
  stage,
  publisher_status_code,
  publisher_status,
  temporal_context,
  confidence,
  thesis_archetype,
  publisher_types,
  publisher_types_ru,
  intent_score,
  quality_score,
  verdict,
  verdict_label_ru,
  updated_at
}
```

❌ **Запрещено:**
- `headline`
- `why_now`
- `thesis`
- `thesis_explain`

**Сортировка:**
1. `confidence desc`
2. `temporal_context = recent_interest` выше
3. `intent_score desc`

⸻

### VECTOR #3 — Investor / Publisher View

#### 5.3 Publisher Types (codes)

- `scout_fund`
- `genre_publisher`
- `marketing_publisher`
- `turnaround_publisher`
- `operator_publisher`
- `influencer_partner`

**В `/detail.publisher_interest`:**
- `who_might_care_codes: string[]`
- `who_might_care: string[]` (RU labels, backward compatible)

**В `/shortlist`:**
- `publisher_types`
- `publisher_types_ru`
- фильтр `publisher_types` работает по пересечению

⸻

### VECTOR #4 — Signal Scale

#### 5.4 Seed Script

`scripts/seed_more_signals.sh`

**Требования:**
- добавляет ≥ 8 новых app_id
- итого `apps_with_signals >= 10`
- часть сигналов: 0–7 дней
- часть: 30–120 дней
- ИДЕМПОТЕНТЕН

⸻

## 6. Verify Scripts (НЕ ТРОГАТЬ ЛОГИКУ)

**Обязательные проверки:**
- `verify_synthetic.sh`
  - S1–S10 (v1.1)
  - S11 Explainability
  - S12 publisher codes
  - S13 signal coverage
- `verify_shortlist.sh`
- `verify_signal_coverage.sh`

**Все должны:**
- `exit 0`

⸻

## 7. Definition of Do

### 7.1 Definition of Done (Cursor обязан это проверить)
- `/api/v1/health` → healthy
- `/list` не содержит thesis
- `/detail` содержит thesis + thesis_explain
- `/shortlist` соответствует контракту
- `apps_with_signals ≥ 10`
- `dashboard.html` не менялся
- нет миграций
- все verify скрипты зелёные

⸻

## 8. Главное правило для Cursor

**Brain — это слой интерпретации, а не принятия решений.**
**Он объясняет и предлагает, но не ломает базовую логику.**
