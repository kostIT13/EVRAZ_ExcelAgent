# EVRAZ Agent — Frontend (React)

Frontend-часть проекта: одностраничное приложение для работы с агентной системой —
чат с LLM-агентом, загрузка Excel-файлов, дашборд, метрики и трейсы выполнения.

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
    ├── types/api.ts            # TypeScript-типы ответов API
    ├── hooks/useToast.ts       # уведомления (toast)
    ├── lib/                    # утилиты (sheet.ts, utils.ts)
    ├── components/
    │   ├── chat/               # компоненты чата
    │   ├── files/              # компоненты файлов
    │   ├── layout/             # шапка, фон, анимированные страницы
    │   ├── trace/              # карточка шага трейса
    │   └── ui/                 # базовые UI (Modal, Tabs, Toast, EmptyState)
    └── pages/                  # страницы приложения
```

---

## Страницы

| Страница | Файл | Возможности |
|---|---|---|
| **Чат** | [`pages/ChatPage.tsx`](src/pages/ChatPage.tsx) | вопросы к агенту, история, прогресс шагов графа, SQL-блок, таблица/график результата, источники ответа |
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
- [`components/trace/TraceStepCard.tsx`](src/components/trace/TraceStepCard.tsx) — карточка шага трейса.

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