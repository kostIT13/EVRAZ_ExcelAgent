# EVRAZ Agent — База данных (PostgreSQL + SQLAlchemy + Alembic)

Описание слоя базы данных проекта: подключение, модели, схемы `public`/`mart`, миграции.

- СУБД: **PostgreSQL 16** (в Docker — `postgres:16-alpine`)
- ORM: **SQLAlchemy 2.0** (async, asyncpg)
- Миграции: **Alembic** (`alembic/` в корне проекта)
- Модели: [`models.py`](models.py)
- Движок/сессии: [`database.py`](database.py)
- Базовый класс: [`base.py`](base.py)

---

## Оглавление

- [Файлы модуля](#файлы-модуля)
- [Подключение](#подключение)
- [Схемы](#схемы)
- [Таблицы](#таблицы)
- [Особенности](#особенности)
- [Миграции Alembic](#миграции-alembic)
- [Создание новой миграции](#создание-новой-миграции)
- [Расширения PostgreSQL](#расширения-postgresql)

---

## Файлы модуля

| Файл | Назначение |
|---|---|
| [`base.py`](base.py) | базовый класс `Base` для ORM-моделей (Declarative) |
| [`database.py`](database.py) | асинхронный движок SQLAlchemy, фабрика сессий |
| [`models.py`](models.py) | ORM-модели всех таблиц (`File`, `Sheet`, `Cell`, `PriceFact` и др.) |

---

## Подключение

Параметры подключения берутся из `.env` (`POSTGRES_*`), см. [`src/core/config.py`](../config.py).

- Асинхронный драйвер приложения: **asyncpg**;
- Синхронный драйвер для онлайн-миграций Alembic: **psycopg2**.

Основные настройки:

| Переменная | Описание |
|---|---|
| `POSTGRES_HOST` / `POSTGRES_PORT` | хост и порт PostgreSQL |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | учётные данные |
| `POSTGRES_DB` | имя базы данных |
| `DB_STATEMENT_TIMEOUT_MS` | statement_timeout для SQL агента (по умолч. 30000) |

---

## Схемы

Проект использует две схемы:

| Схема | Назначение |
|---|---|
| `public` | сырые данные (RAW), служебные таблицы, кэш, журналы |
| `mart` | нормализованная витрина данных (только чтение для агента) |

RAW-таблицы хранят исходную структуру загруженных Excel-файлов (аудит, без изменений),
а витрина `mart` — нормализованные long-факт-таблицы, по которым агент генерирует SQL.

---

## Таблицы

### Схема `public`

| Таблица | ORM-класс | Назначение |
|---|---|---|
| `files` | `File` | загруженные файлы (hash, статус, счётчики) |
| `sheets` | `Sheet` | листы (имя, период, kind) |
| `column_metadata` | `ColumnMetadata` | колонки листов (тип, роль, сэмплы) |
| `cells` | `Cell` | сырые ячейки (текст/число/дата) |
| `excel_comments` | `ExcelComment` | комментарии ячеек |
| `entity_dictionary` | `EntityDictionary` | словарь сущностей (canonical + алиасы + embedding) |
| `query_cache` | `QueryCache` | кэш «нормализованный вопрос → SQL → результат» |
| `golden_dataset` | `GoldenDataset` | эталонные вопросы для тестов качества |
| `query_logs` | `QueryLog` | журнал запросов и трейсов агента |

### Схема `mart`

| Таблица | ORM-класс | Назначение |
|---|---|---|
| `price_facts` | `PriceFact` | нормализованные цены лома |
| `metrics` | `Metric` | производственные метрики (план/факт/отклонение/расход/запасы) |
| `sheet_templates` | `SheetTemplate` | шаблоны листов по Template Fingerprint |
| `supplier_aliases` | `SupplierAlias` | алиасы поставщиков (canonical ↔ alias) |

### Структура витрины

`mart.price_facts`:
`id, file_id, sheet_id, sheet_period, item_name, supplier, price_type,
value, currency, unit, is_blank, source_row_ref`

`mart.metrics`:
`id, file_id, sheet_id, dimension, dimension_type, period, metric_type,
metric, value, unit, is_blank, source_row_ref`

> Пустые ячейки сохраняются признаком `is_blank = 1`, а не превращаются в 0.

---

## Особенности

- **Булевы поля** (`is_blank`, `sheet_kind_auto`, `is_active`) объявлены как `INTEGER (0/1)` —
  в SQL их нужно сравнивать с числами, а не с `TRUE/FALSE`.
- **Идемпотентность нормализации** — повторная заливка файла не дублирует факты в витрине.
- **Read-only для агента** — executor-узел выполняет только `SELECT` по whitelist-таблицам `mart.*`.
- **Чекпоинты LangGraph** — состояние графа агента хранится в PostgreSQL
  (см. [`src/services/agent/checkpointer.py`](../../services/agent/checkpointer.py)).
- **Триграммный поиск** — расширение `pg_trgm` используется entity-resolution.

---

## Миграции Alembic

Миграции находятся в `alembic/versions/` (корень проекта) в порядке применения:

| Миграция | Что делает |
|---|---|
| `cee213b86e64_initial.py` | начальная схема |
| `b7a4f21e3c91_mart_and_entity_embeddings.py` | витрина mart + embeddings сущностей |
| `c2d3e4f5a6b7_mart_metrics_and_sheet_kind.py` | mart.metrics, sheet_kind |
| `d9f2c3a1e5b7_remove_vector_tables.py` | удаление векторных таблиц |
| `f1a2b3c4d5e6_fix_app_readonly_password.py` | пароль read-only приложения |
| `a1b2c3d4e5f6_drop_fact_prices.py` | очистка факт-таблицы цен |

Конфигурация Alembic — `alembic/env.py`: читает `POSTGRES_*` из `.env`
и использует **psycopg2** (синхронный драйвер) для онлайн-миграций.
Поддерживается **offline-режим** — генерация SQL-миграций без работающего PostgreSQL.

---

## Создание новой миграции

1. Измените модели в [`models.py`](models.py);
2. Сгенерируйте ревизию (из корня проекта):

```bash
alembic revision --autogenerate -m "описание_изменения"
```

3. Проверьте сгенерированный файл в `alembic/versions/` и примените:

```bash
alembic upgrade head
```

> При изменении моделей не забывайте про интеграционные тесты
> ([`tests/test_golden_dataset.py`](../../../tests/test_golden_dataset.py)).

Полезные команды:

```bash
alembic current          # текущая ревизия
alembic history          # история миграций
alembic downgrade -1     # откат на одну миграцию назад
docker compose exec service alembic upgrade head   # миграции в Docker
```

---

## Расширения PostgreSQL

Инициализируются автоматически при первом старте контейнера через
`scripts/init-db/01-extensions.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- и другие необходимые расширения
```

Для ручной установки в локальной БД:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

---

## Смежные части проекта

- [Backend](../README.md) — сервисы доступа к таблицам (`src/services/db_tables/`)
- [Агент](../../services/agent/README.md) — безопасная генерация SQL по витрине
- [Корневой README](../../../README.md) — общее описание проекта