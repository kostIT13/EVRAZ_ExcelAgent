# EVRAZ Agent — полное описание проекта

Агентная система «вопрос-ответ» по данным из Excel-файлов с ценами на цветные металлы (лом).
Пользователь загружает Excel-файлы, система парсит их, нормализует в факт-таблицы (mart),
а затем через LLM-агента отвечает на естественно-языковые вопросы, генерируя и выполняя
безопасный SQL-запрос к PostgreSQL.

---

## 1. Обзор архитектуры

Проект состоит из трёх основных частей:

1. **Backend** (`src/`) — Python 3.12 + FastAPI.
   - REST API для загрузки файлов, вопросов, метрик, трейсов.
   - Парсинг Excel и нормализация данных в витрину (mart).
   - LLM-агент на базе LangGraph (классификация → планирование → генерация SQL → выполнение → проверка → ответ).
2. **Frontend** (`frontend/`) — React 18 + TypeScript + Vite.
   - Страницы: чат, файлы, дашборд, метрики, трейс.
3. **Инфраструктура** (`docker-compose.yml`) — PostgreSQL, сам сервис, frontend (Nginx), Prometheus, Grafana.

### Поток данных (высокоуровнево)

```
Excel файл ──► Парсинг (src/core/excel) ──► RAW таблицы (sheets/cells/columns)
     │
     ▼
Нормализация (src/services/mart/normalizer) ──► Витрина: mart.price_facts, mart.metrics
     │
     ▼
Вопрос пользователя ──► LangGraph агент (src/services/agent)
     │                     classifier → disambiguation → planner → codegen → executor → verifier → answer
     ▼
Безопасный SELECT ──► PostgreSQL ──► Ответ в UI
```

---

## 2. Технологический стек и библиотеки

### Backend (Python ≥ 3.12) — `pyproject.toml`

| Библиотека | Назначение |
|---|---|
| `fastapi` | REST API-фреймворк |
| `uvicorn[standard]` | ASGI-сервер |
| `sqlalchemy` 2.x | ORM |
| `alembic` | миграции БД |
| `asyncpg` / `psycopg[binary]` / `psycopg2` | драйверы PostgreSQL |
| `openai` | клиент OpenAI-совместимого LLM API |
| `langgraph` | оркестрация графа агента |
| `langgraph-checkpoint-postgres` | чекпоинты графа в Postgres |
| `langchain-openai` | структурированный вывод (Pydantic) |
| `openpyxl` | чтение Excel |
| `pandas` | обработка табличных данных |
| `rapidfuzz` | нечёткое сопоставление сущностей (fuzzy match) |
| `pydantic-settings` | конфигурация через `.env` |
| `loguru` | логирование |
| `prometheus-client` | метрики |
| `slowapi` | rate limiting |
| `python-multipart` | загрузка файлов |
| `pytest` | тесты |

### Frontend (React) — `frontend/package.json`

| Библиотека | Назначение |
|---|---|
| `react` / `react-dom` | UI |
| `react-router-dom` | роутинг |
| `chart.js` | графики результатов |
| `framer-motion` | анимации |
| `lucide-react` | иконки |
| `react-markdown` | рендер Markdown-ответов |
| `typescript` + `vite` | сборка |

### Инфраструктура (Docker)

| Сервис | Образ |
|---|---|
| `postgres` | postgres:16-alpine |
| `service` (backend) | собирается из `Dockerfile`, порт 8000 |
| `frontend` | собирается из `Dockerfile.frontend` (Nginx), порт 8080/80 |
| `prometheus` | prom/prometheus:v2.53.0, порт 9090 |
| `grafana` | grafana/grafana:11.1.0, порт 3001 |

---

## 3. Структура проекта

```
├── alembic/                  # Миграции БД
│   └── versions/             # a1b2..., b7a4..., c2d3..., cee213..., d9f2..., f1a2...
├── data/                     # Рабочие данные, bm25_index.pkl, примеры xlsx
├── docs/                     # Примеры запросов
├── frontend/                 # React-приложение
│   └── src/
│       ├── api/              # Клиент API
│       ├── components/       # UI-компоненты (чат, файлы, графики, модалки...)
│       ├── hooks/            # кастомные хуки (useToast)
│       ├── lib/              # утилиты, sheet
│       ├── pages/            # ChatPage, DashboardPage, FilesPage, MetricsPage, TracePage
│       └── types/            # TS-типы API
├── scripts/                  # init-db, prometheus.yml, grafana, verify-скрипты
├── src/                      # Backend
│   ├── api/                  # FastAPI-роутеры
│   ├── core/                 # config, db, excel, logging, metrics, ratelimit
│   ├── services/             # agent, db_tables, entity_resolution, excel, generation, llm, mart, evaluation
│   └── main.py               # точка входа FastAPI
└── tests/                    # pytest-тесты, golden-датасет
```

---

## 4. Backend — REST API (`src/api/`)

| Роутер | Пути | Назначение |
|---|---|---|
| `router.py` | `/health` | проверка живости |
| `agent_router.py` | `POST /ask` | задать вопрос агенту |
| `cache_router.py` | `POST /cache/clear` | очистка кэша запросов |
| `schema_router.py` | схема/метаданные | работа со схемой данных |
| `trace_router.py` | трейсы | история выполнения агента |
| `dependencies.py` | — | DI и сессии БД |
| `security.py` | — | безопасность |
| `errors.py` | — | обработка ошибок |
| `schemas.py` | — | Pydantic-схемы запросов/ответов |

Основной эндпоинт — `POST /ask` с параметрами `question`, `top_k`, `mode`, `retry`.
Он запускает `pipeline.run_agent()`, который вызывает LangGraph-агента и логирует результат в `query_logs`.

---

## 5. Frontend (`frontend/src/`)

**Страницы** (`pages/`):
- `ChatPage.tsx` — основной чат с агентом (прогресс шагов, SQL-блок, таблица/график результата, источники).
- `FilesPage.tsx` — загрузка/список файлов, просмотр листов.
- `DashboardPage.tsx` — общая панель.
- `MetricsPage.tsx` — метрики (Prometheus).
- `TracePage.tsx` — просмотр трейсов выполнения.

**Компоненты** (`components/`):
- `chat/`: `AgentProgress`, `ChatMessage`, `ResultChart`, `ResultTable`, `SourcesModal`, `SqlBlock`, `TypingIndicator`.
- `files/`: `FileList`, `FileUpload`, `SheetViewer`.
- `layout/`: `AnimatedPage`, `Background`, `Header`.
- `ui/`: `EmptyState`, `Modal`, `Tabs`, `Toast`.
- `trace/`: `TraceStepCard`.

Общение с backend — через `src/api/index.ts`; типы — в `src/types/api.ts`.

---

## 6. LLM-часть (`src/services/llm/`)

### `llm_client.py`
- Класс `LLMClient` — тонкая обёртка над `AsyncOpenAI` (совместим с любым OpenAI-подобным API).
- Методы:
  - `chat()` — обычный запрос, возвращает строку.
  - `chat_stream()` — стриминг токенов.
- **Retry-логика** (`_try_with_retries`): повторяет до `MAX_RETRIES` раз при:
  - `RateLimitError` / `APITimeoutError`;
  - **пустом ответе модели** (`message.content` = None / пустая строка) — это частая проблема нестабильных моделей; пустой ответ трактуется как сбой, а не валидный результат.
- Модель по умолчанию — `LLM_MODEL_PRIMARY` из `.env`.

### `structured.py`
- Фабрика `get_structured_llm(schema)` через `langchain-openai` `with_structured_output(..., method="json_mode")`.
- Автоматически парсит ответ модели в валидированный Pydantic-объект.
- Кэширует Runnable по схеме в `_STRUCTURED_CACHE`.

### Модель
- Конфигурируется через `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_PRIMARY`.
- По логам использовалась `deepseek-ai/DeepSeek-V4-Flash`, которая иногда возвращает пустой ответ —
  система теперь переживает это за счёт ретраев и fallback-логики.

---

## 7. Агентная часть (`src/services/agent/`)

Агент построен на **LangGraph** (`graph.py`). Граф компилируется с чекпоинтером на Postgres.

### Граф (`graph.py`, `graph_state.py`)
Состояние `GraphState` содержит: вопрос, `query_type`, сущности, план, SQL, результат, трейс,
`retry_count`, `retry_reason`, `confidence` и др.

**Статусы результата** (по `confidence`):
- `confidence >= 0.7` → `success`;
- иначе → `low_confidence` (триггерит self-correction на уровне pipeline);
- при ошибках графа → `failed`.

### Узлы (`src/services/agent/nodes/`)

1. **`classifier_node`** — определяет тип запроса и сущности.
   Типы: `lookup`, `aggregate`, `cross_sheet`, `delta`, `sum_by_supplier`, `find_period`, `unknown`.
   Домен: `prices` / `metrics` / `generic`. Структурированный вывод `ClassifierResult`.
2. **`disambiguation_node`** — проверяет, нужно ли уточнение (`DisambiguationResult`).
   При необходимости ветвится через `interrupt()` (ожидание ответа пользователя) либо авто-разрешение.
3. **`planner_node`** — строит текстовый план действий (`PlannerResult`).
4. **`codegen_node`** — генерирует SQL (текстом через LLM, или детерминированно из спеки через `sql_compiler`).
   Применяет **детерминированные правки**:
   - `_refine_all_kinds_filter` — «все виды меди» → префиксный `item_name ILIKE 'Лом меди%'`;
   - `_refine_supplier_in_filter` / `_refine_supplier_ilike_any` — нормализация дефисов/пробелов в поставщиках
     (`'Сплав-21'` → `'%сплав21%'`);
   - `_normalize_is_blank_filters` — булевы литералы `is_blank = false/true` → целые `0/1`
     (колонка хранится как INTEGER);
   - `validate_sql` — проверка: только `SELECT`, запрещённые ключевые слова, баланс скобок и **баланс одинарных кавычек**
     (детекция обрезанного SQL).
5. **`executor_node`** — выполняет SQL в Postgres (read-only, `statement_timeout`). При ошибке заполняет
   `sql_error` и `retry_reason`, пробует серию fallback-SQL, если результат пуст.
6. **`verifier_node`** — проверяет корректность SQL+результата через LLM (JSON). При невалидном ответе делает
   до 3 попыток и извлекает JSON-подстроку. Если модель не вернула JSON — **детерминированный fallback**
   с уверенностью 0.75 (не роняет граф и не уходит в low_confidence).
7. **`answer_node`** — формирует финальный естественно-языковой ответ.

### Маршрутизация (`routing.py`)
- `route_after_codegen` — пустой SQL/ошибки валидации → ретрай codegen (до `MAX_RETRY_COUNT=3`), иначе failed.
- `route_after_executor` — ошибка SQL → ретрай codegen; успех → verifier.
- `route_after_verifier` — `needs_retry` → codegen; иначе → answer.

### Безопасный компилятор SQL (`sql_compiler.py`)
- `compile_spec()` — компилирует структурированную спеку в безопасный SELECT.
- Whitelist таблиц: `mart.price_facts`, `mart.metrics`.
- Whitelist колонок, разрешённые агрегации (`AVG/SUM/MIN/MAX/COUNT`), операторы.
- `is_blank` трактуется как целое (0/1).

---

## 8. Парсинг Excel (`src/core/excel/`)

| Модуль | Назначение |
|---|---|
| `parser.py` | чтение `.xlsx` через openpyxl/pandas |
| `comment_extractor.py` | извлечение комментариев ячеек |
| `normalize.py` | нормализация имён листов/колонок |
| `schema_inference.py` | авто-определение типов колонок |
| `schemas.py` | Pydantic-схемы листов/колонок |
| `sheet_kind_detector.py` | определение вида листа (prices/metrics/generic) |
| `table_structurer.py` | структуризация таблицы |
| `template_fingerprint.py` | отпечаток шаблона листа |

Парсинг сохраняет данные в таблицы `files`, `sheets`, `column_metadata`, `cells`, `excel_comments`.

---

## 9. Нормализация в витрину (`src/services/mart/normalizer.py`)

Преобразует сырые `sheets/cells` в нормализованные long-факт-таблицы:

- **`mart.price_facts`** — строки цен лома:
  `sheet_period`, `item_name`, `supplier`, `price_type`
  (`среднерыночная` / `аукцион_старт` / `аукцион_победитель` / `поставщик`), `value`, `currency`, `unit`, `is_blank`.
- **`mart.metrics`** — производственные/шихтовые метрики (план/факт/отклонение/расход/запасы):
  `dimension`, `dimension_type`, `period`, `metric_type`, `metric`, `value`, `unit`, `is_blank`.

Пустые ячейки сохраняются признаком `is_blank = 1`, а не превращаются в 0.

---

## 10. База данных PostgreSQL — таблицы (`src/core/db/models.py`)

### Общедоступная схема (public)

| Таблица | Класс | Назначение |
|---|---|---|
| `files` | `File` | загруженные файлы (hash, статус, счётчики) |
| `sheets` | `Sheet` | листы (имя, период, kind) |
| `column_metadata` | `ColumnMetadata` | колонки листов (тип, роль, сэмплы) |
| `cells` | `Cell` | сырые ячейки (текст/число/дата) |
| `entity_dictionary` | `EntityDictionary` | словарь сущностей (canonical name + алиасы + embedding) |
| `excel_comments` | `ExcelComment` | комментарии ячеек |
| `query_cache` | `QueryCache` | кэш вопрос→SQL/результат |
| `golden_dataset` | `GoldenDataset` | эталонные вопросы (тесты качества) |
| `query_logs` | `QueryLog` | журнал запросов/трейсов |

### Схема `mart`

| Таблица | Класс | Назначение |
|---|---|---|
| `price_facts` | `PriceFact` | нормализованные цены лома |
| `metrics` | `Metric` | нормализованные производственные метрики |
| `sheet_templates` | `SheetTemplate` | шаблоны листов по fingerprint |
| `supplier_aliases` | `SupplierAlias` | алиасы поставщиков (canonical ↔ alias) |

### Особенности
- Булевы поля (например `is_blank`, `sheet_kind_auto`, `is_active`) объявлены как `Integer (0/1)` —
  поэтому в SQL их нужно сравнивать с числами, а не с `TRUE/FALSE`.
- Миграции — в `alembic/versions/` (последовательность `cee213` → `b7a4` → `c2d3` → `d9f2` → `f1a2` → `a1b2`).
- Расширения БД инициализируются в `scripts/init-db/01-extensions.sql`.

---

## 11. Сущности и разрешение (`src/services/entity_resolution/`)

- `entity_resolver.py` — сопоставление упомянутых сущностей с реальными (rapidfuzz fuzzy match + словарь).
- `query_cache.py` — кэш результатов разрешения.
- `bm25_index.pkl` в `data/` — BM25-индекс для поиска релевантных листов/сущностей (`top_k`).

---

## 12. Конфигурация (`.env`)

Заполняется из `.env.example`. Ключевые переменные:

| Переменная | Назначение |
|---|---|
| `LLM_BASE_URL` | base URL OpenAI-совместимого API |
| `LLM_API_KEY` | API-ключ |
| `LLM_MODEL_PRIMARY` | основная модель |
| `LLM_TEMPERATURE` | температура (по умолч. 0.1) |
| `LLM_MAX_TOKENS` | лимит токенов (по умолч. 2048) |
| `REQUEST_TIMEOUT_S` | таймаут запросов к LLM (60) |
| `MAX_RETRIES` | число ретраев LLM (3) |
| `POSTGRES_*` | подключение к БД |
| `DB_STATEMENT_TIMEOUT_MS` | таймаут SQL (30000) |
| `TRIGRAM_THRESHOLD` | порог триграммного совпадения (0.25) |
| `RATE_LIMIT_*` | ограничения частоты API |

---

## 13. Мониторинг

- **Prometheus** (`/metrics` на порту 8000) собирает метрики приложения: латентность узлов агента,
  токены LLM (`observe_llm_tokens`), счётчики запросов.
- **Grafana** (порт 3001) визуализирует метрики (датасорс подключается через provisioning).
- Логи — `loguru`, собираются в Docker Compose.

---

## 14. Тесты (`tests/`)

- `test_sql_compiler.py` — безопасный компилятор SQL.
- `test_normalizer_dimension.py` — нормализация измерений.
- `test_classifier_domain.py` — классификатор доменов.
- `test_parser_header_detection.py` — определение шапки Excel.
- `test_golden_dataset.py` — интеграционные тесты на golden-датасете (требуют LLM и данные; маркер `golden`).
- `golden_questions.json` — набор эталонных вопросов.

Запуск:
```
uv run pytest -q
```
или, если используется pip:
```
python -m pytest -q
```

---

## 15. Быстрый старт

1. Скопировать `.env.example` → `.env` и заполнить `LLM_*` и `POSTGRES_*`.
2. Поднять инфраструктуру:
   ```
   docker compose up --build
   ```
   - Backend: http://localhost:8000 (`/docs` — Swagger)
   - Frontend: http://localhost:8080
   - Prometheus: http://localhost:9090
   - Grafana: http://localhost:3001 (admin/admin)
3. Загрузить Excel-файлы через UI (страница «Файлы») → система распарсит и нормализует их.
4. Задавать вопросы в чате (страница «Чат»).

---
