# Game Scout — Эволюция смыслового ядра (Brain v1.1)

## 0. Цель документа

Зафиксировать и расширить «мозг» платформы Game Scout:
превратить сигналы и метрики в объяснимую, проверяемую и масштабируемую модель издательского интереса.

Документ является:
- ✅ единственным источником требований
- ❌ запрещает любые «улучшения от себя»
- ✅ все изменения должны быть покрыты проверками

⸻

## 1. Базовые принципы (НЕ ОБСУЖДАЮТСЯ)

### 1.1. Смысл выше данных
- Система не отвечает на вопрос "есть ли сигналы"
- Система отвечает на вопрос "кто может быть заинтересован и почему сейчас"

### 1.2. Интерпретация ≠ классификация
- thesis — это гипотеза
- thesis_archetype — это объясняемый паттерн
- publisher_interest — это про действия и мотивации

### 1.3. Любая логика должна быть:
- детерминированной
- покрытой тестом
- объяснимой через API

⸻

## 2. DealThesis — обязательная структура

### 2.1. Где возвращается
- `/api/v1/deals/{app_id}/detail` — обязательно
- `/api/v1/deals/list` — НЕ добавлять (чтобы не ломать UI)

### 2.2. Структура DealThesis (инвариант)

```json
{
  "thesis": "string (RU)",
  "thesis_archetype": "enum",
  "temporal_context": "enum",
  "confidence": 0.0–1.0,
  "supporting_facts": ["string"],
  "counter_facts": ["string"],
  "publisher_interest": {
    "who_might_care": ["string"],
    "why_now": ["string"],
    "risk_flags": ["string"],
    "next_actions": ["string"]
  }
}
```

⸻

## 3. Архетипы (thesis_archetype)

### 3.1. Допустимые значения (СТРОГО)

- `early_publisher_search`
- `late_pivot_after_release`
- `weak_signal_exploration`
- `opportunistic_outreach`
- `high_intent_low_quality`
- `unclear_intent`

❌ `marketing_distress` — ЗАПРЕЩЁН (даже если кажется логичным)

⸻

### 3.2. Единые временные пороги (ИНВАРИАНТ)

```
FRESH_DAYS = 60
WEAK_DAYS = 90
```

Запрещено использовать другие числа.

⸻

### 3.3. Жёсткий приоритет правил (сверху вниз)

1. `released + свежие behavioral_intent ≤ 60` → `late_pivot_after_release`
2. `demo | coming_soon + свежие ≤ 60` → `early_publisher_search`
3. `свежесть > 90` → `weak_signal_exploration`
4. `свежие сигналы без чёткого паттерна` → `opportunistic_outreach`
5. `intent > 0 и quality == 0` → `high_intent_low_quality`
6. иначе → `unclear_intent`

⚠️ `high_intent_low_quality` — ТОЛЬКО fallback, никогда не раньше.

⸻

## 4. Publisher Status — нормализация понятия «издатель»

### 4.1. Единственный источник истины

`steam_app_cache.publishers`

### 4.2. Нормализация

- `[]` → `self_published`
- `["X"]` → `has_publisher`
- `NULL` → `unknown`

### 4.3. Где возвращается

- **list:**
  - `publisher_status_code`
  - `publisher_status` (RU)
- **detail:**
  - `publisher_status_code`
  - `publisher_status`

⸻

## 5. Partner-mode (КРИТИЧЕСКОЕ ПРАВИЛО)

### 5.1. Условие

```
publisher_status_code == has_publisher
AND
есть behavioral_intent
```

### 5.2. Что меняется

- ❌ НИГДЕ не использовать формулировку «ищет издателя»
- ✅ Использовать:
  - «ищет партнёра»
  - «co-publishing»
  - «маркетинговый партнёр»
  - «рестарт релиза»

### 5.3. Risk flag (обязательно)

```
"У игры уже есть издатель — запрос может означать co-pub, маркетинг, или рестарт релиза"
```

⸻

## 6. Publisher Interest Map (ядро «мозга»)

### 6.1. Типы издательского интереса (константы)

- `scout_fund`
- `genre_publisher`
- `marketing_publisher`
- `turnaround_publisher`
- `operator_publisher`
- `influencer_partner`

### 6.2. Маппинг archetype → interest

| Archetype | Who might care |
|-----------|----------------|
| `early_publisher_search` | scout, genre, marketing |
| `late_pivot_after_release` | turnaround, marketing, operator |
| `weak_signal_exploration` | scout, genre |
| `opportunistic_outreach` | influencer, marketing |
| `high_intent_low_quality` | marketing, influencer |
| `unclear_intent` | scout (только если intent > 0) |

⸻

## 7. Confidence (0.0–1.0)

### 7.1. Формула (детерминированная)

- `+0.3` если есть свежие `behavioral_intent ≤ 60`
- `+0.2` если `stage` согласуется с архетипом
- `+0.1` если `intent_score > 0`
- `−0.2` если `quality_score == 0`
- `−0.2` если сигналы старше 90 дней

Ограничить `0.0 ≤ confidence ≤ 1.0`.

⸻

## 8. Проверки (ОБЯЗАТЕЛЬНО)

### 8.1. verify_synthetic.sh — инварианты

Скрипт должен проверять:
- `thesis ≠ null`
- `thesis_archetype ∈ whitelist`
- `marketing_distress` не встречается
- partner-mode:
  - при `has_publisher` thesis содержит «партнёр»
  - НЕ содержит «ищет издателя»
  - `risk_flags` содержит фразу про «уже есть издатель»

### 8.2. Любая новая логика → новая секция проверки

⸻

## 9. Запреты (жёстко)

❌ менять gates
❌ менять scoring
❌ менять verdict
❌ менять SQL-фильтры list
❌ добавлять новые таблицы
❌ менять dashboard

⸻

## 10. Definition of Done

- `bash scripts/verify_synthetic.sh` → exit 0
- API не падает
- Формулировки на русском
- Partner-mode работает
- Архетипы стабильны
- Смысл объясним
