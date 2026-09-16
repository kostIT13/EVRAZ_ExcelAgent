# EVRAZ Agent — Агентная часть (LangGraph)

LLM-агент «вопрос → SQL → ответ»: преобразует естественно-языковые вопросы пользователя
в безопасный SQL по витрине данных `mart.*`, выполняет его в PostgreSQL и формирует
прозрачный ответ с полным трейсом выполнения.

- Оркестрация: **LangGraph** (StateGraph)
- Чекпоинты: **PostgreSQL** (`langgraph-checkpoint-postgres`)
- Промпты: [`prompts.py`](prompts.py)
- Схемы структурированного вывода: [`structured_schemas.py`](structured_schemas.py)

---

## Оглавление

- [Структура модуля](#структура-модуля)
- [Граф агента](#граф-агента)
- [Узлы](#узлы)
- [Маршрутизация и ретраи](#маршрутизация-и-ретраи)
- [Статусы результата](#статусы-результата)
- [Безопасность SQL](#безопасность-sql)
- [Безопасный компилятор SQL](#безопасный-компилятор-sql)
- [Поток вопроса](#поток-вопроса)
- [Смежные части проекта](#смежные-части-проекта)

---

## Структура модуля

```
src/services/agent/
├── graph.py                   # построение графа, LangGraphAgent, AgentResult
├── graph_state.py             # состояние графа (GraphState) и константы узлов
├── checkpointer.py            # менеджер Postgres-checkpointer'а (lazy init)
├── prompts.py                 # системные промпты для узлов
├── structured_schemas.py      # Pydantic-схемы structured output
├── sql_compiler.py            # безопасный компилятор спеки в SELECT
└── nodes/
    ├── __init__.py
    ├── classifier_node.py     # классификация запроса и сущностей
    ├── disambiguation_node.py # уточнение вопроса (interrupt / auto)
    ├── planner_node.py        # план действий
    ├── codegen_node.py        # генерация и валидация SQL
    ├── executor_node.py       # выполнение SQL в PostgreSQL
    ├── verifier_node.py       # LLM-проверка корректности
    ├── answer_node.py         # финальный ответ
    ├── entity_resolution_node.py  # разрешение сущностей
    └── routing.py             # условные переходы между узлами
```

---

## Граф агента

Граф описывается в [`graph.py`](graph.py) (функция `build_agent_graph`) и компилируется
лениво в `LangGraphAgent._get_graph` с чекпоинтером на PostgreSQL.

```
Classifier → Disambiguation → Planner → CodeGen → Executor → Verifier → Answer
     │             │              │         │          │           │
     └──► failed (при критических ошибках на любом шаге)
```

Условные рёбра (`routing.py`) позволяют:
- пропустить Disambiguation, если уточнение не требуется;
- вернуться на CodeGen при ошибках SQL/валидации/верификации;
- завершиться через `Answer` или `Failed`.

---

## Узлы

| Узел | Модуль | Назначение |
|---|---|---|
| **Classifier** | [`nodes/classifier_node.py`](nodes/classifier_node.py) | определяет тип запроса (`lookup`, `aggregate`, `cross_sheet`, `delta`, `sum_by_supplier`, `find_period`, `unknown`) и домен (`prices`/`metrics`/`generic`), извлекает сущности |
| **Disambiguation** | [`nodes/disambiguation_node.py`](nodes/disambiguation_node.py) | проверяет необходимость уточнения; при необходимости ветвится через `interrupt()` (ожидание ответа пользователя) либо авто-разрешает |
| **Planner** | [`nodes/planner_node.py`](nodes/planner_node.py) | строит текстовый план действий (`PlannerResult`) |
| **CodeGen** | [`nodes/codegen_node.py`](nodes/codegen_node.py) | генерирует SQL (LLM или детерминированно из спеки через `sql_compiler`), применяет детерминированные правки и валидирует |
| **Executor** | [`nodes/executor_node.py`](nodes/executor_node.py) | выполняет read-only SQL с `statement_timeout`; при пустом результате пробует fallback-SQL |
| **Verifier** | [`nodes/verifier_node.py`](nodes/verifier_node.py) | LLM-проверка корректности SQL+результата; до 3 попыток, извлечение JSON; при недоступности модели — детерминированный fallback (confidence 0.75) |
| **Answer** | [`nodes/answer_node.py`](nodes/answer_node.py) | формирует финальный естественно-языковой ответ |

Дополнительно: `entity_resolution_node` — сопоставление сущностей вопроса со справочниками
(item_name / supplier / sheet_period) через fuzzy-поиск.

---

## Маршрутизация и ретраи

[`nodes/routing.py`](nodes/routing.py):

| Переход | Логика |
|---|---|
| `route_after_classifier` | сущности не найдены/домен неизвестен → Disambiguation; иначе → Planner |
| `route_after_disambiguation` | уточнение получено → Planner; иначе → Failed |
| `route_after_planner` | план построен → CodeGen; ошибка → Failed |
| `route_after_codegen` | пустой SQL/ошибки валидации → повторный CodeGen (до `MAX_RETRY_COUNT=3`), иначе → Failed |
| `route_after_executor` | ошибка SQL → CodeGen; успех → Verifier |
| `route_after_verifier` | `needs_retry` → CodeGen; иначе → Answer |

Также работает **self-correction** на уровне pipeline ([`src/services/generation/pipeline.py`](../generation/pipeline.py)):
при `low_confidence` результат перепроверяется.

---

## Статусы результата

По значению `confidence` в `AgentResult`:

| Условие | Статус |
|---|---|
| `confidence >= 0.7` | `success` |
| иначе | `low_confidence` (запускает self-correction) |
| ошибки графа | `failed` |
| ожидание уточнения | `waiting_for_input` |

Ответ содержит: `answer`, `sql_query`, `sql_result` (превью), `request_id`, `trace`,
`query_type`, `retry_count`, `chart_data` (если результат — временной ряд) и др.
(см. dataclass `AgentResult` в [`graph.py`](graph.py)).

---

## Безопасность SQL

Все SQL-запросы проходят валидацию в [`nodes/codegen_node.py`](nodes/codegen_node.py) (`validate_sql`):

- ✅ Только `SELECT` — whitelist таблиц `mart.price_facts`, `mart.metrics`;
- ✅ Whitelist колонок и разрешённых агрегаций (`AVG/SUM/MIN/MAX/COUNT`);
- 🚫 Blacklist ключевых слов: `INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/GRANT/REVOKE/EXECUTE/COPY/VACUUM`;
- ✅ Баланс круглых скобок и одинарных кавычек (детекция обрезанного SQL);
- ⏱ `statement_timeout` на уровне сессии (`DB_STATEMENT_TIMEOUT_MS`).

### Детерминированные правки

- «все виды меди» → префиксный фильтр `item_name ILIKE 'Лом меди%'`;
- нормализация поставщиков: `'Сплав-21'` → `'%сплав21%'` (дефисы/пробелы);
- `is_blank = false/true` → целые `0/1` (колонка хранится как INTEGER).

---

## Безопасный компилятор SQL

[`sql_compiler.py`](sql_compiler.py) — надёжная альтернатива текстовой LLM-генерации:

- `compile_spec()` компилирует структурированную спеку в безопасный `SELECT`;
- ограничивает набор таблиц/колонок/операторов/агрегаций;
- `is_blank` трактуется как целое (0/1).

Используется как fallback в codegen-узле, когда текстовая генерация недостаточно надёжна.

---

## Поток вопроса

1. Пользователь задаёт вопрос через `POST /ask`;
2. `pipeline.run_agent()` запускает граф (кэш вопросов проверяется до прогона);
3. Classifier определяет домен/тип и сущности (entity-resolution);
4. При необходимости — Disambiguation (interrupt с вариантами уточнения);
5. Planner → CodeGen генерирует и валидирует SQL;
6. Executor выполняет SQL в PostgreSQL (read-only);
7. Verifier проверяет корректность;
8. Answer формирует ответ; результат логируется в `query_logs` (трейс по узлам).

Пример вопроса: *«Покажи среднюю цену лома меди у Сплав-21 за январь»*
→ `SELECT AVG(value) FROM mart.price_facts WHERE item_name ILIKE 'Лом меди%' AND supplier ILIKE '%сплав21%' AND sheet_period = '2025-01'`

---

## Смежные части проекта

- [Backend](../../README.md) — FastAPI-сервис, POST /ask
- [База данных](../../core/db/README.md) — витрина mart, чекпоинты
- [LLM-клиент](../llm/llm_client.py) и [structured output](../llm/structured.py) — ретраи и Pydantic-вывод
- [Корневой README](../../../README.md) — общее описание проекта