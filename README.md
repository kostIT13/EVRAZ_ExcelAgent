# EVRAZ RAG Agent

**AI-агент для интеллектуальной работы с Excel-файлами металлургической компании ЕВРАЗ.**

Система позволяет загружать Excel-файлы с ценами на металлы, автоматически парсить их, строить векторные индексы (dense + sparse в Qdrant) и отвечать на вопросы пользователя на естественном языке — как через RAG-пайплайн, так и через специализированного LangGraph-агента с генерацией SQL.

---

## Содержание

- [Архитектура](#архитектура)
- [Возможности](#возможности)
- [Стек технологий](#стек-технологий)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
- [API](#api)
  - [Управление файлами](#управление-файлами)
  - [RAG / Agent](#rag--agent)
  - [Traceability](#traceability)
- [Архитектура агента (LangGraph)](#архитектура-агента-langgraph)
- [RAG-пайплайн](#rag-пайплайн)
- [Структура проекта](#структура-проекта)
- [Разработка](#разработка)
- [Лицензия](#лицензия)

---

## Архитектура

```
┌─────────────┐     ┌─────────────────────────────────────────────────────┐
│  Frontend   │     │                   Backend (FastAPI)                  │
│  (Vue/HTML) │────▶│                                                     │
│  :8080      │     │  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
└─────────────┘     │  │ /files/* │  │   /ask/*     │  │  /trace/*     │  │
                    │  │  REST    │  │  RAG/Agent   │  │  Traceability │  │
                    │  └────┬─────┘  └──────┬───────┘  └───────┬───────┘  │
                    │       │               │                  │          │
                    │  ┌────▼───────────────▼──────────────────▼──────┐   │
                    │  │           GenerationPipeline                  │   │
                    │  │  ┌──────────┐  ┌──────────┐  ┌───────────┐  │   │
                    │  │  │ RAG-only │  │ LangGraph│  │ Verifier  │  │   │
                    │  │  │ Pipeline │  │  Agent   │  │           │  │   │
                    │  │  └──────────┘  └──────────┘  └───────────┘  │   │
                    │  └────────────────────┬─────────────────────────┘   │
                    │                       │                            │
                    │  ┌────────────────────▼─────────────────────────┐   │
                    │  │              RagService                       │   │
                    │  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │   │
                    │  │  │ Dense    │ │  Sparse  │ │   Hybrid     │  │   │
                    │  │  │Retriever │ │  Vector  │ │   Retriever  │  │   │
                    │  │  └──────────┘ └──────────┘ └──────────────┘  │   │
                    │  └────────────────────┬─────────────────────────┘   │
                    └───────────────────────┼─────────────────────────────┘
                                            │
              ┌─────────────────────────────┼─────────────────────────────┐
              │              Qdrant (dense + sparse)                      │
              │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐   │
              │  │  chunks  │ │  sheets  │ │ columns  │ │  comments  │   │
              │  │ (dense+  │ │ (dense+  │ │ (dense+  │ │ (dense+    │   │
              │  │  sparse) │ │  sparse) │ │  sparse) │ │  sparse)   │   │
              │  └──────────┘ └──────────┘ └──────────┘ └────────────┘   │
              └──────────────────────────────────────────────────────────┘
                                            │
              ┌─────────────────────────────┼─────────────────────────────┐
              │              PostgreSQL (реляционные данные)              │
              │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐   │
              │  │  files   │ │  sheets  │ │ columns  │ │   cells    │   │
              │  ├──────────┤ ├──────────┤ ├──────────┤ ├────────────┤   │
              │  │fact_prices││ query_logs││query_cache││golden_dataset│  │
              │  └──────────┘ └──────────┘ └──────────┘ └────────────┘   │
              └──────────────────────────────────────────────────────────┘
                                            │
              ┌─────────────────────────────┼─────────────────────────────┐
              │         Ollama (LLM)        │      fastembed (Dense)      │
              │  ┌──────────────────┐       │  ┌──────────────────────┐   │
              │  │  LLM (chat)      │       │  │ Embedding Model      │   │
              │  │  (fallback)      │       │  │ multilingual-e5-small│   │
              │  └──────────────────┘       │  └──────────────────────┘   │
              └─────────────────────────────┴─────────────────────────────┘
```

### Компоненты

| Компонент | Назначение |
|-----------|-----------|
| **FastAPI** | Основной бэкенд-сервер (порт 8000) |
| **PostgreSQL** | Хранение реляционных данных Excel (файлы, листы, ячейки, логи) |
| **Qdrant** | Векторное хранилище (dense + sparse вектора, гибридный поиск) |
| **Ollama** | Локальный LLM для fallback (chat) |
| **fastembed** | Локальные dense-эмбеддинги (multilingual-e5-large) на ONNX Runtime |
| **LangGraph** | Граф агента (Classifier → Planner → CodeGen → Executor → Verifier) |
| **flashrank** | Реранкинг результатов гибридного поиска |
| **Frontend** | Веб-интерфейс на Vite (порт 8080) |

---

## Возможности

### 📂 Загрузка и парсинг Excel
- Загрузка `.xlsx` / `.xls` файлов через REST API
- Автоматическое определение строк-заголовков
- Распознавание типов колонок (число, цена, дата, текст, ID)
- Очистка имён колонок от телефонов, лишних символов
- Разделение объединённых ячеек
- Хранение полной структуры: файл → листы → колонки → ячейки

### 🔍 Гибридный поиск (RAG)
- **Dense retrieval**: эмбеддинги через `fastembed` (`intfloat/multilingual-e5-large`) с косинусной близостью
- **Sparse retrieval**: BM25-подобные sparse-вектора (хранятся в Qdrant)
- **Fusion**: RRF (Reciprocal Rank Fusion) — выполняется одним запросом к Qdrant
- **Реранкинг**: кросс-энкодерная модель `ms-marco-MiniLM-L-12-v2` (flashrank)
- Кэширование эмбеддингов запросов (in-memory, через абстрактный интерфейс)
- Вектора хранятся в Qdrant (dense + sparse), PostgreSQL — только реляционные данные

### 🤖 LangGraph Agent
- **Classifier**: определяет тип запроса (lookup / aggregate / cross_sheet / delta)
- **Planner**: составляет план действий на основе схемы данных
- **CodeGen**: генерирует SQL-запрос с валидацией (read-only, запрещённые ключевые слова)
- **Executor**: безопасно выполняет SQL с таймаутом
- **Verifier**: проверяет ответ на галлюцинации, при необходимости запускает retry
- **Self-Correction**: автоматический повтор при низком качестве ответа

### 📊 Режимы работы
| Режим | Описание |
|-------|----------|
| `auto` | Автоопределение: сначала агент, при неудаче — fallback на RAG |
| `rag` | Только RAG (гибридный поиск + LLM) |
| `agent` | Только агент (полный граф LangGraph) |

### 🔎 Traceability
- Полный трейс каждого запроса: вопрос → план → SQL → результат
- История запросов с возможностью просмотра по `request_id`
- Логирование в БД (таблица `query_logs`)

---

## Стек технологий

### Backend
| Технология | Назначение |
|-----------|-----------|
| **Python 3.12+** | Язык разработки |
| **FastAPI** | Веб-фреймворк |
| **SQLAlchemy 2.0** | ORM |
| **asyncpg** | Асинхронный драйвер PostgreSQL |
| **Qdrant** | Векторное хранилище (dense + sparse) |
| **fastembed** | Генерация sparse-векторов (BM25/SPLADE) |
| **flashrank** | Реранкинг результатов поиска |
| **LangGraph** | Граф агента |
| **OpenAI SDK** | Клиент для LLM (OpenAI / vLLM / DeepSeek / Ollama) |
| **openpyxl** | Парсинг Excel |
| **pandas** | Обработка данных |
| **Pydantic** | Валидация схем |
| **Loguru** | Логирование |
| **Alembic** | Миграции БД |

### Frontend
| Технология | Назначение |
|-----------|-----------|
| **Vite** | Сборщик |
| **Vanilla JS** | Клиентский код |
| **Nginx** | Веб-сервер + прокси на backend |

### Инфраструктура
| Технология | Назначение |
|-----------|-----------|
| **Docker / Docker Compose** | Контейнеризация |
| **PostgreSQL** | Реляционная база данных |
| **Qdrant** | Векторное хранилище |
| **Ollama** | Локальный LLM |

---

## Быстрый старт

### 1. Клонирование

```bash
git clone <repository-url>
cd EVRAZ_AGENT
```

### 2. Настройка окружения

Скопируйте `.env.example` в `.env` и отредактируйте:

```bash
cp .env.example .env
```

Минимальная конфигурация:

```env
# LLM (основной)
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL_PRIMARY=deepseek-ai/DeepSeek-V4-Flash
LLM_MODEL_CHEAP=qwen2.5:1.5b

# Dense-эмбеддинги через fastembed (локально, ONNX Runtime)
EMBED_MODEL=intfloat/multilingual-e5-large
FASTEMBED_MODEL=intfloat/multilingual-e5-large
EMBED_DIMENSION=1024

# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
POSTGRES_DB=evraz_rag
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_URL=postgresql+asyncpg://postgres:your-password@postgres:5432/evraz_rag

# Qdrant (векторное хранилище)
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=evraz_chunks
```

### 3. Запуск через Docker Compose

```bash
docker compose up -d
```

Будут запущены:
- **PostgreSQL** (порт 5432)
- **Qdrant** (порт 6333)
- **Ollama** (порт 11434)
- **Backend** (порт 8000)
- **Frontend** (порт 8080)

### 4. Инициализация БД

```bash
docker compose exec service alembic upgrade head
```

### 5. Загрузка модели эмбеддингов (fastembed)

Модель `intfloat/multilingual-e5-large` скачивается автоматически при первом
запуске с HuggingFace Hub и кэшируется локально (никаких действий не требуется).

### 6. Проверка

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

Откройте браузер: [http://localhost:8080](http://localhost:8080)

---

## Конфигурация

Все настройки задаются через переменные окружения (файл `.env`).

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `LLM_BASE_URL` | — | URL API для LLM (OpenAI / vLLM / DeepSeek) |
| `LLM_API_KEY` | — | API-ключ |
| `LLM_MODEL_PRIMARY` | — | Основная модель |
| `LLM_MODEL_CHEAP` | — | Дешёвая модель (fallback) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | URL Ollama (chat fallback) |
| `FASTEMBED_MODEL` | `intfloat/multilingual-e5-large` | Модель dense-эмбеддингов (fastembed) |
| `EMBED_DIMENSION` | `1024` | Размерность эмбеддингов |
| `LLM_TEMPERATURE` | `0.1` | Температура LLM |
| `LLM_MAX_TOKENS` | `2048` | Максимум токенов |
| `REQUEST_TIMEOUT_S` | `60` | Таймаут запроса к LLM |
| `MAX_RETRIES` | `3` | Количество retry при ошибках LLM |
| `POSTGRES_URL` | — | Полный URL подключения к БД |
| `QDRANT_URL` | `http://qdrant:6333` | URL Qdrant |
| `QDRANT_API_KEY` | — | API-ключ Qdrant (опционально) |
| `QDRANT_COLLECTION` | `evraz_chunks` | Имя коллекции в Qdrant |
| `QDRANT_SPARSE_MODEL` | `Qdrant/bm25` | Модель sparse-векторов (fastembed) |
| `RERANKER_MODEL` | `ms-marco-MiniLM-L-12-v2` | Модель реранкера (flashrank) |
| `RERANKER_ENABLED` | `true` | Включить реранкинг |
| `RERANKER_TOP_K` | `5` | Сколько результатов вернуть после реранкинга |

---

## API

### Управление файлами

Все эндпоинты находятся под префиксом `/files`.

#### `POST /files/upload` — загрузка Excel-файла

Загружает `.xlsx` / `.xls` файл (до 50 МБ). Автоматически парсит, сохраняет структуру в БД и строит векторные индексы.

**Request:** `multipart/form-data` с полем `file`

**Response (201):**
```json
{
  "message": "File uploaded and processed successfully",
  "file": {
    "id": 1,
    "filename": "prices.xlsx",
    "file_hash": "a1b2c3d4e5f6...",
    "total_sheets": 3,
    "total_rows": 1500,
    "total_cells": 45000,
    "uploaded_at": "2025-01-15T10:30:00Z",
    "processed_at": "2025-01-15T10:30:05Z",
    "status": "uploaded",
    "error_message": null
  }
}
```

#### `GET /files` — список файлов

**Параметры:** `skip` (0), `limit` (100), `status` (опционально)

#### `GET /files/{file_id}` — детали файла

Возвращает файл со списком листов.

#### `DELETE /files/{file_id}` — удаление файла

Каскадно удаляет листы, колонки, ячейки и эмбеддинги.

#### `GET /files/{file_id}/sheets` — листы файла

#### `GET /files/{file_id}/sheets/{sheet_id}` — детали листа с колонками

#### `GET /files/{file_id}/sheets/{sheet_id}/columns` — колонки листа

#### `GET /files/{file_id}/sheets/{sheet_id}/cells` — ячейки листа

**Параметры:** `skip` (0), `limit` (100)

#### `POST /files/{file_id}/reindex` — перестроение индексов

Полезно после изменений данных или если индексация не удалась при загрузке.

### RAG / Agent

#### `POST /ask` — задать вопрос

**Request:**
```json
{
  "question": "Какая цена меди в январе 2025?",
  "top_k": 10,
  "mode": "auto",
  "conversation_history": []
}
```

**Параметры:**
| Поле | Тип | Описание |
|------|-----|----------|
| `question` | string (1-2000) | Вопрос пользователя |
| `top_k` | int (1-50) | Количество чанков для поиска |
| `mode` | `auto` / `rag` / `agent` | Режим обработки |
| `conversation_history` | array | История для self-correction |

**Response (agent mode):**
```json
{
  "answer": "Цена меди в январе 2025 составила 8500 руб/тн...",
  "confidence": 0.92,
  "sources": [],
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "latency_ms": 3420,
  "mode_used": "agent",
  "query_type": "lookup",
  "sql_query": "SELECT c.value_number ...",
  "sql_result_preview": [{"value_number": 8500.0}],
  "retry_count": 0,
  "status": "success",
  "self_corrected": false
}
```

### Traceability

#### `GET /trace` — список последних запросов

**Параметры:** `limit` (20), `offset` (0)

#### `GET /trace/{request_id}` — полный трейс запроса

Возвращает все шаги обработки: вопрос → классификация → план → SQL → результат → ответ.

---

## Архитектура агента (LangGraph)

Агент построен на базе **LangGraph StateGraph** и проходит через следующие узлы:

```
Вход → [RAG] → [Classifier] → [Planner] → [CodeGen] → [Executor] → [Verifier] → [Answer] → Выход
                  │               │           │  ▲           │  ▲         │  ▲
                  └───────────────┘           └──┴───────────┴──┴─────────┴──┘ (retry до 3 раз)
```

### Узлы графа

| Узел | Назначение | Вход | Выход |
|------|-----------|------|-------|
| **RAG** | Гибридный поиск (BM25 + Dense) | Вопрос пользователя | `rag_context`, `rag_chunks` |
| **Classifier** | Определение типа запроса и сущностей | Вопрос + RAG-контекст | `query_type`, `entities`, `relevant_sheets` |
| **Planner** | Составление плана действий | Тип запроса + схема листов | `plan`, `schema` |
| **CodeGen** | Генерация SQL с валидацией | План + схема + RAG-контекст | `sql_query`, `validation_errors` |
| **Executor** | Безопасное выполнение SQL | SQL-запрос | `sql_result` / `sql_error` |
| **Verifier** | Проверка ответа, решение о retry | Результат SQL + вопрос | `answer`, `confidence`, `needs_retry` |
| **Answer** | Финальное форматирование ответа | Ответ от Verifier | Финальный `answer` |

### Self-Correction

Если после первого прохода `confidence < 0.5` или статус `failed`/`low_confidence`, пайплайн автоматически делает второй проход с контекстом предыдущей ошибки:

```python
needs_correction = (
    result.status in ("failed", "low_confidence")
    or result.confidence < 0.5
    or not result.answer
    or len(result.answer) < 20
)
```

### Типы запросов (QueryType)

| Тип | Описание | Пример |
|-----|----------|--------|
| `lookup` | Поиск конкретного значения | "Какая цена меди?" |
| `aggregate` | Агрегация (сумма, среднее) | "Средняя цена никеля за квартал" |
| `cross_sheet` | Сравнение между листами | "Сравнить цены января и февраля" |
| `delta` | Разница во времени | "На сколько изменилась цена?" |
| `unknown` | Неопределённый тип | — |

---

## RAG-пайплайн

### Chunking

Текст листов разбивается на чанки тремя стратегиями:

| Стратегия | Описание |
|-----------|----------|
| `tokens` | Разбивка по токенам (словам) с перекрытием |
| `sentences` | Разбивка по предложениям |
| `adaptive` | Адаптивная: по абзацам, с перекрытием (по умолчанию) |

### Индексация

1. **Dense**: каждый чанк эмбеддится через `fastembed` (`intfloat/multilingual-e5-large`) → хранится в Qdrant
2. **Sparse**: BM25-подобные sparse-вектора генерируются через fastembed → хранятся в Qdrant
3. **Column embeddings**: отдельные эмбеддинги для каждой колонки
4. **Sheet embeddings**: общий эмбеддинг для каждого листа (fallback)
5. **Comments**: эмбеддинги Excel-комментариев

### Гибридный поиск

```
Запрос → [Embedder] → Dense vector
       → [Sparse]   → Sparse vector
       → [Qdrant]   → Гибридный поиск (RRF-слияние одним запросом)
       → [Reranker] → Реранкинг (flashrank) → Результаты
```

Методы слияния (fusion):
- **RRF** (Reciprocal Rank Fusion): `score = 1 / (k + rank)`, где `k=60` — выполняется в Qdrant
- **Реранкинг**: кросс-энкодерная модель `ms-marco-MiniLM-L-12-v2` переупорядочивает результаты

### Verifier (проверка ответов)

После генерации ответа Verifier проверяет:
1. **Числа**: все числа из ответа должны присутствовать в контексте
2. **Сущности**: именованные сущности проверяются на наличие в контексте
3. **Покрытие**: доля слов ответа, найденных в контексте (порог 40%)
4. **Уверенность**: `confidence = coverage - warnings * 0.15`

---

## Структура проекта

```
EVRAZ_AGENT/
├── .env.example              # Шаблон конфигурации
├── docker-compose.yml        # Docker Compose (PostgreSQL + Qdrant + Ollama + Backend + Frontend)
├── Dockerfile                # Dockerfile для backend
├── Dockerfile.frontend       # Dockerfile для frontend
├── pyproject.toml            # Зависимости Python
├── uv.lock                   # Lock-файл uv
│
├── alembic/                  # Миграции БД
│   ├── env.py
│   └── script.py.mako
│
├── data/                     # Данные (Excel-файлы)
│   └── data_proportional_prices.xlsx
│
├── frontend/                 # Веб-интерфейс
│   ├── index.html
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.js
│   ├── public/
│   │   └── favicon.svg
│   └── src/
│       ├── api.js            # API-клиент
│       ├── main.js           # Точка входа
│       └── styles/
│           └── main.css
│
└── src/                      # Исходный код backend
    ├── main.py               # Точка входа FastAPI
    ├── pipeline-plan.md      # План развития
    │
    ├── api/                  # REST API
    │   ├── router.py         # /files/* эндпоинты
    │   ├── agent_router.py   # /ask/* эндпоинты
    │   ├── trace_router.py   # /trace/* эндпоинты
    │   ├── schemas.py        # Pydantic-схемы
    │   ├── dependencies.py   # DI
    │   └── errors.py         # Централизованная обработка ошибок
    │
    ├── core/                 # Ядро
    │   ├── config.py         # Настройки (pydantic-settings)
    │   ├── logging_settings.py
    │   ├── db/
    │   │   ├── base.py       # SQLAlchemy Base
    │   │   ├── database.py   # Асинхронный движок + сессии
    │   │   └── models.py     # ORM-модели (File, Sheet, ColumnMetadata, Cell, QueryLog)
    │   ├── qdrant/
    │   │   └── client.py     # Qdrant-клиент (dense + sparse, гибридный поиск)
    │   └── excel/
    │       ├── parser.py     # Парсинг Excel (openpyxl)
    │       ├── normalize.py  # Нормализация данных и типов
    │       └── schemas.py    # Pydantic-схемы для парсинга
    │
    ├── services/
    │   ├── excel/
    │   │   ├── ingestion_service.py  # Загрузка и индексация файлов
    │   │   └── repository.py         # Сохранение в БД
    │   │
    │   ├── rag/
    │   │   ├── rag_service.py  # Оркестратор RAG
    │   │   ├── chunker.py      # Разбивка на чанки
    │   │   ├── embedder.py     # Эмбеддинги + абстрактный кэш
    │   │   ├── embedding_cache.py  # Интерфейс кэша эмбеддингов
    │   │   ├── sparse.py       # Генерация sparse-векторов (fastembed)
    │   │   ├── reranker.py     # Реранкинг (flashrank)
    │   │   ├── hybrid.py       # Гибридный поиск (RRF через Qdrant)
    │   │   └── retrieval.py    # Dense retrieval (Qdrant)
    │   │
    │   ├── generation/
    │   │   ├── pipeline.py     # GenerationPipeline (RAG + Agent)
    │   │   ├── rag_prompt.py   # Промпты для RAG
    │   │   └── verifier.py     # Проверка ответов
    │   │
    │   ├── agent/
    │   │   ├── graph.py        # LangGraph граф + LangGraphAgent
    │   │   ├── graph_state.py  # TypedDict состояния графа
    │   │   └── nodes/
    │   │       ├── rag_node.py       # RAG-узел
    │   │       ├── classifier_node.py # Классификация запроса
    │   │       ├── planner_node.py    # Планирование
    │   │       ├── codegen_node.py    # Генерация SQL
    │   │       ├── executor_node.py   # Выполнение SQL
    │   │       ├── verifier_node.py   # Верификация
    │   │       ├── answer_node.py     # Финальный ответ
    │   │       └── routing.py         # Conditional edges
    │   │
    │   └── llm/
    │       └── llm_client.py   # OpenAI-совместимый клиент
    │
    └── __init__.py
```

---

## Разработка

### Локальный запуск без Docker

```bash
# Установка зависимостей
uv sync

# Запуск PostgreSQL (например, через Docker)
docker run -d --name postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=evraz_rag \
  -p 5432:5432 \
  postgres:16-alpine

# Запуск Qdrant
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant:latest

# Запуск Ollama
docker run -d --name ollama -p 11434:11434 ollama/ollama:latest
docker exec ollama ollama pull BAAI/bge-m3

# Миграции БД
alembic upgrade head

# Запуск backend
uvicorn src.main:app --reload --port 8000
```

### Добавление миграции

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Тестирование API

```bash
# Загрузка файла
curl -X POST http://localhost:8000/files/upload \
  -F "file=@data/data_proportional_prices.xlsx"

# Вопрос
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Какая цена меди?", "mode": "auto"}'

# Трейс
curl http://localhost:8000/trace
```

---

## Лицензия

Проект разработан в рамках учебной практики по программированию для компании ЕВРАЗ.
