# TZ_SIGNAL_INGESTION_MASTER.md

## Цель

Обеспечить массовое и устойчивое наполнение `games` и `signals` для работы Brain System и отображения большого количества игр в dashboard.

⸻

## 1. Принцип

- Brain НЕ меняется
- Все verdict / thesis / confidence — downstream
- Ingestion — upstream слой

⸻

## 2. Минимальные цели v1

- `games ≥ 2 000`
- `apps_with_signals ≥ 100`
- `/api/v1/deals/list` возвращает сотни строк

⸻

## 3. Ingestion Vectors

### Vector A — Steam Games Index

- **Источник:** Steam API / scrape
- **Все released + upcoming**
- **Только факты (без сигналов)**
- **Upsert, идемпотентно**

⸻

### Vector B — Reddit Signals

- **Сабреддиты:**
  - `IndieGaming`
  - `Steam`
  - `PlayMyGame`
- **Сигнал = post/comment с Steam link**
- **Вес:** post > comment

⸻

### Vector C — Review Velocity

- **7d vs 30d**
- **Сигнал при аномалии**
- **Используется Brain напрямую**

⸻

## 4. Таблицы (существующие)

- `games`
- `signals`
- `deal_intent_signal`

❗ **Новые таблицы НЕ добавлять**

⸻

## 5. Инварианты

- `/list` не содержит thesis
- Brain logic не трогать
- Только ingestion + data volume

⸻

## 6. Acceptance Criteria

- `apps_with_signals >= 100`
- `SELECT count(*) FROM games >= 2000`
- `/api/v1/deals/list` returns `> 200` items

⸻

## 7. Out of scope

- UI
- Ranking
- Monetization
- ML

⸻

## Конец документа
