# Топология Docker Compose

Развёртывание через [`docker-compose.yml`](../docker-compose.yml). Backend
собирается из `Dockerfile`, frontend — из `Dockerfile.frontend` (Nginx static).

```mermaid
flowchart TD
    U["Браузер пользователя"] --> FE

    subgraph Compose ["Docker Compose (app_network)"]
        subgraph FEBox ["Frontend"]
            FE["Nginx :80/:8080<br/>React static build"]
        end

        subgraph BEBox ["Backend"]
            BE["service :8000<br/>uvicorn src.main:app"]
            VOL["volume: ./data:/app/data, ./src:/app/src"]
        end

        subgraph DBSBox ["Data"]
            PG[("postgres:16-alpine :5432")]
            INIT["scripts/init-db → docker-entrypoint-initdb.d"]
        end

        subgraph OPSBox ["Observability"]
            PROM["prometheus :9090"]
            GRAF["grafana :3001<br/>admin/admin"]
            PROMSVC["prometheus.yml mount"]
            GRAFSVC["grafana datasource provisioning"]
        end
    end

    LLM["LLM API: OpenAI-совместимый"]

    U -->|":8080 или :80"| FE
    FE -->|"/api → :8000"| BE
    BE -->|":5432, asyncpg"| PG
    PG -. "init" .- INIT
    BE -->|"LLM_BASE_URL"| LLM
    BE -->|"/metrics :8000"| PROM
    GRAF -->|"datasource"| PROM
    PROMSVC -. "mount" .- PROM
    GRAFSVC -. "mount" .- GRAF
    VOL -. "mount" .- BE
```

## Порты

| Сервис | Порт (host) | Назначение |
|---|---|---|
| `frontend` | 80 / 8080 | статика React + прокси на API |
| `service` | 8000 | FastAPI (`/docs` — Swagger, `/metrics`) |
| `postgres` | 5432 | PostgreSQL 16 |
| `prometheus` | 9090 | метрики |
| `grafana` | 3001 | дашборды (admin/admin) |

## Запуск

```bash
cp .env.example .env   # заполнить LLM_* и POSTGRES_*
docker compose up --build
```

Healthcheck `postgres` (pg_isready) — `service` стартует после готовности БД.