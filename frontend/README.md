# EVRAZ Agent — Frontend (React)

Frontend-часть проекта: одностраничное приложение для работы с агентной системой —
чат с LLM-агентом, загрузка Excel-файлов, дашборд, метрики, трейсы выполнения
и страница «Демо» — прогон контрольных примеров ПМИ (Приложение А) с автопроверками
на живом стенде.

- Стек: **React 18** + **TypeScript** + **Vite**
- Роутинг: `react-router-dom` · Графики: `chart.js` · Анимации: `framer-motion`
- Зависимости: [`frontend/package.json`](package.json)

---

## Оглавление

- [Структура](#структура)
- [Страницы](#страницы)
- [Компоненты](#компоненты)
- [API-клиент](#api-клиент)
- [Запуск](#запуск)
- [Сборка в Docker](#сборка-в-docker)

---

## Структура

```
frontend/
├── index.html                  # HTML-оболочка Vite
├── vite.config.ts              # конфигурация Vite (прокси на :8000)
├── nginx.conf                  # конфигурация Nginx для продакшена
├── package.json                # зависимости и скрипты
└── src/
    ├── main.tsx                # точка входа React
    ├── App.tsx                 # роутер и layout
    ├── styles/main.css         # глобальные стили
    ├── api/index.ts            # клиент REST API (axios/fetch)
    ├── data/pmiAnnexA.ts       # чек-лист Приложения А ПМИ (данные демо-страницы)
    ├── data/pmiRunBook.ts      # рабочая книга прогона: речь, вопросы, автопроверки по каждому пункту
    ├── types/api.ts            # TypeScript-типы ответов API
    ├── hooks/useToast.ts       # уведомления (toast)
    ├── lib/                    # утилиты (sheet.ts, utils.ts, pmiProbes.ts, pmiChecks.ts)
    ├── components/
    │   ├── chat/               # компоненты чата
    │   ├── files/              # компоненты файлов
    │   ├── layout/             # шапка, фон, анимированные страницы
    │   ├── pmi/                # страница «Демо» (AnnexRunner)
    │   ├── trace/              # карточки/инспектор шагов, waterfall трейса
    │   └── ui/                 # базовые UI (Modal, Tabs, Toast, EmptyState)
    └── pages/                  # страницы приложения
```

---

## Страницы

| Страница | Файл | Возможности |
|---|---|---|
| **Чат** | [`pages/ChatPage.tsx`](src/pages/ChatPage.tsx) | вопросы к агенту, история, прогресс шагов графа, SQL-блок, таблица/график результата, источники ответа |
| **Демо (ПМИ)** | [`pages/DemoPage.tsx`](src/pages/DemoPage.tsx) | прогон Приложения А ПМИ (А-1…А-17): требования, шаги, вопросы в чат, речь для комиссии, автопроверки на живом стенде, вердикты и выгрузка протокола (приложение Б) |
| **Файлы** | [`pages/FilesPage.tsx`](src/pages/FilesPage.tsx) | загрузка `.xlsx`, список файлов и статусы, просмотр листов (`SheetViewer`) |
| **Дашборд** | [`pages/DashboardPage.tsx`](src/pages/DashboardPage.tsx) | общая панель состояния системы |
| **Метрики** | [`pages/MetricsPage.tsx`](src/pages/MetricsPage.tsx) | Prometheus-метрики (RPS, латентность, статусы) |
| **Трейсы** | [`pages/TracePage.tsx`](src/pages/TracePage.tsx) | детальный просмотр выполнения графа агента по шагам |

---

## Компоненты

### Чат ([`components/chat/`](src/components/chat/))
- `AgentProgress` — индикатор текущего шага агента (Classifier → … → Answer);
- `ChatMessage` — сообщение пользователя/агента (markdown-рендер);
- `ResultChart` — график на Chart.js, если `chart_available`;
- `ResultTable` — табличный вывод `sql_result`;
- `SourcesModal` — источники ответа (листы/ячейки);
- `SqlBlock` — отображение сгенерированного SQL с подсветкой;
- `TypingIndicator` — анимация «печатает…».

### Файлы ([`components/files/`](src/components/files/))
- `FileUpload` — drag-and-drop загрузка;
- `FileList` — список файлов со статусами обработки;
- `SheetViewer` — просмотр структуры листа (колонки, ячейки, комментарии).

### UI и прочее
- [`components/ui/`](src/components/ui/) — `Modal`, `Tabs`, `Toast`, `EmptyState`;
- [`components/layout/`](src/components/layout/) — `Header`, `Background`, `AnimatedPage`;
- [`components/pmi/AnnexRunner.tsx`](src/components/pmi/AnnexRunner.tsx) — прогон чек-листа
  Приложения А ПМИ: вкладка на каждый контрольный пример, автопроверки стенда, вердикты
  комиссии и выгрузка протокола (приложение Б) + шпаргалки спикера;
- [`lib/pmiProbes.ts`](src/lib/pmiProbes.ts) — живые пробы стенда (`/health`, `/files`,
  `/trace`, `/metrics/summary`, `/llm/config`) для карточек прогона;
- [`lib/pmiChecks.ts`](src/lib/pmiChecks.ts) — автопроверки пунктов: настоящие вызовы API
  (загрузка файлов, `/ask`, трассы, метрики, OpenAPI) с доказательством в строках фактов;
- [`components/pmi/ModelSwitcher.tsx`](src/components/pmi/ModelSwitcher.tsx) — панель А-5:
  смена модели прямо в демо (`GET /llm/models`, `PUT /llm/model`, `POST /llm/model/reset`)
  с проверкой ответа кандидата и подтверждением через `GET /llm/config`;
- [`components/pmi/BenchmarkFiveRunner.tsx`](src/components/pmi/BenchmarkFiveRunner.tsx) —
  панель А-6: прогон пяти задач Заказчика из браузера (те же вопросы и допуск 1 %, что у
  `benchmark/run_first5.py`) с PASS RATE, флагом «из кэша» по `from_cache` и ссылкой на трассу;
- [`components/trace/`](src/components/trace/) — `TraceStepCard` (карточка шага трейса),
  `StepInspector` (детали шага), `TraceWaterfall` (waterfall-диаграмма узлов графа).

---

## API-клиент

- [`src/api/index.ts`](src/api/index.ts) — единая точка обращения к backend;
- [`src/types/api.ts`](src/types/api.ts) — типы: `AskResponse`, `AskRequest`, `FileInfo`,
  `SheetInfo`, `TraceInfo` и др.

В dev-режиме Vite проксирует запросы на backend (`localhost:8000`) через `vite.config.ts`.
Продакшен-сборка раздаётся Nginx (`nginx.conf`) с проксированием `/api` на сервис.

---

## Запуск

### Dev-режим

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173  (прокси на backend :8000)
```

### Продакшен-сборка

```bash
npm run build          # tsc -b && vite build
npm run preview        # локальный предпросмотр собранного бандла
```

### Docker (через корневой docker-compose)

```bash
docker compose up --build frontend
# → http://localhost:8080 (Nginx)
```

---

## Сборка в Docker

Образ собирается из корня проекта:

```yaml
# docker-compose.yml
frontend:
  build:
    context: .
    dockerfile: Dockerfile.frontend   # multi-stage: node build → nginx
  ports:
    - "8080:80"
    - "80:80"
```

Порядок сборки: `node`-стейдж компилирует TypeScript/Vite, финальный образ на базе
Nginx раздаёт статику и проксирует API-запросы на backend-сервис.

---

## Смежные части проекта

- [Backend](../src/README.md) — FastAPI-сервис и REST API
- [База данных](../src/core/db/README.md) — схемы public/mart, миграции Alembic
- [Корневой README](../README.md) — общее описание проекта