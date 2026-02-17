# TZ_SIGNAL_INGESTION_VECTOR_A_EXEC_V1.md

**Owner:** Cursor  
**Goal:** Увеличить `apps_with_signals` с ~28 до ≥100, не меняя Brain/скоринг/гейты.

**Status:** EXEC v1 (Execution)

---

## 0) Цель (бизнес-результат)

Увеличить `apps_with_signals` (уникальных `app_id` в `deal_intent_signal`) с ~28 до ≥100, не меняя Brain/скоринг/гейты.

### Definition of Done (DoD)

- ✅ `apps_with_signals >= 100` (Progress Gate — НЕ блокирует merge, но обязателен в отчёте)
- ✅ `dup=0` по `(source, url)` (Stability Gate — блокирует merge)
- ✅ `/api/v1/deals/list?limit=50&min_intent_score=0&min_quality_score=0` возвращает `count > 0` (Stability Gate — блокирует merge)
- ✅ `verify_synthetic.sh` PASS по Stability Gate
- ✅ Идемпотентность: повторный запуск collectors не увеличивает total signals за счёт дублей

---

## 1) Инварианты (ЗАПРЕЩЕНО)

### Нельзя:
- ❌ Менять Brain logic (архетипы, confidence, thesis, shortlist, gates/filters, verdict)
- ❌ Менять контракт `/api/v1/deals/list`, `/detail`, `/shortlist` (кроме добавления новых ingestion endpoints)
- ❌ Добавлять миграции / новые таблицы
- ❌ Ослаблять проверку `dup=0`
- ❌ Говорить "merge-ready", если Stability Gate FAIL

### Можно:
- ✅ Расширять ingestion: Reddit, Steam reviews, synthetic seeding
- ✅ Добавлять/улучшать scripts verify и ingestion
- ✅ Добавлять новые docs в `docs/`

---

## 2) Governance: Mode B (Two-Gate System)

### Stability Gate (blocking):
- verify scripts exit 0
- `dup=0`
- `/list count > 0` при нулевых порогах
- API contracts OK

### Progress Gate (non-blocking):
- `apps_with_signals >= 100` (цель роста)
- "сколько добавили app_id за прогон", "какие источники дали прирост"

**Cursor обязан в отчёте писать:**
- `MERGE-READY: YES/NO`
- `Mode: B`
- `Stability Gate: PASS/FAIL`
- `Progress Gate: PASS/FAIL`
- значения метрик

---

## 3) Вектор A — Что именно реализовать

### A1) Reddit Collector Expansion (P1)

**Цель:** добыть основную массу новых app_id через расширение Reddit.

**Требования:**

1. **Расширить сабреддиты (минимум):**
   - `r/Steam`
   - `r/pcgaming`
   - `r/SteamDeck`
   - `r/Games`
   - `r/IndieGaming`
   - `r/IndieDev`
   - `r/GameDeals`
   - `r/Gaming`
   - Оставить текущие (если есть)

2. **Увеличить исторический диапазон:**
   - параметр `days` минимум до 90 (а лучше 180, если быстро)

3. **Увеличить лимит постов:**
   - параметр `limit_per_sub` минимум 500 (а лучше 1000)

4. **Извлечение app_id:**
   - поддержать `store.steampowered.com/app/<id>`
   - поддержать `steamcommunity.com/app/<id>`
   - поддержать "steam app id" из текста, только если рядом есть "steam" (защита от мусора)
   - если app_id не найден — сигнал не сохранять

5. **Сигналы:**
   - минимум сохранять `behavioral_intent` или `intent_keyword` (что уже есть)
   - `url` — источник (пост/коммент)
   - `text` — обрезать до 280 символов (или текущие правила проекта)
   - `published_at`/`created_at` корректно считать

6. **Идемпотентность:**
   - не вставлять дубликаты по `(source, url)`
   - если такой url уже есть — пропустить

**Acceptance для A1:**
- после прогона `apps_with_signals` увеличивается минимум на +30 (если есть доступ к данным)
- `dup=0`

---

### A2) Reddit Comments Expansion (P1.5)

Извлекать сигналы не только из постов, но и из топ-комментариев.

**Требования:**
- для каждого поста брать top N комментариев (N=20 достаточно)
- искать Steam links и intent keywords
- сохранять сигнал по url комментария
- те же правила идемпотентности

**Acceptance:**
- прирост уникальных app_id +10 дополнительно (если данные есть)

---

### A3) Steam Reviews as Source (P2)

Здесь не нужен внешний API — у тебя уже есть таблицы с review daily.

**Идея:**
- взять игры с аномалией review velocity или ростом review volume
- извлечь "intent" из метаданных/событий? (минимально: создавать signals типа `review_spike` как proxy intent)

**Но если в `deal_intent_signal` нет типа `review_spike`, тогда:**
- использовать существующий тип `behavioral_intent` и в snippet писать "review velocity spike detected"
- url можно сделать synthetic вида `steam_reviews://app/<id>/spike/<date>`

**Acceptance:**
- добавить минимум +20 app_id сигналов из `review_spike`
- не ломать schema, не добавлять новые таблицы

---

### A4) Synthetic Expansion (P4, safety net)

Расширить `scripts/seed_more_signals.sh`:
- выбирать существующие games (случайно или top по `recent_reviews_30d`)
- добавлять сигналы в `deal_intent_signal` так, чтобы:
  - `apps_with_signals` добивался до 100, если реальные источники не дали
  - идемпотентно (не дублировать по `source,url`)

**Acceptance:**
- повторный запуск не увеличивает `apps_with_signals` бесконечно
- seed может поднять `apps_with_signals` до цели, но должен отчётно помечаться как synthetic contribution

---

## 4) Новые/обновлённые скрипты

### 4.1 `scripts/verify_signal_ingestion.sh` (NEW)

Печатает:
- `apps_with_signals`
- `total signals`
- `dup table (source,url)`
- `top sources by unique app_id`
- `top 20 app_id by signals count`

**Exit code:**
- FAIL если `dup>0`
- FAIL если `/list count=0` при нулевых порогах
- PASS иначе
- `apps_with_signals>=100` — печатать как Progress Gate PASS/FAIL, но не влияет на exit code (Mode B)

### 4.2 Обновить `scripts/verify_synthetic.sh`
- оставить Stability Gate проверки (S1…S13)
- Progress Gate (`apps_with_signals>=100`) — отдельная секция, НЕ блокирует merge

---

## 5) API endpoints (если уже есть — доработать)

Нужно иметь возможность запускать ingestion командами:
- `POST /api/v1/deals/signals/collect_reddit?days=90&limit_per_sub=500&include_comments=true`
- `POST /api/v1/deals/signals/collect_steam_reviews?days=180` (если делаем A3)
- (опционально) `POST /api/v1/deals/signals/seed?target_apps_with_signals=100`

Все endpoints должны быть идемпотентны.

---

## 6) Финальный PR Review & Fix Loop (обязателен)

После реализации Cursor обязан:
1. Прогнать verify:
   - `bash scripts/verify_synthetic.sh ; echo $?`
   - `bash scripts/verify_shortlist.sh ; echo $?`
   - `bash scripts/verify_signal_ingestion.sh ; echo $?`
2. Вывести отчет строго в формате:
   - Verify results
   - Key SQL metrics
   - Contract checks
   - Idempotency
   - MERGE-READY + Mode + Gates

**Запрещено писать "готово к merge", если Stability FAIL.**

---

## 7) Команды для проверки

```bash
docker compose restart api
curl -sS http://127.0.0.1:8000/api/v1/health | jq .

# Run ingestion
curl -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_reddit?days=90&limit_per_sub=500&include_comments=true"

# Verify
bash scripts/verify_synthetic.sh ; echo $?
bash scripts/verify_shortlist.sh ; echo $?
bash scripts/verify_signal_ingestion.sh ; echo $?

# Metrics
bash scripts/verify_signal_coverage.sh
```

---

**Конец документа**
