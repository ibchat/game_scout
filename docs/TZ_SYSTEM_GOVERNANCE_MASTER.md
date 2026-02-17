# TZ_SYSTEM_GOVERNANCE_MASTER.md

**Owner:** System  
**Purpose:** Канонический документ для governance системы Game Scout, определяющий правила merge, метрики и процессы.

---

## 0. Принципы

1. **Каноничность:** Этот документ имеет приоритет над любыми другими ТЗ и процессами.
2. **Двухгейтовая система:** Merge контролируется через Stability Gate и Progress Gate.
3. **Запрет самовольных решений:** Cursor НЕ имеет права выбирать Mode без ссылки на этот документ.

---

## 1. Mode B: Two-Gate System (активный режим)

### 1.1 Stability Gate (блокирует merge)

**Назначение:** Гарантировать стабильность системы, отсутствие регрессий.

**Критерии блокировки:**
- ❌ Любой verify скрипт падает с ошибкой стабильности (не метрики прогресса)
- ❌ `dup > 0` для любого source
- ❌ `/list` содержит `thesis` или `thesis_explain`
- ❌ `/shortlist` содержит запрещенные поля
- ❌ Ingestion не идемпотентен
- ❌ `/list count=0` при наличии данных в БД (регрессия gates/filters)
- ❌ Любые другие регрессии функциональности

**Stability Gate = PASS, если:**
- ✅ Все verify скрипты проходят проверки стабильности (exit 0 для стабильности)
- ✅ `dup=0` для всех source
- ✅ Контракты API соблюдены
- ✅ Идемпотентность работает
- ✅ Нет регрессий функциональности

**Stability Gate = FAIL → MERGE-READY = NO (блокирует merge)**

---

### 1.2 Progress Gate (НЕ блокирует merge)

**Назначение:** Отслеживать прогресс по целевым метрикам, обязателен к отчету.

**Критерии:**
- `apps_with_signals >= 100` (или другая целевая метрика из ТЗ)
- Другие метрики прогресса из конкретных ТЗ

**Progress Gate = PASS, если:**
- ✅ Целевая метрика достигнута

**Progress Gate = FAIL, если:**
- ❌ Целевая метрика не достигнута

**Progress Gate = FAIL НЕ блокирует merge**, но:
- Обязателен к отчету в PR Review
- Должен быть план достижения метрики

---

## 2. Правила для verify-скриптов

### 2.1 Явная разметка секций по Gate (ОБЯЗАТЕЛЬНО)

**Обязательное правило:** Все verify-скрипты должны явно размечать секции по Gate.

**Stability Gate секции:**
- **S1–S12** (или по факту как в скрипте до Progress Gate)
- **Любые контрактные проверки** (API контракты, отсутствие дублей, идемпотентность)
- Блокируют merge (устанавливают `fail=1` при FAIL)
- Влияют на exit code скрипта
- Примеры: проверка дублей, контракты API (`/list` не содержит `thesis`), идемпотентность, регрессии, контракт `/list count > 0`

**Progress Gate секции:**
- **S13+** (или по факту как в скрипте после Stability Gate)
- **Метрики прогресса** (`apps_with_signals >= 100`, seed coverage, масштабирование)
- НЕ блокируют merge (НЕ устанавливают `fail=1`)
- НЕ влияют на exit code скрипта
- Только отчет о прогрессе
- Примеры: `apps_with_signals >= 100`, проверка после seed, другие целевые метрики из ТЗ

**Правило для exit code:**
- Если все Stability Gate секции (S1–S12) PASS → exit code = 0
- Если хотя бы одна Stability Gate секция FAIL → exit code = 1
- Progress Gate секции (S13+) НИКОГДА не влияют на exit code

**Для verify_synthetic.sh конкретно:**
- **Stability Gate:** S1–S12 (включая S13 - контракт `/list count > 0`)
- **Progress Gate:** S14+ (apps_with_signals >= 100, seed coverage)

### 2.2 Разделение проверок

**Stability checks (блокируют merge):**
- Отсутствие дублей
- Соблюдение контрактов API
- Идемпотентность
- Отсутствие регрессий
- Наличие данных в `/list` при наличии данных в БД (см. п.2.3)

**Progress checks (только отчет):**
- `apps_with_signals >= 100`
- Другие целевые метрики из ТЗ

### 2.3 Контракт `/list` endpoint (минимальный смысловой контракт)

**Обязательное требование:**
- При `min_intent_score=0&min_quality_score=0` endpoint `/api/v1/deals/list` должен возвращать `count > 0`
- Это минимальный смысловой контракт: при нулевых порогах должна быть хотя бы одна игра
- Если `count = 0` при этих параметрах → это регрессия (Stability Gate FAIL)

**Если `count = 0`:**
- Обязателен breakdown `excluded_reasons` в отчёте PR Review
- Нужно объяснить, почему все игры исключены gates/filters
- Если данные есть в БД, но все исключены → это регрессия, требующая фикса
- Проверка должна выводить `excluded_reasons` из ответа API для диагностики

**Проверка в verify-скриптах:**
- Stability Gate секция должна проверять: `/list?min_intent_score=0&min_quality_score=0` → `count > 0`
- Если FAIL → установить `fail=1` и вывести `excluded_reasons` из ответа API
- Недостаточно просто проверить `count=1` — нужно проверять `count > 0` при нулевых порогах

---

## 3. Формат отчета PR Review

**Обязательный формат:**

```
MERGE-READY: YES | NO
Stability Gate: PASS | FAIL
Progress Gate: PASS | FAIL
apps_with_signals: X / 100
```

**Интерпретация:**
- `MERGE-READY = NO` только если `Stability Gate = FAIL`
- `Progress Gate = FAIL` не блокирует merge, но обязателен к отчету

---

## 4. Запреты

1. ❌ Запрещено выбирать Mode без ссылки на этот документ
2. ❌ Запрещено блокировать merge из-за недостижения целевой метрики прогресса
3. ❌ Запрещено игнорировать регрессии функциональности
4. ❌ Запрещено писать "WARNING" без анализа для `/list count=0`

---

## 5. Изменение Mode

**Только через:**
1. Обновление этого документа
2. Явное указание в ТЗ конкретного PR
3. Согласование с owner системы

**Cursor НЕ имеет права самовольно менять Mode.**

---

## 6. Примеры

### Пример 1: Stability Gate FAIL
```
MERGE-READY: NO
Stability Gate: FAIL (причина: /list count=0 при наличии данных в БД)
Progress Gate: FAIL
apps_with_signals: 28 / 100
```

### Пример 2: Stability Gate PASS, Progress Gate FAIL
```
MERGE-READY: YES
Stability Gate: PASS
Progress Gate: FAIL
apps_with_signals: 28 / 100
```

### Пример 3: Оба PASS
```
MERGE-READY: YES
Stability Gate: PASS
Progress Gate: PASS
apps_with_signals: 100 / 100
```

---

**Конец документа**
