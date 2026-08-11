# AI-агент для работы с Excel (ЕВРАЗ-1) — план

Система, отвечающая на вопросы по Excel-файлам с полным объяснением источника ответа
(traceability), без утечки коммерческой тайны (цены на металлы) наружу.

> **Обновление (рефакторинг):** целевая архитектура больше не использует тяжёлый
> RAG-over-cells (chunk-эмбеддинги, BM25, Qdrant, pgvector как обязательные). Вместо этого —
> лёгкое entity-resolution по справочникам, нормализованная факт-таблица `mart.price_facts`
> и read-only доступ к БД для генерации SQL.

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
   (`similarity()`/`%`), без эмбеддингов, без Qdrant/BM25/vector.
3. **Agent Orchestrator** — LangGraph StateGraph:
   `Classifier → Planner → CodeGen → Executor → Verifier → Answer`
   (без RAG-узла; без LangChain-обёртки).
4. **Sandbox/Read-only** — SQL-исполнение через read-only роль `app_readonly`
   (GRANT SELECT на `mart.*`) + statement_timeout.
5. **Traceability** — маппинг результата на конкретные ячейки, полный trace запроса.
6. **API** — FastAPI, endpoints `upload` / `ask` / `trace/{request_id}`,
   auth (API-key) + rate limiting (slowapi), Prometheus `/metrics`.

---

## 3. Этапы реализации

### Этап 1: MVP — «чистые» файлы
**Deliverables:**
- Ingestion: парсинг → нормализация в `mart.price_facts`.
- Entity-resolution по справочникам (без chunk-retrieval).
- SQL-based code generation с read-only валидацией (app_readonly).
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

**entity_embeddings** — компактный справочник эмбеддингов сущностей
`(id, entity_type [item/supplier/period], entity_value, embedding, created_at)`.

**Индексы:** pg_trgm GIN на `mart.price_facts.item_name`/`.supplier`, B-tree на
`(sheet_period)`, `(file_id)`, `(price_type)`.

**Роли:** `app_readonly` (GRANT SELECT на `mart.*`) для Executor-узла.

---

## 5. Миграционный путь

- `raw.*` сохраняется для аудита/переиндексации.
- Старые embedding-таблицы (`chunk_embeddings`, `sheet_embeddings`, `col_emb`) оставлены как
  deprecated на один релиз (миграция добавляет `mart.*`/`entity_embeddings`, не удаляет старые).
- Qdrant/Ollama переведены в опциональный compose-профиль `legacy-vector`.
- RAG-only режим (`mode=rag`) пересобран на entity-resolution (не chunk-retrieval).

---

## 6. Метрики качества

- Accuracy golden-dataset (по SQL-сигнатуре и результату).
- Доля `failed` / `low_confidence`.
- Latency per-node и общий RPS.
- Время индексации файла (до рефакторинга — минуты; после — секунды).
