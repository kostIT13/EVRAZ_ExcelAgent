# EVRAZ Agent

**AI-агент для интеллектуальной работы с Excel-файлами металлургической компании ЕВРАЗ.**

Система позволяет загружать Excel-файлы с ценами на металлы, автоматически нормализовать их в
факт-таблицу (`mart.price_facts`) и отвечать на вопросы на естественном языке через
LangGraph-агент с генерацией SQL.

Архитектура ориентирована на prod-ready: без тяжёлого RAG-over-cells, с лёгким entity-resolution,
read-only доступом к БД для генерации SQL, асинхронным ingestion, наблюдаемостью (Prometheus),
auth и rate limiting.

---

## Содержание

- [Архитектура](#архитектура)
- [Возможности](#возможности)
- [Стек технологий](#стек-технологий)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
- [API](#api)
- [Асинхронный ingestion](#асинхронный-ingestion)
- [Наблюдаемость](#наблюдаемость)
- [Auth и rate limiting](#auth-и-rate-limiting)
- [Безопасность БД (read-only роль)](#безопасность-бд-read-only-роль)
- [Schema Inference](#schema-inference)
- [Golden dataset](#golden-dataset)
- [Секреты](#секреты)
- [Структура проекта](#структура-проекта)
- [Лицензия](#лицензия)

---

## Архитектура

```
Excel файл
    │
    ▼
Schema Inference (LLM, разово на новый формат)
    │  → Template Fingerprint (кэш схем в mart.sheet_templates)
    │  → Human confirmation (для новых форматов)
    ▼
Normalize → raw.cells (аудит) + mart.price_facts (плоская факт-таблица)
    │
    ▼
Entity Resolution (item_name/supplier/sheet_period из mart.price_facts)
    │  + pg_trgm fuzzy-поиск (similarity()/%) по item_name/supplier
    ▼
LangGraph агент: Classifier → Planner → CodeGen → Executor → Verifier → Answer
    │  (без RAG-узла, без Qdrant, без pgvector — сущности передаются в промпт)
    ▼
PostgreSQL (read-only роль app_readonly: GRANT SELECT на mart.*)
```

Ключевые изменения по сравнению с прежней (RAG-over-cells) архитектурой:

- **Удалён RAG-узел** из начала графа. Теперь граф начинается с `Classifier`.
- **Удалены Qdrant, Ollama, pgvector** полностью. Расширение `pg_trgm` включено в Postgres.
- **Entity-resolution**: на ingestion собираются уникальные значения справочников
  (`item_name`, `supplier`, `sheet_period`) напрямую из `mart.price_facts` (десятки–сотни записей).
  В рантайме вопрос сопоставляется с кандидатами через pg_trgm `similarity()`/`%`
  (без эмбеддинг-модели, без BM25-индекса, без RU-лемматизации).
- **Нормализованная схема**: `raw.*` (files/sheets/columns/cells — аудит) и `mart.price_facts`
  (long-таблица фактов), на которой агент генерирует SQL.

---

## Возможности

- Загрузка Excel-файлов (`.xlsx`/`.xls`) с асинхронной фоновой обработкой и опросом статуса.
- Нормализация в `mart.price_facts` (идемпотентная, перезалив файла не дублирует факты).
- LangGraph-агент: Classifier → Planner → CodeGen → Executor → Verifier → Answer.
- Генерация безопасного SQL с read-only ролью `app_readonly` (защита на уровне БД).
- Entity-resolution по справочникам + pg_trgm fuzzy-поиск.
- Schema Inference (LLM) + Template Fingerprint для разнородных форматов таблиц.
- API-key auth + rate limiting (slowapi).
- Prometheus-метрики (`/metrics`) и расширенные query_logs.
- Golden dataset (pytest, marker `golden`) для регрессионного тестирования.

---

## Стек технологий

- **FastAPI** — веб-фреймворк.
- **LangGraph** — явный StateGraph агента (без LangChain-обёртки).
- **PostgreSQL** (pgvector image, но без обязательного vector-расширения) + `pg_trgm`.
- **SQLAlchemy 2.0** (async, asyncpg) + **Alembic**.
- **fastembed** — локальные dense-эмбеддинги (модель через `FASTEMBED_MODEL`).
- **prometheus-client**, **slowapi**, **pytest**.

---

## Быстрый старт

```bash
cp .env.example .env
# заполните .env (LLM, Postgres)

docker compose up --build
# миграции
docker compose exec service alembic upgrade head
```

Сервис поднимется на `:8000`, фронтенд — на `:8080`.

> Примечание: Qdrant и Ollama запускаются только с профилем `legacy-vector`:
> `docker compose --profile legacy-vector up`. Для нового пайплайна они не нужны.

---

## Конфигурация

Основные переменные (полный список — в `.env.example`):

| Переменная | Описание |
|---|---|
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_PRIMARY`, `LLM_MODEL_CHEAP` | LLM-клиент |
| `EMBED_PREFIX_MODE` | `e5` / `nomic` / `none` — префиксы эмбеддинга (для nomic — `search_query:`/`search_document:`) |
| `READONLY_DB_USER`, `READONLY_DB_PASSWORD` | read-only роль Executor-узла |
| `DB_STATEMENT_TIMEOUT_MS` | statement_timeout для БД (отдельно от `REQUEST_TIMEOUT_S`) |
| `API_KEY` | API-ключ для `/files/*` и `/ask/*` (пусто = dev) |
| `RATE_LIMIT_ASK`, `RATE_LIMIT_UPLOAD` | rate limiting (slowapi) |
| `INGESTION_QUEUE_MODE` | `inproc` / `celery` / `arq` |

---

## API

### Управление файлами (`/files/*`)

- `POST /files/upload` — загрузка (асинхронно, возвращает `file_id`).
- `GET /files/{id}/status` — опрос статуса обработки.
- `GET /files` — список.
- `GET /files/{id}` — детали.
- `GET /files/{id}/sheets`, `/columns`, `/cells` — просмотр raw-структуры.
- `POST /files/{id}/reindex` — пересоздание сущностей.
- `POST /files/{id}/sheets/{sheet_id}/infer-schema` — Schema Inference (LLM).
- `POST /files/{id}/sheets/{sheet_id}/confirm-schema` — подтверждение схемы.

### Agent (`/ask/*`)

- `POST /ask` — вопрос к агенту (`mode`: `agent` | `rag` | `auto`).

### Traceability

- `GET /trace/...` — трассировка выполнения графа.

---

## Асинхронный ingestion

Парсинг + нормализация + entity-resolution вынесены из синхронного `/files/upload` в фоновую
очередь (`inproc` по умолчанию; интерфейс совместим с `celery`/`arq`). Клиент получает `file_id`
и опрашивает статус через `GET /files/{id}/status`.

Статусы: `uploaded → processing → ready | failed`.

---

## Наблюдаемость

`GET /metrics` отдаёт метрики Prometheus:

- RPS и латентность `/ask` (по статусу).
- Per-node latency графа (classifier/planner/codegen/executor/verifier/answer).
- Доля `failed` / `low_confidence`.
- Token usage LLM.

`query_logs` расширены полями: latency по узлам, token usage/стоимость, текст ошибки при `failed`.

---

## Auth и rate limiting

- `/files/*` и `/ask/*` защищены API-ключом (заголовок `X-API-Key`), проверка через
  `verify_api_key`. Если `API_KEY` пуст — auth отключён (dev-режим).
- Rate limiting через slowapi (`RATE_LIMIT_ASK`, `RATE_LIMIT_UPLOAD`).

---

## Безопасность БД (read-only роль)

Executor-узел подключается к PostgreSQL через роль `app_readonly` с `GRANT SELECT` только на
`mart.*`. Это защита на уровне БД в дополнение к keyword-blacklist валидации SQL в `codegen_node`.
`statement_timeout` задаётся на уровне сессии (`DB_STATEMENT_TIMEOUT_MS`).

---

## Schema Inference

Для разнородных форматов таблиц (сдвинутые шапки, вложенные заголовки, merged cells):

1. `template_fingerprint.compute_sheet_fingerprint` считает отпечаток структуры листа.
2. Если отпечаток совпадает с подтверждённым шаблоном в `mart.sheet_templates` — схема
   применяется без вызова LLM.
3. Иначе `schema_inference.schema_inference_service.infer` вызывает LLM со структурным выводом
   (Pydantic `SheetSchema`), результат сохраняется как `pending_confirmation`.
4. Пользователь подтверждает/правит схему через `confirm-schema` (статус → `confirmed`).

---

## Golden dataset

`tests/golden_questions.json` — набор вопросов с ожидаемыми SQL-сигнатурами/результатами.
`tests/test_golden_dataset.py` прогоняет их через агента (marker `golden`, включается `--golden`).

```bash
pytest tests/            # юнит-проверки (без LLM)
pytest --golden tests/   # интеграционные golden-тесты (требуют LLM и данные)
```

Запускайте в CI при каждом изменении промптов/схемы.

---

## Секреты

Прод-секреты (LLM API-ключ, пароли БД, `READONLY_DB_PASSWORD`, `API_KEY`) не должны лежать в
`.env` в пайплайне деплоя. Интеграция с secrets-менеджером (Hashicorp Vault / облачный аналог):

- Секреты загружаются в рантайм из Vault (или env-injection в CI/CD).
- `READONLY_DB_PASSWORD` создаётся в БД отдельной операцией и не коммитится.
- Пример (Vault): приложение читает секреты по пути
  `secret/evraz/prod` и передаёт их в `Settings` до создания движков БД.

---

## Структура проекта

```
src/
  main.py                    # FastAPI app, lifespan, /metrics, /health
  api/                       # роутеры (files, agent, trace, schema, security, ratelimit)
  core/
    config.py                # настройки (включая read-only роль, rate limits)
    db/                      # engine, session, models (raw + mart + entity_embeddings)
    excel/                   # parser, normalize, schema_inference, template_fingerprint
    metrics.py               # Prometheus-метрики
  services/
    agent/                   # LangGraph: graph.py, nodes (classifier/planner/codegen/executor/verifier)
    mart/                    # normalizer raw->mart
    excel/                   # ingestion_service, ingestion_queue, repository
    rag/                     # entity_embeddings (лёгкий entity-resolution), embedder
tests/                       # golden dataset + pytest
alembic/                     # миграции
scripts/init-db/             # расширения Postgres (pg_trgm, vector legacy)
```

---

## Лицензия

Проприетарная (внутренний проект).
