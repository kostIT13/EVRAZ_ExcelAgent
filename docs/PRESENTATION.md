# EVRAZ Agent
## AI-агент для работы с Excel-файлами металлургической компании

**Демонстрация проекта**

*Backend: Python 3.12 · FastAPI · LangGraph · PostgreSQL*
*Frontend: React 18 · TypeScript · Vite*

---

# Проблематика

- Ежедневные **Excel-файлы с ценами на цветные металлы (лом)** — десятки листов, разные форматы
- Файлы **«грязные»**: сдвинутые шапки, merged cells, вложенные заголовки
- Бизнес-пользователи хотят **отвечать на вопросы простым языком**, а не разбираться в таблицах
- Цены — **коммерческая тайна**: данные не должны утекать наружу

> **Результат:** менеджер тратит часы на ручной поиск по файлам вместо принятия решений

---

# Задача

Построить **prod-ready систему «вопрос–ответ»** по Excel-данным:

1. Загрузил файл → система сама распарсила и нормализовала
2. Задал вопрос на естественном языке → получил ответ с данными
3. Ответ **прозрачен**: видно, какой SQL выполнен и откуда взялись цифры
4. Безопасно: только чтение, только проверенные таблицы, без утечки данных

**Цель:** точность ≥ 85% на ключевых типах запросов при полной traceability ответа

---

# Решение — обзор

```
Excel файл
    │
    ▼
Парсинг (src/core/excel) ──► RAW-таблицы (files, sheets, cells)
    │
    ▼
Нормализация ──► Витрина mart.price_facts / mart.metrics
    │
    ▼
Вопрос пользователя ──► LangGraph-агент ──► Безопасный SELECT
    │                                          │
    ▼                                          ▼
              Ответ + SQL + источники   PostgreSQL
```

**Три части проекта:**

| Часть | Технологии | Назначение |
|---|---|---|
| Backend | FastAPI, LangGraph, SQLAlchemy | API, парсинг, агент |
| Frontend | React 18 + TS + Vite | Чат, файлы, дашборд, метрики, трейсы |
| Инфраструктура | Docker Compose, Nginx | PostgreSQL, Prometheus, Grafana |

---

# Поток обработки файла

1. **Upload** — файл сохраняется, статус `uploaded`
2. **Ingestion (асинхронно)** — парсинг Excel: листы, колонки, ячейки, комментарии
3. **Schema Inference** — LLM предлагает схему для новых форматов;
   известные форматы распознаются по **Template Fingerprint** без LLM
4. **Normalize** — перенос в витрину данных (идемпотентно, повторная заливка без дублей)
5. **Entity Resolution** — сбор справочников сущностей для ответов
6. Статус → `ready` ✅ (или `failed` с текстом ошибки)

```
uploaded → processing → ready | failed
```

---

# Витрина данных (mart)

### `mart.price_facts` — цены лома

| Колонка | Пример |
|---|---|
| `sheet_period` | 2025-01 |
| `item_name` | Лом меди марки А |
| `supplier` | Сплав-21 |
| `price_type` | среднерыночная / аукцион_старт / поставщик |
| `value`, `currency`, `unit` | 486 500, ₽, т |
| `is_blank` | 0/1 (пустые ячейки не превращаются в 0) |

### `mart.metrics` — производственные метрики

`dimension`, `period`, `metric_type`, `metric`, `value`, `unit`, `is_blank`

> Long-факт-таблицы: агент генерирует простой SQL без обращения к сырым ячейкам

---

# LangGraph-агент

Граф узлов с чекпоинтами в PostgreSQL и ретраями:

```
Classifier → Disambiguation → Planner → CodeGen → Executor → Verifier → Answer
```

| Узел | Что делает |
|---|---|
| **Classifier** | тип запроса (`lookup`, `aggregate`, `delta`, `cross_sheet`…) и домен (`prices`/`metrics`) |
| **Disambiguation** | уточняет вопрос, если нужно (interrupt или авто-разрешение) |
| **Planner** | текстовый план действий |
| **CodeGen** | генерация SQL + детерминированные правки + валидация |
| **Executor** | выполняет read-only SQL, при пустом результате — fallback-SQL |
| **Verifier** | LLM-проверка корректности (до 3 попыток + детерминированный fallback) |
| **Answer** | финальный естественно-языковой ответ |

Статусы по `confidence`: `success (≥0.7)` · `low_confidence (self-correction)` · `failed`

---

# Безопасная генерация SQL

Детерминированные правки в CodeGen:

- «Все виды меди» → префиксный фильтр `item_name ILIKE 'Лом меди%'`
- Нормализация поставщиков: `'Сплав-21'` → `'%сплав21%'`
- Булевы поля `is_blank` → целые `0/1`

Валидация перед выполнением:

- ✅ Только `SELECT` (whitelist таблиц `mart.*`)
- 🚫 Blacklist: `INSERT / UPDATE / DELETE / DROP / ALTER / DROP ...`
- ✅ Баланс скобок и кавычек (детекция обрезанного SQL)
- ⏱ `statement_timeout` 30 сек

> Альтернатива LLM: [`sql_compiler.py`](src/services/agent/sql_compiler.py) компилирует структурированную спеку в безопасный SELECT

---

# Entity Resolution

Сопоставление упомянутых в вопросе сущностей с реальными:

- Справочники: `item_name`, `supplier`, `sheet_period`
- **Fuzzy-match** (rapidfuzz) + триграммный поиск PostgreSQL (`pg_trgm`)
- **BM25-индекс** (`data/bm25_index.pkl`) для выбора релевантных листов (`top_k`)
- Кэш результатов разрешения сущностей

Вопрос: *«Средняя цена лома меди у Сплав-21 в январе?»*
→ подставляются **реальные значения-кандидаты** из БД — меньше галлюцинаций названий

---

# Frontend (React + TypeScript)

| Страница | Возможности |
|---|---|
| **Чат** | вопросы к агенту, прогресс шагов, SQL-блок, таблица/график результата, источники |
| **Файлы** | загрузка Excel, статусы обработки, просмотр листов и структуры |
| **Дашборд** | общая панель состояния |
| **Метрики** | Prometheus-метрики системы |
| **Трейсы** | просмотр выполнения графа агента по шагам |

Компоненты: `AgentProgress`, `ChatMessage`, `ResultChart` (Chart.js), `ResultTable`,
`SourcesModal`, `SqlBlock`, `TypingIndicator`, `SheetViewer`, `FileUpload`…

---

# Наблюдаемость

**Prometheus** (`/metrics`):
- RPS и латентность `/ask`
- Per-node latency графа (classifier / planner / codegen / executor / verifier / answer)
- Доля `failed` / `low_confidence`
- Token usage LLM

**query_logs** — журнал запросов: latency по узлам, тексты ошибок, трейсы

**Grafana** (порт 3001) — визуализация, подключена через provisioning

**Логи** — loguru, собираются в Docker Compose

---

# Безопасность и защита

- **API-key auth** (`X-API-Key`) для `/files/*` и `/ask/*`; в dev — отключена
- **Rate limiting** (slowapi): `RATE_LIMIT_ASK = 30/min`, `RATE_LIMIT_UPLOAD = 10/min`
- **Read-only SQL** — агент физически не может изменить данные
- **Секреты** — только через `.env`, рекомендуются secrets-менеджер (Vault)
- **Устойчивость LLM**: ретраи при rate-limit, таймаутах и **пустом ответе модели**;
  structured output (Pydantic) для классификатора и планировщика

---

# Качество: тесты

| Тест | Что проверяет |
|---|---|
| [`test_sql_compiler.py`](tests/test_sql_compiler.py) | безопасный компилятор SQL |
| [`test_normalizer_dimension.py`](tests/test_normalizer_dimension.py) | нормализация измерений |
| [`test_classifier_domain.py`](tests/test_classifier_domain.py) | классификатор доменов |
| [`test_parser_header_detection.py`](tests/test_parser_header_detection.py) | определение шапки Excel |
| [`test_golden_dataset.py`](tests/test_golden_dataset.py) | **golden-датасет** — эталонные вопросы (маркер `golden`) |

```bash
pytest tests/            # юнит-тесты (без LLM)
pytest -m golden tests/  # интеграционные golden-тесты (LLM + данные)
```

Golden-датасет прогоняется в CI при каждом изменении промптов/схемы/нормализации

---

# Демонстрация — сценарий

### Шаг 1. Загрузка файла
Открываем страницу **«Файлы»** → загружаем `xlsx` → система парсит, инферит схему, нормализует в витрину

### Шаг 2. Вопрос в чате
*«Покажи среднюю цену лома меди у поставщика Сплав-21 за январь»*

### Шаг 3. Наблюдаем агента
Прогресс шагов: Classifier → Planner → CodeGen → Executor → Verifier → Answer

### Шаг 4. Проверяем прозрачность
- SQL-запрос, который выполнил агент
- Таблица/график с результатом
- Источники (листы и ячейки)

### Шаг 5. Метрики и трейсы
Смотрим latency узлов в Metrics и полный трейс запроса в Trace

---

# Архитектура развёртывания

| Сервис | Порт | Назначение |
|---|---|---|
| `postgres` | 5432 | PostgreSQL 16 (+ pg_trgm) |
| `service` | 8000 | FastAPI-приложение (Swagger `/docs`) |
| `frontend` | 8080 | React + Nginx |
| `prometheus` | 9090 | сбор метрик |
| `grafana` | 3001 | дашборды (admin/admin) |

```bash
cp .env.example .env        # заполнить LLM_* и POSTGRES_*
docker compose up --build -d
docker compose exec service alembic upgrade head
# → http://localhost:8080
```

---

# Итоги

### Что сделано
- ✅ Асинхронный ingestion Excel → нормализованная витрина данных
- ✅ LangGraph-агент «вопрос → SQL → ответ» с полным трейсом
- ✅ Безопасная генерация SQL (whitelist + blacklist + валидация)
- ✅ Entity Resolution для точного сопоставления сущностей
- ✅ Современный React-интерфейс (чат, файлы, метрики, трейсы)
- ✅ Наблюдаемость: Prometheus + Grafana + журнал запросов
- ✅ Golden-датасет и тесты для контроля качества

### Ключевые принципы
**Нормализация вместо векторного поиска · Детерминизм вместо «магии» LLM · Прозрачность каждого ответа**

---

# Перспективы развития

- Расширение типов вопросов и увеличение golden-датасета
- Поддержка новых форматов листов (Schema Inference уже готов)
- Secrets-менеджер (Vault) для прод-контура
- Интеграция с корпоративной авторизацией (SSO)
- Автоматические алерты в Grafana по качеству ответов
- Мобильный клиент и экспорт отчётов

---

# Спасибо за внимание!

## EVRAZ Agent

**AI-агент для интеллектуальной работы с Excel-файлами**

Вопросы?

---

*Подробности: [`README.md`](README.md) · [`PROJECT.md`](PROJECT.md) · [`INSTRUCTIONS.md`](INSTRUCTIONS.md)*