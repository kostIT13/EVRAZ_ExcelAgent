# EVRAZ Agent

**AI-агент для интеллектуальной работы с Excel-файлами металлургической компании ЕВРАЗ.**

Система позволяет загружать Excel-файлы с ценами на металлы, автоматически нормализовать их в
факт-таблицу (`mart.price_facts`) и отвечать на вопросы на естественном языке через
LangGraph-агент с генерацией SQL.

Архитектура ориентирована на prod-ready: лёгкое entity-resolution по справочникам,
read-only доступом к БД для генерации SQL, асинхронный ingestion, наблюдаемость (Prometheus),
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
    │  (entity-resolution выполняется внутри Classifier/Planner)
    ▼
PostgreSQL (mart.* — SQL выполняет Executor-узел)
```

Архитектура построена вокруг нормализованной факт-таблицы и генерации SQL без тяжёлых
векторных поисков:

- **Entity-resolution**: на ingestion собираются уникальные значения справочников
  (`item_name`, `supplier`, `sheet_period`) напрямую из `mart.price_facts` (десятки–сотни записей).
  В рантайме вопрос сопоставляется с кандидатами через pg_trgm `similarity()`/`%`
  (без эмбеддинг-модели, без BM25-индекса, без RU-лемматизации).
- **Нормализованная схема**: `raw.*` (files/sheets/columns/cells — аудит) и `mart.price_facts`
  (long-таблица фактов), на которой агент генерирует SQL.
- **Кэш ответов**: нормализованный вопрос → SQL → результат хранится в `query_cache`.

---

## Возможности

- Загрузка Excel-файлов (`.xlsx`/`.xls`) с асинхронной фоновой обработкой и опросом статуса.
- Нормализация в `mart.price_facts` (идемпотентная, перезалив файла не дублирует факты).
- LangGraph-агент: Classifier → Disambiguation → Planner → CodeGen → Executor → Verifier → Answer.
- Генерация безопасного SQL с keyword-blacklist валидацией в `codegen_node`.
- Entity-resolution по справочникам + pg_trgm fuzzy-поиск.
- Schema Inference (LLM) + Template Fingerprint для разнородных форматов таблиц.
- API-key auth + rate limiting (slowapi).
- Prometheus-метрики (`/metrics`) и расширенные query_logs.
- Golden dataset (pytest, marker `golden`) для регрессионного тестирования.

---

## Стек технологий

- **FastAPI** — веб-фреймворк.
- **LangGraph** — явный StateGraph агента (без LangChain-обёртки).
- **PostgreSQL** + `pg_trgm` (fuzzy-поиск для entity-resolution).
- **SQLAlchemy 2.0** (async, asyncpg) + **Alembic**.
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

---

## Конфигурация

Основные переменные (полный список — в `.env.example`):

| Переменная | Описание |
|---|---|
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_PRIMARY`, `LLM_MODEL_CHEAP` | LLM-клиент |
| `TRIGRAM_THRESHOLD` | порог pg_trgm similarity для fuzzy-сопоставления сущностей |
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
- `POST /files/{id}/sheets/{sheet_id}/infer-schema` — Schema Inference (LLM).
- `POST /files/{id}/sheets/{sheet_id}/confirm-schema` — подтверждение схемы.

### Agent (`/ask/*`)

- `POST /ask` — вопрос к агенту (`mode`: `auto` | `agent`).

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

## Безопасность SQL

Executor-узел выполняет сгенерированный SQL под основной ролью БД. Защита от опасных
запросов обеспечивается keyword-blacklist валидацией SQL в `codegen_node` (блокировка
INSERT/UPDATE/DELETE/DROP и не-mart сущностей). `statement_timeout` задаётся на уровне
сессии (`DB_STATEMENT_TIMEOUT_MS`).

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

Прод-секреты (LLM API-ключ, пароли БД, `API_KEY`) не должны лежать в `.env` в пайплайне
деплоя. Интеграция с secrets-менеджером (Hashicorp Vault / облачный аналог):

- Секреты загружаются в рантайм из Vault (или env-injection в CI/CD).
- Пример (Vault): приложение читает секреты по пути
  `secret/evraz/prod` и передаёт их в `Settings` до создания движков БД.

---

## Структура проекта

```
src/
  main.py                    # FastAPI app, lifespan, /metrics, /health
  api/                       # роутеры (files, agent, trace, schema, security, ratelimit)
  core/
    config.py                # настройки (rate limits, timeout, trgm threshold)
    db/                      # engine, session, models (raw + mart)
    excel/                   # parser, normalize, schema_inference, template_fingerprint
    metrics.py               # Prometheus-метрики
  services/
    agent/                   # LangGraph: graph.py, nodes (classifier/planner/codegen/executor/verifier)
    mart/                    # normalizer raw->mart
    excel/                   # ingestion_service, ingestion_queue, repository
    entity_resolution/       # entity-resolver, query_cache (pg_trgm, без эмбеддингов)
tests/                       # golden dataset + pytest
alembic/                     # миграции
scripts/init-db/             # расширения Postgres (pg_trgm)
```

---

## Лицензия

Проприетарная (внутренний проект).
