# Инструкция по запуску приложения EVRAZ Agent

Документ описывает все способы запуска приложения: через Docker Compose (рекомендуемый) и вручную (локальная разработка).

---

## Содержание

1. [Требования](#1-требования)
2. [Настройка конфигурации (.env)](#2-настройка-конфигурации-env)
3. [Запуск через Docker Compose (рекомендуется)](#3-запуск-через-docker-compose-рекомендуется)
4. [Локальный запуск без Docker (разработка)](#4-локальный-запуск-без-docker-разработка)
5. [Порты и адреса сервисов](#5-порты-и-адреса-сервисов)
6. [Миграции БД (Alembic)](#6-миграции-бд-alembic)
7. [Запуск тестов](#7-запуск-тестов)
8. [Остановка приложения](#8-остановка-приложения)
9. [Устранение неполадок](#9-устранение-неполадок)

---

## 1. Требования

### Для Docker-запуска

- **Docker** версии 20+ с Docker Compose v2 (`docker compose`).
- Свободные порты: `5432`, `8000`, `8080`, `80`, `9090`, `3001`.

### Для локального запуска

- **Python** 3.12+
- **Node.js** 18+ (для фронтенда) и npm
- **PostgreSQL** 16+ с расширением `pg_trgm`
- Менеджер пакетов **uv** (рекомендуется) либо pip

---

## 2. Настройка конфигурации (.env)

1. Скопируйте пример конфигурации:

   ```bash
   cp .env.example .env
   ```

2. Откройте `.env` и заполните обязательные параметры:

   | Переменная | Значение |
   |---|---|
   | `LLM_BASE_URL` | базовый URL LLM-провайдера (OpenAI-совместимый) |
   | `LLM_API_KEY` | API-ключ LLM |
   | `LLM_MODEL_PRIMARY` | основная модель (например `deepseek-ai/DeepSeek-V4-Flash`) |
   | `LLM_MODEL_CHEAP` | быстрая/дешёвая модель |
   | `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | учётные данные БД |
   | `API_KEY` | API-ключ для `/files/*` и `/ask/*` (пусто = auth отключён в dev) |

   Остальные параметры имеют разумные значения по умолчанию.

> **Важно:** `.env` содержит секреты и не должен попадать в систему контроля версий (он уже добавлен в `.gitignore`).

---

## 3. Запуск через Docker Compose (рекомендуется)

Из корня проекта:

```bash
# 1. Подготовить конфигурацию (если ещё не сделано)
cp .env.example .env
# заполните .env

# 2. Собрать и поднять все сервисы
docker compose up --build
```

Для запуска в фоновом режиме (без блокировки терминала):

```bash
docker compose up --build -d
```

### Применить миграции БД

После первого старта (или при появлении новых миграций) выполните:

```bash
docker compose exec service alembic upgrade head
```

### Проверка запуска

```bash
docker compose ps
```

Ожидаемые контейнеры: `postgres`, `service`, `frontend`, `prometheus`, `grafana`.

Приложение доступно по адресам:

- Backend API: http://localhost:8000
- Frontend UI: http://localhost:8080
- Метрики Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (логин/пароль `admin`/`admin`)

---

## 4. Локальный запуск без Docker (разработка)

### 4.1. Backend (FastAPI)

```bash
# 1. Создать и активировать виртуальное окружение
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 2. Установить зависимости (через uv)
uv pip install -e .

# 3. Подготовить .env (см. раздел 2)
cp .env.example .env

# 4. Применить миграции (PostgreSQL должен быть запущен)
alembic upgrade head

# 5. Запустить сервер
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Backend поднимется на http://localhost:8000. Swagger-документация доступна на http://localhost:8000/docs.

> **Примечание:** для локального запуска в `.env` измените `POSTGRES_HOST` с `postgres` на `localhost` (или адрес вашего PostgreSQL).

### 4.2. Frontend (React + Vite)

В отдельном терминале из каталога `frontend/`:

```bash
cd frontend
npm install
npm run dev
```

Dev-сервер Vite по умолчанию стартует на http://localhost:5173. Убедитесь, что в коде фронтенда указан корректный URL API (по умолчанию проксируется на `:8000`).

---

## 5. Порты и адреса сервисов

| Сервис | Docker Compose | Локально (dev) |
|---|---|---|
| PostgreSQL | `localhost:5432` | `localhost:5432` |
| Backend (FastAPI) | `localhost:8000` | `localhost:8000` |
| Frontend (React) | `localhost:8080` (nginx) | `localhost:5173` (Vite) |
| Prometheus | `localhost:9090` | — |
| Grafana | `localhost:3001` | — |
| Swagger /docs | `localhost:8000/docs` | `localhost:8000/docs` |

---

## 6. Миграции БД (Alembic)

Применить миграции (Docker):

```bash
docker compose exec service alembic upgrade head
```

Применить миграции (локально):

```bash
alembic upgrade head
```

Откатить на одну миграцию назад:

```bash
alembic downgrade -1
```

Показать текущую версию:

```bash
alembic current
```

---

## 7. Запуск тестов

### Юнит-тесты (без LLM)

```bash
# Docker
docker compose exec service pytest tests/

# Локально
pytest tests/
```

### Интеграционные golden-тесты (требуют LLM и данные)

```bash
pytest --golden tests/
```

---

## 8. Остановка приложения

Остановить и удалить контейнеры (данные в томах сохраняются):

```bash
docker compose down
```

Полная очистка (включая тома с данными БД и Grafana):

```bash
docker compose down -v
```

> **Внимание:** `-v` удаляет данные PostgreSQL и Grafana. Используйте только при необходимости.

---

## 9. Устранение неполадок

| Проблема | Решение |
|---|---|
| Порты заняты | Остановите процессы на портах `5432/8000/8080/80` или измените маппинг портов в `docker-compose.yml` |
| `pg_trgm` не установлен | Расширение создаётся автоматически при старте через `scripts/init-db`. При ручной установке выполните `CREATE EXTENSION IF NOT EXISTS pg_trgm;` |
| Ошибка подключения к БД | Проверьте `POSTGRES_*` в `.env`; при локальном запуске `POSTGRES_HOST` должен быть `localhost`, а не `postgres` |
| Миграции не применены | Выполните `docker compose exec service alembic upgrade head` |
| Пустые ответы агента | Проверьте `LLM_BASE_URL`, `LLM_API_KEY` и доступность LLM-провайдера |
| Ошибка `Connection refused` при загрузке файла | Убедитесь, что ingestion-очередь (`INGESTION_QUEUE_MODE`) в рабочем состоянии (`inproc`) |
| Фронтенд не открывается | Проверьте, что контейнер `frontend` работает (`docker compose ps`) и порт `8080` не занят |

---

## Упрощённый запуск «одной командой»

```bash
cp .env.example .env   # + заполнить .env
docker compose up --build -d
docker compose exec service alembic upgrade head
```

После этого открывайте http://localhost:8080 — интерфейс приложения готов к работе.