# CI — непрерывная интеграция

Проект использует **GitHub Actions** для непрерывной интеграции. Единственный
workflow — [`ci.yml`](workflows/ci.yml) — запускает юнит- и интеграционные тесты
при каждом push в `main`/`master` и на каждый pull request.

## Обзор

```mermaid
flowchart TD
    TRIGGER{{"push в main/master или pull_request"}} --> CI

    subgraph CIJOB ["ci.yml — CI (unit + integration)"]
        U["unit<br/>pytest -m 'not golden and not integration'<br/>Ubuntu, Python 3.12, без БД"]
        I["integration<br/>pytest tests/integration -m integration<br/>service: postgres:16, TEST_POSTGRES_URL"]
    end

    U -. "needs" .-> I
```

## Workflow: `ci.yml`

| Параметр | Значение |
|---|---|
| Файл | [`.github/workflows/ci.yml`](workflows/ci.yml) |
| Триггеры | `push` в `main`/`master`, `pull_request` |
| Runner | `ubuntu-latest` |
| Python | 3.12 (с кэшем pip) |

### Job `unit` — юнит-тесты (без БД и LLM)

- Устанавливает зависимости: `pip install -e .`
- Запускает тесты без golden- и интеграционных маркеров:

  ```bash
  pytest tests/ -m "not golden and not integration" -v
  ```

- Не требует внешних сервисов (PostgreSQL, LLM) и выполняется первым.

### Job `integration` — интеграционные тесты (PostgreSQL)

- Зависит от job `unit` (`needs: unit`).
- Поднимает сервис-контейнер `postgres:16` с healthcheck:

  | Переменная | Значение |
  |---|---|
  | `POSTGRES_USER` | `evraz` |
  | `POSTGRES_PASSWORD` | `evraz_secret` |
  | `POSTGRES_DB` | `evraz_test` |
  | Порт | `5432` |

- Передаёт в окружение `TEST_POSTGRES_URL`:

  ```
  postgresql+asyncpg://evraz:evraz_secret@localhost:5432/evraz_test
  ```

- Запускает интеграционные тесты:

  ```bash
  pytest tests/integration/ -m integration -v
  ```

## Маркеры pytest

Маркеры объявлены в [`pyproject.toml`](../pyproject.toml):

| Маркер | Описание | В CI |
|---|---|---|
| `golden` | Golden-dataset тесты (требуют LLM и данные) | ❌ не запускаются |
| `integration` | Интеграционные тесты с реальной PostgreSQL | ✅ job `integration` |

## Локальный запуск

```bash
# Юнит-тесты (как в CI)
pytest tests/ -m "not golden and not integration" -v

# Интеграционные тесты (нужен запущенный PostgreSQL)
export TEST_POSTGRES_URL="postgresql+asyncpg://evraz:evraz_secret@localhost:5432/evraz_test"
pytest tests/integration/ -m integration -v

# Все тесты (golden пропустятся без --golden)
pytest tests/
```

Без `TEST_POSTGRES_URL` интеграционные тесты пропускаются, golden-тесты — без
флага `--golden`.

## Связанные материалы

- Схема CI/CD: [`diagrams/ci_cd.md`](../diagrams/ci_cd.md)
- Workflow: [`.github/workflows/ci.yml`](workflows/ci.yml)