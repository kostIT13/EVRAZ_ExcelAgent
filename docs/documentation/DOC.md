# Документация проекта EVRAZ Agent

## Назначение

EVRAZ Agent — веб-приложение для загрузки и анализа Excel-файлов с данными о ценах на металлы и производственных показателях. Система сохраняет исходные данные, преобразует их в аналитическую витрину PostgreSQL и отвечает на вопросы на естественном языке с помощью LLM-агента.

## Возможности

- Загрузка Excel-файлов и фоновый разбор листов, столбцов, ячеек и комментариев.
- Нормализация цен и производственных метрик в таблицы витрины.
- Поиск сущностей и сопоставление вариантов названий материалов и поставщиков.
- Ответы агента на вопросы по данным с диалоговым контекстом, уточнениями и графиками.
- Просмотр файлов, метрик и трассировки выполнения через веб-интерфейс.
- REST API, аутентификация API-ключом и ограничение частоты запросов.

## Архитектура

Проект состоит из следующих частей:

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy и LangGraph. Код API расположен в `src/api`, настройки и работа с базой — в `src/core`, прикладные сервисы — в `src/services`.
- **Frontend:** React 18, TypeScript и Vite. Страницы приложения находятся в `frontend/src/pages`.
- **База данных:** PostgreSQL 16. Исходные данные хранятся в таблицах схемы `public`, нормализованные факты — в `mart.price_facts` и `mart.metrics`.
- **Инфраструктура:** Docker Compose запускает базу, backend, frontend, Prometheus и Grafana.
- **LLM:** используется настроенный OpenAI-совместимый провайдер; параметры подключения задаются через `.env`.

### Обработка данных

1. Пользователь загружает Excel-файл через интерфейс или `POST /files/upload`.
2. Фоновая очередь разбирает книгу и сохраняет листы, колонки, ячейки и комментарии.
3. Сервис распознаёт тип листа и нормализует данные в таблицы витрины.
4. Справочники сущностей индексируются для последующего сопоставления с формулировками пользователя.
5. При запросе агент формирует план, генерирует безопасный read-only SQL к витрине, выполняет его и формирует ответ.

## Структура репозитория

```text
.
├── src/                    # Backend: API, агент, обработка Excel и сервисы
├── frontend/               # React-интерфейс
├── alembic/                # Миграции базы данных
├── tests/                  # Юнит-, интеграционные и golden-тесты
├── data/                   # Данные и примеры для локальной разработки
├── docs/                   # Материалы проекта и инструкции для демонстраций
├── diagrams/               # Диаграммы архитектуры и потоков
├── scripts/                # Конфигурации мониторинга и служебные скрипты
├── docker-compose.yml      # Локальный запуск полного стека
├── pyproject.toml          # Зависимости и настройки Python-проекта
└── frontend/package.json   # Зависимости и команды frontend
```

## Запуск через Docker Compose

Требуются Docker и Docker Compose v2. Из корня репозитория скопируйте `.env.example` в `.env`, задайте параметры LLM и PostgreSQL, затем выполните:

```bash
docker compose up --build
```

Миграции применяются командой:

```bash
docker compose exec service alembic upgrade head
```

Основные адреса:

- Frontend: <http://localhost:8080>
- Backend API и Swagger: <http://localhost:8000/docs>
- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3001>

## Локальная разработка

Backend требует Python 3.12+, доступную PostgreSQL 16 с расширением `pg_trgm` и настроенный `.env`.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
uv pip install -e .
alembic upgrade head
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Для frontend в отдельном терминале:

```bash
cd frontend
npm install
npm run dev
```

## Конфигурация

Настройки загружаются из `.env`; актуальный список параметров и пример значений находятся в [`.env.example`](.env.example), описание модели настроек — в [`src/core/config.py`](src/core/config.py). Ключевые группы настроек:

- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_PRIMARY` — подключение к LLM;
- `POSTGRES_*` или `POSTGRES_URL` — подключение к PostgreSQL;
- `API_KEY` — защита API (пустое значение отключает проверку ключа для локальной разработки);
- `DB_STATEMENT_TIMEOUT_MS`, `RATE_LIMIT_*`, `INGESTION_QUEUE_MODE` — выполнение SQL, лимиты API и очередь обработки.

Не добавляйте реальные секреты из `.env` в систему контроля версий.

## Основные API-маршруты

- `GET /health` — состояние backend.
- `POST /files/upload`, `GET /files` и `GET /files/{id}/status` — загрузка и контроль обработки файлов.
- `POST /ask` — вопрос к агенту; `/ask/resume` продолжает диалог после уточнения, `/ask/chart` формирует график.
- `GET /trace` — трассировки запросов.
- `GET /metrics` и `GET /metrics/summary` — метрики приложения.

Полная интерактивная спецификация доступна в Swagger по адресу `/docs` при запущенном backend.

## Проверки

Юнит-тесты запускаются из корня проекта:

```bash
pytest tests/ -m "not golden and not integration"
```

Интеграционные тесты требуют отдельную тестовую PostgreSQL и переменную `TEST_POSTGRES_URL`. Golden-тесты требуют настроенную LLM и загруженные данные. Подробности приведены в [`tests/README.md`](tests/README.md).

## Дополнительная документация

- [`README.md`](README.md) — подробный обзор возможностей, API и конфигурации.
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — запуск Docker и локальной среды, миграции и устранение неполадок.
- [`src/README.md`](src/README.md) — устройство backend.
- [`frontend/README.md`](frontend/README.md) — страницы и разработка frontend.
- [`src/services/agent/README.md`](src/services/agent/README.md) — граф и узлы агента.
- [`src/core/db/README.md`](src/core/db/README.md) — схема базы данных.
- [`diagrams/README.md`](diagrams/README.md) — диаграммы проекта.

