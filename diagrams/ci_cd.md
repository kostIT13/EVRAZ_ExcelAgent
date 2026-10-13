# CI / CD — GitHub Actions

Один workflow: [`ci.yml`](../.github/workflows/ci.yml) — юнит-тесты (без БД и LLM)
и интеграционные тесты с реальным PostgreSQL. Golden-тесты (LLM) в CI не запускаются.

```mermaid
flowchart TD
    TRIGGER{{"push в main/master или pull_request"}} --> CI

    subgraph CIJOB ["ci.yml — CI (unit + integration)"]
        U["unit<br/>pytest -m 'not golden and not integration'<br/>Ubuntu, Python 3.12, без БД"]
        I["integration<br/>pytest tests/integration -m integration<br/>service: postgres:16, TEST_POSTGRES_URL"]
    end

    U -. "needs" .-> I
```

```mermaid
sequenceDiagram
    participant GH as GitHub
    participant UJ as Job "unit" (Ubuntu)
    participant IJ as Job "integration" (Ubuntu)
    participant PG as Service postgres:16

    GH->>UJ: checkout + setup-python + pip install -e .
    UJ->>UJ: pytest -m "not golden and not integration"
    GH->>IJ: после unit (needs)
    GH->>PG: запуск postgres:16 (healthcheck)
    IJ->>IJ: pytest tests/integration -m integration
    IJ->>PG: TEST_POSTGRES_URL → public+mart схемы
    Note over IJ,PG: интеграционные тесты создают и удаляют таблицы
```

## Детали

| Job | Команда | Требования |
|---|---|---|
| `unit` | `pytest tests/ -m "not golden and not integration" -v` | нет |
| `integration` | `pytest tests/integration/ -m integration -v` | `TEST_POSTGRES_URL` (service-контейнер) |

Локально: `pytest tests/` — юнит-тесты идут, integration пропускаются без
`TEST_POSTGRES_URL`, golden — без `--golden`.