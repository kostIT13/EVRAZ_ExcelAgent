# CI / CD — GitHub Actions

Два workflow: [`ci.yml`](../.github/workflows/ci.yml) (без LLM) и
[`golden.yml`](../.github/workflows/golden.yml) (LLM-регрессия).

```mermaid
flowchart TD
    TRIGGER{{"push в main/master или pull_request"}} --> CI

    subgraph CIJOB ["ci.yml — CI (unit + integration)"]
        U["unit<br/>pytest -m 'not golden and not integration'<br/>Ubuntu, Python 3.12, без БД"]
        I["integration<br/>pytest tests/integration -m integration<br/>service: postgres:16, TEST_POSTGRES_URL"]
    end

    TRIGGER --> GOLD

    U -. "needs" .-> I

    subgraph GOLDJOB ["golden.yml — LLM-регрессия"]
        U2["unit-tests<br/>pytest -m 'not golden and not integration'"]
        G["golden<br/>postgres service + миграции + demo-data"]
        G2["Отчёт по точности<br/>run_golden_report.py"]
    end

    GOLD --> SEC{{"secrets: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_PRIMARY"}}
    SEC -- "отсутствуют" --> GFALL["golden падает ожидаемо"]

    U2 --> G
    G --> G2
```

```mermaid
sequenceDiagram
    participant GH as GitHub
    participant UJ as Job "unit" (Ubuntu)
    participant IJ as Job "integration" (Ubuntu)
    participant PG as Service postgres:16
    participant GJ as Job "golden" (Ubuntu)

    GH->>UJ: checkout + setup-python + pip install -e .
    UJ->>UJ: pytest -m "not golden and not integration"
    GH->>IJ: после unit (needs)
    GH->>PG: запуск postgres:16 (healthcheck)
    IJ->>IJ: pytest tests/integration -m integration
    IJ->>PG: TEST_POSTGRES_URL → public+mart схемы
    Note over IJ,PG: интеграционные тесты создают и удаляют таблицы
    GH->>GJ: golden (только при наличии LLM-секретов)
    GJ->>PG: alembic upgrade + load_demo_data
    GJ->>GJ: pytest -m golden tests/test_golden_dataset.py
```

## Детали

| Job | Команда | Требования |
|---|---|---|
| `unit` | `pytest tests/ -m "not golden and not integration" -v` | нет |
| `integration` | `pytest tests/integration/ -m integration -v` | `TEST_POSTGRES_URL` (service-контейнер) |
| `unit-tests` (golden.yml) | `pytest tests/ -m "not golden and not integration" -v` | нет |
| `golden` | `alembic upgrade head` → `load_demo_data.py` → `pytest -m golden` | LLM-секреты |

Локально: `pytest tests/` — юнит-тесты идут, integration пропускаются без
`TEST_POSTGRES_URL`, golden — без `--golden`.