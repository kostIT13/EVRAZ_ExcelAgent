# AI-агент для работы с Excel (ЕВРАЗ-1) — план

Система, отвечающая на вопросы по Excel-файлам с полным объяснением источника ответа
(traceability), без утечки коммерческой тайны (цены на металлы) наружу.

---

## 1. Цели и ограничения

**Цель:** точность ≥85% на 5 типах запросов, с полным traceability ответа.

**Жёсткие ограничения:**
- Данные — коммерческая тайна (цены на металлы). Сырые цифры наружу не уходят.
- Файлы — «грязные»: multi-level headers, merged cells, разные структуры листов.
- Ответ должен быть traceable: пользователь видит, из какой ячейки взят результат.
- Latency ≤ 15 сек на типичный запрос, ≤ 60 сек на сложный cross-sheet.

**Не-цели MVP:**
- Работа с макросами (.xlsm) — откладываем.
- Real-time коллаборация.
- Мобильный клиент.

---

## 2. Архитектура (слои)

1. **Ingestion** — парсинг Excel → Schema Inference (LLM, разово) + Template Fingerprint
   (кэш схем) → нормализация в `mart.price_facts` (идемпотентно). Фоновая очередь задач.
2. **Entity Resolution** — уникальные значения справочников (`item_name`, `supplier`,
   `sheet_period`) собираются напрямую из `mart.price_facts` + pg_trgm fuzzy-поиск
   (`similarity()`/`%`), без эмбеддингов.
3. **Agent Orchestrator** — LangGraph StateGraph:
   `Classifier → Disambiguation → Planner → CodeGen → Executor → Verifier → Answer`
   (entity-resolution выполняется внутри Classifier/Planner; без LangChain-обёртки).
4. **SQL-исполнение** — Executor-узел выполняет SQL под основной ролью БД
   с keyword-blacklist валидацией + statement_timeout.
5. **Traceability** — маппинг результата на конкретные ячейки, полный trace запроса.
6. **API** — FastAPI, endpoints `upload` / `ask` / `trace/{request_id}`,
   auth (API-key) + rate limiting (slowapi), Prometheus `/metrics`.

---

## 3. Этапы реализации

### Этап 1: MVP — «чистые» файлы
**Deliverables:**
- Ingestion: парсинг → нормализация в `mart.price_facts`.
- Entity-resolution по справочникам (без chunk-retrieval).
- SQL-based code generation с keyword-blacklist валидацией.
- FastAPI с endpoints `upload`/`ask`.
- Бенчмарк на 30 кейсах (6 на каждый тип запроса).
- Traceability: ответ + список использованных листов/ячеек.

**Критерий готовности:** ≥75% accuracy, latency p95 ≤ 20 сек.

### Этап 2: V1 — «грязные» файлы
**Deliverables:**
- Merged cells classifier + multi-level header resolver (Schema Inference).
- Template Fingerprint: кэш подтверждённых LLM-схем в `mart.sheet_templates`.
- Human confirmation схемы (confirm-schema endpoint + UI).
- Асинхронный ingestion (очередь) + статус + polling.
- Кэш ответов.
- Audit log + feedback loop.
- Расширение бенчмарка до 100 кейсов.

### Этап 3: V2 — prod-ready
- Наблюдаемость: Prometheus `/metrics`, latency по узлам, token usage.
- Auth + rate limiting.
- Secrets-менеджер (Vault).
- Golden dataset + pytest в CI.

---

## 4. Итоговая схема данных

**raw.\*** (аудит, без изменений): `files`, `sheets`, `columns`, `cells`.

**mart.\*** (нормализованная, read-only для агента):
- `mart.price_facts` — long-таблица фактов
  `(id, file_id, sheet_id, sheet_period, item_name, supplier, price_type, value, currency, unit, source_row_ref)`.
- `mart.sheet_templates` — кэш подтверждённых LLM-схем
  `(fingerprint, schema_json, status, confidence, confirmed_by, confirmed_at)`.

**entity_dictionary** — справочник канонических сущностей
`(id, canonical_name, aliases, category, description, created_at, updated_at)`.

**query_cache** — кэш «нормализованный вопрос → SQL → результат».

**Индексы:** pg_trgm GIN на `mart.price_facts.item_name`/`.supplier`, B-tree на
`(sheet_period)`, `(file_id)`, `(price_type)`.

**Безопасность SQL:** keyword-blacklist валидация в codegen_node; Executor
подключается под основной ролью БД с `statement_timeout`.

---

## 5. Миграционный путь

- `raw.*` сохраняется для аудита/переиндексации.
- Устаревшие embedding-таблицы удалены (миграция `remove_vector_tables`).
- Векторные сервисы и таблицы (`chunk_embeddings`, `sheet_embeddings`, `col_emb`,
  `entity_embeddings`) больше не используются и удалены из схемы.
- Agent-режим пересобран на entity-resolution (без chunk-retrieval).

---

## 6. Метрики качества

- Accuracy golden-dataset (по SQL-сигнатуре и результату).
- Доля `failed` / `low_confidence`.
- Latency per-node и общий RPS.
- Время индексации файла (секунды).
