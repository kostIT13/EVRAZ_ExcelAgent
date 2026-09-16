# EVRAZ Agent — Backend (FastAPI)

Backend-часть проекта: REST API, парсинг Excel, нормализация данных в витрину (mart),
LLM-агент на LangGraph и наблюдаемость (Prometheus).

- Язык/версия: **Python ≥ 3.12**
- Фреймворк: **FastAPI** + uvicorn (ASGI)
- Зависимости: [`pyproject.toml`](../pyproject.toml)

---

## Оглавление

- [Структура](#структура)
- [Модули](#модули)
- [REST API](#rest-api)
- [Запуск](#запуск)
- [Конфигурация](#конфигурация)
- [Поток обработки](#поток-обработки)
- [Смежные части проекта](#смежные-части-проекта)

---

## Структура

```
src/
├── main.py                      # точка входа FastAPI (lifespan, роутеры, /health, /metrics)
├── api/                         # FastAPI-роутеры и схемы
│   ├── router.py                #   файлы: upload / status / sheets / columns / cells
│   ├── agent_router.py          #   POST /ask — вопросы к агенту
│   ├── schema_router.py         #   Schema Inference и подтверждение схем
│   ├── trace_router.py          #   трейсы выполнения графа
│   ├── cache_router.py          #   очистка кэша запросов
│   ├── security.py              #   API-key auth
│   ├── ratelimit.py             #   slowapi-лимиты
│   ├── errors.py                #   обработчики исключений
│   └── schemas.py               #   Pydantic-схемы запросов/ответов
├── core/
│   ├── config.py                # настройки через pydantic-settings (.env)
│   ├── logging_settings.py      # loguru
│   ├── metrics.py               # Prometheus-метрики
│   ├── db/                      # engine, session, Base, ORM-модели
│   └── excel/                   # парсинг Excel, schema inference, fingerprint
└── services/
    ├── agent/                   # LangGraph-агент (см. README агента)
    ├── llm/                     # LLMClient, structured output
    ├── mart/                    # нормализация в mart.price_facts / mart.metrics
    ├── excel/                   # ingestion-сервис и очередь
    ├── entity_resolution/       # fuzzy-резолвер сущностей, BM25-индекс
    ├── generation/              # pipeline.run_agent()
    ├── evaluation/              # golden-датасет
    └── db_tables/               # сервисы доступа к таблицам БД
```

---

## Модули

### `src/main.py`
Точка входа. В `lifespan`:
1. Проверка подключения к БД (`SELECT 1`);
2. Старт воркера очереди ingestion ([`src/services/excel/ingestion_queue.py`](../src/services/excel/ingestion_queue.py));
3. Инициализация LangGraph checkpointer (Postgres).

Подключает роутеры и эндпоинты `/health`, `/metrics`, `/metrics/summary`.

### `src/api/`
REST-слой. Все роутеры описаны ниже. Auth — через `verify_api_key` (заголовок `X-API-Key`),
rate limiting — `slowapi`.

### `src/core/`
- **config** — все настройки из `.env` (модель `Settings`, pydantic-settings);
- **db** — асинхронный движок SQLAlchemy 2.0 (asyncpg), сессии, модели;
- **excel** — парсер, нормализация имён, детектор вида листа, schema inference,
  template fingerprint (см. README БД для связки с `mart.sheet_templates`);
- **metrics** — Prometheus-метрики: RPS/латентность `/ask`, per-node latency графа,
  доля `failed`/`low_confidence`, token usage LLM.

### `src/services/`
- **llm** — тонкая обёртка `AsyncOpenAI` с ретраями (в т.ч. на пустой ответ модели)
  и фабрика structured-output через `langchain-openai` (`with_structured_output(json_mode)`);
- **mart** — нормализация сырых ячеек в long-факт-таблицы витрины, идемпотентно;
- **excel** — асинхронная очередь ingestion (`inproc`) и сервис обработки файлов;
- **entity_resolution** — сопоставление сущностей (rapidfuzz + pg_trgm), кэш, BM25-индекс;
- **agent** — см. [`services/agent/README.md`](services/agent/README.md);
- **generation** — `pipeline.run_agent()`: запуск агента, self-correction, логирование в `query_logs`;
- **db_tables** — сервисы по таблицам (`cell_service`, `column_service`, `file_service`,
  `query_log_service`, `sheet_service`).

---

## REST API

Интерактивная документация — Swagger: `http://localhost:8000/docs`.

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/health` | проверка живости |
| `GET` | `/metrics` | метрики Prometheus |
| `POST` | `/files/upload` | загрузка Excel-файла (асинхронно, возвращает `file_id`) |
| `GET` | `/files` | список файлов |
| `GET` | `/files/{id}` | детали файла |
| `GET` | `/files/{id}/status` | статус обработки |
| `GET` | `/files/{id}/sheets` | листы файла |
| `GET` | `/files/{id}/columns` | колонки листов |
| `GET` | `/files/{id}/cells` | сырые ячейки |
| `POST` | `/files/{id}/sheets/{sheet_id}/infer-schema` | Schema Inference (LLM) |
| `POST` | `/files/{id}/sheets/{sheet_id}/confirm-schema` | подтверждение схемы |
| `POST` | `/ask` | вопрос к агенту: `{question, top_k, mode, retry, response_mode}` |
| `POST` | `/cache/clear` | очистка кэша запросов |
| `GET` | `/trace/...` | трейсы выполнения графа |

Эндпоинты `/files/*` и `/ask/*` защищены API-ключом (если `API_KEY` задан в `.env`).

---

## Запуск

### Через Docker Compose (рекомендуется)

```bash
cp .env.example .env            # заполнить LLM_* и POSTGRES_*
docker compose up --build -d
docker compose exec service alembic upgrade head
# Backend: http://localhost:8000  ·  Swagger: http://localhost:8000/docs
```

### Локально (разработка)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (Linux/macOS: source .venv/bin/activate)
uv pip install -e .             # или pip install -e .
cp .env.example .env            # POSTGRES_HOST=localhost при локальном запуске
alembic upgrade head
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Конфигурация

Все переменные читаются из `.env` (см. [`.env.example`](../.env.example)):

| Переменная | Описание | По умолчанию |
|---|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` | OpenAI-совместимый LLM API | — |
| `LLM_MODEL_PRIMARY` | основная модель | `deepseek-ai/DeepSeek-V4-Flash` |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | параметры генерации | `0.1` / `2048` |
| `REQUEST_TIMEOUT_S` / `MAX_RETRIES` | таймаут и ретраи LLM | `60` / `3` |
| `POSTGRES_*` | подключение к PostgreSQL | — |
| `DB_STATEMENT_TIMEOUT_MS` | timeout выполнения SQL | `30000` |
| `TRIGRAM_THRESHOLD` | порог fuzzy-совпадения сущностей | `0.25` |
| `API_KEY` | ключ для `/files/*` и `/ask/*` (пусто = dev) | — |
| `RATE_LIMIT_ASK` / `RATE_LIMIT_UPLOAD` | rate limits | `30/minute` / `10/minute` |
| `INGESTION_QUEUE_MODE` | режим очереди ingestion | `inproc` |

---

## Поток обработки

1. **Upload** → запись в `files` со статусом `uploaded`;
2. **Ingestion** (асинхронно) → парсинг Excel → `sheets`, `column_metadata`, `cells`, `excel_comments`;
3. **Schema Inference** → LLM-схема для новых форматов или Template Fingerprint из `mart.sheet_templates`;
4. **Normalize** → перенос в `mart.price_facts` / `mart.metrics` (идемпотентно);
5. **Entity Resolution** → сбор справочников сущностей;
6. Статус файла → `ready` / `failed`.

Вопросы пользователя обрабатывает LangGraph-агент (см. [`services/agent/README.md`](services/agent/README.md)),
а SQL выполняет executor-узел против витрины `mart.*`.

---

## Смежные части проекта

- [Frontend](../frontend/README.md) — React-интерфейс
- [База данных](core/db/README.md) — схемы public/mart, миграции Alembic
- [Агент](services/agent/README.md) — LangGraph-граф и узлы
- [Корневой README](../README.md) — общее описание проекта