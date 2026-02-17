# TZ_PR_REVIEW_FIX_LOOP.md

**Owner:** Cursor  
**Goal:** Перед любым merge/push в ветку — гарантированно прогонять тесты, ловить регрессии, фиксить и прикладывать доказательства в PR/ответ.

---

## 0) Инварианты (нельзя ломать)

1) `/api/v1/deals/list` НЕ должен возвращать `thesis` и `thesis_explain`.
2) `apps/api/static/game_scout_dashboard.html` НЕ менять.
3) Никаких новых миграций/таблиц (если не оговорено отдельно).
4) Все ingestion-скрипты должны быть **идемпотентны** (повторный запуск не создает дублей и не "раздувает" метрики неправильно).
5) Brain logic не менять (если это PR не про Brain).

---

## 1) Pre-flight: чистое состояние + сервис живой

### 1.1 Pull + Restart
```bash
git pull
docker compose restart api
curl -4 -sS "http://127.0.0.1:8000/api/v1/health" | jq .
```

**AC:** health = healthy

### 1.2 Логи старта (на случай flake)
```bash
docker compose logs api --tail 120
```

⸻

## 2) Канонический прогон тестов (must-run)

Запускать в таком порядке:

```bash
bash scripts/verify_synthetic.sh ; echo "verify_synthetic=$?"
bash scripts/verify_shortlist.sh ; echo "verify_shortlist=$?"
bash scripts/verify_signal_coverage.sh
```

Если реализуется ingestion-вектор (A/B/C) — добавить verify для него:

```bash
bash scripts/verify_signal_ingestion_reddit.sh ; echo "verify_ingestion_reddit=$?"
# или youtube
bash scripts/verify_signal_ingestion_youtube.sh ; echo "verify_ingestion_youtube=$?"
# или steam reviews
bash scripts/verify_signal_ingestion_steam_reviews.sh ; echo "verify_ingestion_steam=$?"
```

**AC:** все exit code = 0.

⸻

## 3) Sanity checks (SQL + API)

### 3.1 apps_with_signals (главная метрика)

```bash
docker compose exec postgres psql -U postgres -d game_scout -c \
"SELECT COUNT(DISTINCT app_id) AS apps_with_signals FROM deal_intent_signal;"
```

**AC:** метрика не уменьшилась относительно baseline PR.
Если в ТЗ цель задана (например >=100) — должна быть достигнута.

### 3.2 Проверка дублей по (source,url)

```bash
docker compose exec postgres psql -U postgres -d game_scout -c \
"SELECT source, COUNT(*) total, COUNT(DISTINCT url) uniq, (COUNT(*)-COUNT(DISTINCT url)) dup
 FROM deal_intent_signal
 GROUP BY source
 ORDER BY total DESC;"
```

**AC:** dup = 0 для всех source.

### 3.3 /list не содержит thesis

```bash
curl -4 -sS "http://127.0.0.1:8000/api/v1/deals/list?limit=1&synthetic_only=true&min_intent_score=0&min_quality_score=0" \
| jq '{has_thesis: (.games[0] | has("thesis")), keys:(.games[0]|keys)}'
```

**AC:** has_thesis = false

### 3.4 Контракт /list: count > 0 при min_intent_score=0&min_quality_score=0

```bash
curl -4 -sS "http://127.0.0.1:8000/api/v1/deals/list?limit=50&min_intent_score=0&min_quality_score=0" \
| jq '{status, count, excluded_reasons}'
```

**AC:** 
- status = "ok"
- count > 0
- Если count = 0 → обязателен breakdown excluded_reasons в отчёте

### 3.5 /shortlist контракт (без запрещенных полей)

```bash
curl -4 -sS "http://127.0.0.1:8000/api/v1/deals/shortlist?limit=1" \
| jq '.items[0] | {keys:(keys), has_thesis:has("thesis"), has_thesis_explain:has("thesis_explain"), has_headline:has("headline"), has_why_now:has("why_now")}'
```

**AC:** has_thesis=false, has_thesis_explain=false, has_headline=false, has_why_now=false

⸻

## 4) Идемпотентность ingestion (обязательно для ingestion PR)

### 4.1 Первый запуск ingestion

(пример — Reddit)

```bash
curl -4 -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_reddit?days=90" | jq .
bash scripts/verify_signal_coverage.sh
```

### 4.2 Второй запуск ingestion (повтор)

```bash
curl -4 -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_reddit?days=90" | jq .
bash scripts/verify_signal_coverage.sh
```

### 4.3 SQL контроль дублей после повторного запуска

Повторить пункт 3.2.

**AC:** повторный запуск не создает дублей, dup=0, метрики растут только если реально появились новые url/app_id.

⸻

## 5) Если что-то упало — протокол фикса (обязателен)

1. Зафиксировать точный шаг и его stdout/stderr.
2. Показать логи:
   ```bash
   docker compose logs api --tail 200
   ```
3. Минимальный фикс (smallest diff), без "рефакторинга ради красоты".
4. Повторить разделы 1–4 полностью.
5. Только после этого commit.

⸻

## 6) Формат отчета, который Cursor обязан приложить в PR/ответ

**Согласно TZ_SYSTEM_GOVERNANCE_MASTER.md: обязательный формат:**

```
MERGE-READY: YES | NO
Stability Gate: PASS | FAIL
Progress Gate: PASS | FAIL
apps_with_signals: X / 100
```

**Дополнительные блоки:**

### A) Verify results
- verify_synthetic=0 (stability checks)
- verify_shortlist=0
- verify_signal_coverage: apps_with_signals=…

### B) Key SQL metrics
- apps_with_signals=…
- duplicates table (source/total/uniq/dup)

### C) Contract checks
- /list has_thesis=false
- /shortlist no forbidden fields

### D) Idempotency (если ingestion)
- before/after counts + dup=0

⸻

## 7) Commit правила

- 1 commit на логическую единицу (ingestion/verify/bugfix)
- Сообщение: `feat:` или `fix:` или `test:` (как в репо принято)
- Никаких временных `*.bak` файлов в git

⸻

## Definition of Done

- [ ] Все verify проходят (exit 0)
- [ ] dup=0 по (source,url)
- [ ] /list без thesis
- [ ] /shortlist контракт соблюден
- [ ] ingestion идемпотентен (если применимо)
- [ ] Отчет по формату из раздела 6 приложен

---

## 8) Merge-Ready Rule (ЖЕСТКОЕ ПРАВИЛО)

**Согласно TZ_SYSTEM_GOVERNANCE_MASTER.md: Mode B (Two-Gate System)**

**Важно:** Verify скрипты должны быть детерминированными и не флапать от "данные уже есть" или внешних факторов (rate limiting). MERGE-READY можно писать только если все Stability verify exit 0.

### Stability Gate (блокирует merge)

**MERGE-READY = NO, если Stability Gate = FAIL:**
- ❌ Любой verify скрипт падает с ошибкой стабильности
- ❌ dup > 0 для любого source
- ❌ /list содержит `thesis` или `thesis_explain`
- ❌ /shortlist содержит запрещенные поля
- ❌ Ingestion не идемпотентен (если применимо)
- ❌ /list count=0 при наличии данных в БД (регрессия)

**Stability Gate = PASS, если:**
- ✅ Все stability checks пройдены
- ✅ dup=0 для всех source
- ✅ Контракты API соблюдены
- ✅ Идемпотентность работает
- ✅ Нет регрессий функциональности

### Progress Gate (НЕ блокирует merge)

**Progress Gate отслеживает:**
- `apps_with_signals >= 100` (или другая целевая метрика)

**Progress Gate = FAIL НЕ блокирует merge**, но обязателен к отчету.

**MERGE-READY = YES, если:**
- ✅ Stability Gate = PASS
- ✅ (Progress Gate может быть FAIL, это не блокирует)

**Запрещено писать "готово к merge" при Stability Gate = FAIL.**

---

## 10) Запрет "warning" по /list count=0 без анализа

**Запрещено:**
- ❌ Писать "WARNING: /list count=0" без анализа причин
- ❌ Игнорировать count=0 как "не критично"

**Обязательно:**
- ✅ Проверить, есть ли данные в БД: `SELECT COUNT(*) FROM deal_intent_game WHERE intent_score > 0`
- ✅ Проверить gates/filters: почему игры не проходят фильтры
- ✅ Если данные есть в БД, но count=0 → это BUG, MERGE-READY = NO
- ✅ Если данных нет в БД → это не bug, но нужно объяснить в отчете

**Анализ count=0:**
```bash
# Проверка данных в БД
docker compose exec postgres psql -U postgres -d game_scout -c \
"SELECT COUNT(*) as total_games, COUNT(*) FILTER (WHERE intent_score > 0) as with_intent FROM deal_intent_game;"

# Проверка сигналов
docker compose exec postgres psql -U postgres -d game_scout -c \
"SELECT COUNT(*) as signals, COUNT(DISTINCT app_id) as apps FROM deal_intent_signal WHERE app_id IS NOT NULL;"
```

**Если count=0, но данные есть в БД → это регрессия, требующая фикса.**
