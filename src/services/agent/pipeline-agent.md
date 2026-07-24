# Agent Pipeline — полное описание

**Agent Pipeline** — интеллектуальный агент на базе LangGraph, который отвечает на вопросы по Excel-данным через цепочку: поиск → классификация → планирование → генерация SQL → выполнение → верификация → ответ.

---

## Содержание

- [Общая схема](#общая-схема)
- [1. Запуск агента](#1-запуск-агента)
- [2. RAG Node — гибридный поиск](#2-rag-node--гибридный-поиск)
- [3. Classifier Node — классификация запроса](#3-classifier-node--классификация-запроса)
- [4. Planner Node — планирование](#4-planner-node--планирование)
- [5. CodeGen Node — генерация SQL](#5-codegen-node--генерация-sql)
- [6. Executor Node — выполнение SQL](#6-executor-node--выполнение-sql)
- [7. Verifier Node — верификация](#7-verifier-node--верификация)
- [8. Answer Node — финальный ответ](#8-answer-node--финальный-ответ)
- [9. Маршрутизация (Conditional Edges)](#9-маршрутизация-conditional-edges)
- [10. Self-Correction](#10-self-correction)
- [11. Полный цикл запроса](#11-полный-цикл-запроса)
- [Ключевые файлы](#ключевые-файлы)

---

## Общая схема

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         LangGraph Agent Graph                            │
│                                                                          │
│  Вход ──▶ [RAG] ──▶ [Classifier] ──▶ [Planner] ──▶ [CodeGen] ──▶ [Executor] ──▶ [Verifier] ──▶ [Answer] ──▶ Выход
│                       │                │              │  ▲              │  ▲              │  ▲
│                       │                │              │  │              │  │              │  │
│                       │                │              │  │              │  │              │  │
│                       └────────────────┘              └──┴──────────────┴──┴──────────────┴──┘
│                                                       retry до 3 раз (CodeGen → Executor → Verifier)
│                                                                          │
│                                                                    [Failed] ──▶ Выход (ошибка)
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                    Self-Correction (вне графа)                            │
│                                                                          │
│  Первый проход ──▶ confidence < 0.5? ──▶ Да ──▶ Второй проход с историей │
│                       │                        ошибок                    │
│                       Нет                                                │
│                       ▼                                                  │
│                  Финальный ответ                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Запуск агента

**Файл:** [`src/services/generation/pipeline.py`](src/services/generation/pipeline.py) — метод [`run_agent()`](src/services/generation/pipeline.py:153)

Агент запускается через `GenerationPipeline.run_agent()`:

```python
async def run_agent(
    self,
    question: str,
    top_k: int = 30,
    session: Optional[AsyncSession] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> AgentResult:
```

**Параметры:**
- `question` — вопрос пользователя
- `top_k` — количество чанков для RAG-поиска (по умолчанию 30, больше чем в RAG-режиме)
- `conversation_history` — история предыдущих попыток для self-correction

**Входная точка в граф:** [`LangGraphAgent.run()`](src/services/agent/graph.py:211)

Создаёт начальное состояние [`GraphState`](src/services/agent/graph_state.py:27):

```python
initial_state = {
    "question": question,
    "request_id": str(uuid.uuid4()),
    "top_k": top_k,
    "rag_context": "",
    "rag_chunks": [],
    "rag_error": None,
    "query_type": None,
    "entities": [],
    "relevant_sheets": [],
    "plan": "",
    "schema": [],
    "sql_query": "",
    "validation_errors": [],
    "sql_result": [],
    "sql_error": None,
    "answer": "",
    "confidence": 0.0,
    "retry_count": 0,
    "needs_retry": False,
    "retry_reason": "",
    "trace": {},
    "error": None,
}
```

---

## 2. RAG Node — гибридный поиск

**Файл:** [`src/services/agent/nodes/rag_node.py`](src/services/agent/nodes/rag_node.py) — функция [`rag_node()`](src/services/agent/nodes/rag_node.py:19)

**Назначение:** Выполнить гибридный поиск (BM25 + Dense) по вопросу пользователя, чтобы получить релевантный контекст для всех последующих узлов.

**Вход:** `question`, `top_k`
**Выход:** `rag_context` (отформатированный текст), `rag_chunks` (сырые результаты)

**Процесс:**
1. Вызов [`rag_service.hybrid_search(query=question, top_k=top_k)`](src/services/rag/rag_service.py:302)
2. Форматирование результатов через [`format_context()`](src/services/generation/rag_prompt.py:29)
3. Сохранение в `state["rag_context"]` и `state["rag_chunks"]`

**Обработка ошибок:** Если поиск упал — `rag_context` остаётся пустым, но граф продолжает работу (Classifier может работать без контекста).

---

## 3. Classifier Node — классификация запроса

**Файл:** [`src/services/agent/nodes/classifier_node.py`](src/services/agent/nodes/classifier_node.py) — функция [`classifier_node()`](src/services/agent/nodes/classifier_node.py:68)

**Назначение:** Определить тип запроса, извлечь сущности и найти релевантные листы.

**Вход:** `question`, `rag_context`
**Выход:** `query_type`, `entities`, `relevant_sheets`

### Типы запросов

| Тип | Enum | Описание | Пример |
|-----|------|----------|--------|
| `lookup` | `QueryType.LOOKUP` | Поиск конкретного значения | "Какая цена меди в январе?" |
| `aggregate` | `QueryType.AGGREGATE` | Агрегация (сумма, среднее, мин/макс) | "Средняя цена никеля за квартал" |
| `cross_sheet` | `QueryType.CROSS_SHEET` | Сравнение между листами | "Сравнить цены января и февраля" |
| `delta` | `QueryType.DELTA` | Разница во времени | "На сколько изменилась цена?" |
| `unknown` | `QueryType.UNKNOWN` | Неопределённый тип | — |

### Процесс

1. **Получение списка листов** из БД: `id`, `normalized_name`, `description`
2. **Формирование промпта** с RAG-контекстом и списком листов
3. **Вызов LLM** с JSON-схемой ответа:

```json
{
  "query_type": "lookup",
  "entities": ["медь", "январь 2025"],
  "relevant_sheet_ids": [1, 3]
}
```

4. **Парсинг JSON** с очисткой от markdown-обёртки
5. **Валидация**: если `query_type` не из списка — `unknown`
6. **Маппинг ID листов** в полные объекты

**System prompt:**
```
Ты — классификатор запросов к базе данных Excel-файла Evraz с ценами на металлы.
...
Правила определения query_type:
- lookup: вопрос про конкретное значение
- aggregate: вопрос про сумму, среднее, минимум, максимум
- cross_sheet: сравнение между разными листами/месяцами
- delta: разница между значениями во времени
- unknown: если не подходит ни под один из вышеперечисленных
```

---

## 4. Planner Node — планирование

**Файл:** [`src/services/agent/nodes/planner_node.py`](src/services/agent/nodes/planner_node.py) — функция [`planner_node()`](src/services/agent/nodes/planner_node.py:95)

**Назначение:** Составить текстовый план действий для генерации SQL-запроса.

**Вход:** `question`, `query_type`, `entities`, `relevant_sheets`, `rag_context`
**Выход:** `plan` (текстовый план), `schema` (схема релевантных листов)

### Процесс

1. **Получение схемы** релевантных листов из БД:

```python
schema = [
    {
        "id": 1,
        "name": "цвломна_дек25",
        "original_name": "ЦВ лом на Дек25",
        "description": "Цены на цветной лом, декабрь 2025",
        "columns": [
            {
                "name": "наименование_лома",
                "original_name": "Наименование лома",
                "data_type": "text",
                "sample_values": ["Медь", "Никель", "Алюминий"]
            },
            {
                "name": "среднерыночная_цена_рубтн",
                "original_name": "Среднерыночная цена, руб/тн",
                "data_type": "price",
                "sample_values": [8500, 12000]
            }
        ]
    }
]
```

2. **Формирование промпта** с RAG-контекстом, типом запроса, сущностями и схемой
3. **Вызов LLM** для генерации плана

**System prompt:**
```
Ты — планировщик запросов к базе данных Excel-файла с ценами на металлы.
...
План должен быть конкретным и содержать:
1. Какие листы (таблицы) нужно использовать
2. Какие колонки нужны для ответа
3. Какие условия фильтрации (WHERE)
4. Нужна ли агрегация (SUM/AVG/MIN/MAX) или группировка
5. Нужна ли сортировка
```

**Пример плана:**
```
1. Использовать лист "цвломна_дек25" (id=1)
2. Отфильтровать по колонке "наименование_лома" = "Медь"
3. Взять значение из колонки "среднерыночная_цена_рубтн" (col_index=10)
4. Вернуть одно число — цену меди
```

---

## 5. CodeGen Node — генерация SQL

**Файл:** [`src/services/agent/nodes/codegen_node.py`](src/services/agent/nodes/codegen_node.py) — функция [`codegen_node()`](src/services/agent/nodes/codegen_node.py:127)

**Назначение:** Сгенерировать SQL-запрос на основе плана и выполнить его валидацию.

**Вход:** `question`, `plan`, `query_type`, `entities`, `rag_context`, `schema`
**Выход:** `sql_query`, `validation_errors`

### Процесс

1. **Формирование промпта** с:
   - Полной схемой БД (таблицы `sheets`, `column_metadata`, `cells`)
   - Планом действий
   - RAG-контекстом
   - Явными `normalized_name` из RAG-контекста (чтобы LLM не транслитерировал)

2. **Вызов LLM** для генерации SQL

3. **Очистка SQL** от markdown-обёртки (` ```sql `, ` ``` `)

4. **Валидация SQL** — функция [`validate_sql()`](src/services/agent/nodes/codegen_node.py:94):

```python
def validate_sql(sql: str) -> List[str]:
    errors = []
    
    # 1. Должен начинаться с SELECT
    if not sql_upper.startswith("SELECT"):
        errors.append("Запрос должен начинаться с SELECT (read-only)")
    
    # 2. Проверка на запрещённые ключевые слова
    FORBIDDEN_KEYWORDS = [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
        "TRUNCATE", "GRANT", "REVOKE", "EXECUTE", "EXEC",
        "COPY", "VACUUM", "ANALYZE", "REINDEX",
    ]
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(r'\b' + re.escape(keyword) + r'\b', sql_upper):
            errors.append(f"Запрещённое ключевое слово: {keyword}")
    
    # 3. Должен содержать FROM
    if "FROM" not in sql_upper:
        errors.append("Запрос должен содержать FROM")
    
    # 4. Баланс скобок
    if sql.count("(") != sql.count(")"):
        errors.append("Несбалансированные круглые скобки")
    
    return errors
```

**System prompt (схема БД):**
```sql
Таблица sheets:
- id: INTEGER PRIMARY KEY
- file_id: INTEGER
- sheet_index: INTEGER
- original_name: TEXT
- normalized_name: TEXT  -- например, "цвломна_дек25"
- description: TEXT
- row_count: INTEGER
- col_count: INTEGER

Таблица column_metadata:
- id: INTEGER PRIMARY KEY
- sheet_id: INTEGER (FK → sheets.id)
- col_index: INTEGER
- original_name: TEXT
- normalized_name: TEXT  -- например, "среднерыночная_цена_рубтн"
- data_type: TEXT
- sample_values: JSONB

Таблица cells:
- id: BIGINT PRIMARY KEY
- sheet_id: INTEGER (FK → sheets.id)
- row_num: INTEGER
- col_index: INTEGER
- value_text: TEXT
- value_number: DOUBLE PRECISION
- value_date: TIMESTAMP
- original_value: TEXT
```

**Критические правила для CodeGen:**
- Использовать `sheets.normalized_name` без транслитерации
- Для числовых значений — `cells.value_number`
- Для текстовых — `cells.value_text`
- Для поиска цены по наименованию — подзапрос с `col_index`
- Только SELECT (read-only)

---

## 6. Executor Node — выполнение SQL

**Файл:** [`src/services/agent/nodes/executor_node.py`](src/services/agent/nodes/executor_node.py) — функция [`executor_node()`](src/services/agent/nodes/executor_node.py:25)

**Назначение:** Безопасно выполнить SQL-запрос и вернуть результат.

**Вход:** `sql_query`, `validation_errors`
**Выход:** `sql_result` (список строк), `sql_error` (опционально)

### Процесс

1. **Проверка наличия SQL**: если пустой → `sql_error`
2. **Проверка валидации**: если есть ошибки → `sql_error`
3. **Выполнение SQL**:
   - Открывается асинхронная сессия SQLAlchemy
   - Устанавливается `statement_timeout = '30s'`
   - Выполняется `text(sql_query)`
   - Результат конвертируется в список dict: `[{col: value, ...}, ...]`
   - Ограничение: максимум 100 строк (`MAX_RESULT_ROWS`)
4. **Обработка ошибок**: любое исключение → `sql_error`

**Безопасность:**
- Только SELECT (read-only) — проверено на этапе CodeGen
- Таймаут 30 секунд
- Ограничение на количество строк результата

---

## 7. Verifier Node — верификация

**Файл:** [`src/services/agent/nodes/verifier_node.py`](src/services/agent/nodes/verifier_node.py) — функция [`verifier_node()`](src/services/agent/nodes/verifier_node.py:56)

**Назначение:** Проверить, отвечает ли результат SQL-запроса на исходный вопрос. Принять решение о retry.

**Вход:** `question`, `sql_query`, `sql_result`, `sql_error`, `rag_context`, `retry_count`
**Выход:** `answer`, `confidence`, `needs_retry`, `retry_reason`, `retry_count`

### Процесс

1. **Если SQL-ошибка** → `needs_retry=True`, `retry_reason="sql_error: ..."`
2. **Если пустой результат** → `needs_retry=True`, `retry_reason="empty_result"`
3. **Если есть данные** → вызов LLM для верификации:

**System prompt:**
```
Ты — верификатор ответов на вопросы по Excel-файлу с ценами на металлы.
...
Верни JSON с полями:
1. "is_correct": true/false
2. "confidence": число от 0.0 до 1.0
3. "answer": человекочитаемый ответ на русском языке
4. "needs_retry": true/false
5. "retry_reason": причина retry (если needs_retry=true)
```

**Причины retry:**
| Причина | Описание |
|---------|----------|
| `wrong_sheet` | Не тот лист |
| `wrong_column` | Не та колонка |
| `wrong_aggregation` | Не та агрегация |
| `missing_filter` | Не хватает фильтра |
| `incomplete_result` | Неполный результат |
| `sql_error` | Ошибка выполнения SQL |
| `empty_result` | Пустой результат |

**Правила верификации:**
- Если результат пустой → скорее всего `needs_retry=true`
- Если в результате есть данные, отвечающие на вопрос → `is_correct=true`
- Не быть излишне строгим
- Если не уверен → лучше `is_correct=true` с низким confidence, чем ложный retry

**Максимум retry:** 3 (`MAX_RETRY_COUNT`)

---

## 8. Answer Node — финальный ответ

**Файл:** [`src/services/agent/nodes/answer_node.py`](src/services/agent/nodes/answer_node.py) — функция [`answer_node()`](src/services/agent/nodes/answer_node.py:15)

**Назначение:** Финальное форматирование ответа пользователю.

**Вход:** `answer`, `confidence`, `sql_result`
**Выход:** Финальный `answer` (гарантированно непустой)

**Логика:**
- Если ответ непустой → оставить как есть
- Если ответ пустой, но есть `sql_result` → "Получены данные, но не удалось сформировать ответ"
- Если ответ пустой и нет данных → "Не удалось найти ответ на ваш вопрос"

---

## 9. Маршрутизация (Conditional Edges)

**Файл:** [`src/services/agent/nodes/routing.py`](src/services/agent/nodes/routing.py)

Определяет, в какой узел переходить после каждого шага.

### После RAG → Classifier
Всегда идёт в Classifier, даже если RAG упал с ошибкой.

### После Classifier → Planner
Всегда идёт в Planner.

### После Planner → CodeGen
Всегда идёт в CodeGen.

### После CodeGen → Executor / CodeGen (retry) / Failed

```python
if not sql_query:
    if retry_count < MAX_RETRY_COUNT:  # → CodeGen (retry)
    else:                               # → Failed

if validation_errors:
    if retry_count < MAX_RETRY_COUNT:  # → CodeGen (retry)
    else:                               # → Executor (пробуем выполнить)
else:                                   # → Executor
```

### После Executor → Verifier / CodeGen (retry) / Failed

```python
if sql_error:
    if retry_count < MAX_RETRY_COUNT:  # → CodeGen (retry)
    else:                               # → Failed
else:                                   # → Verifier
```

### После Verifier → Answer / CodeGen (retry) / Failed

```python
if needs_retry and retry_count < MAX_RETRY_COUNT:   # → CodeGen (retry)
if needs_retry and retry_count >= MAX_RETRY_COUNT:  # → Answer (отдаём что есть)
else:                                                # → Answer
```

---

## 10. Self-Correction

**Файл:** [`src/services/generation/pipeline.py`](src/services/generation/pipeline.py) — метод [`run_agent()`](src/services/generation/pipeline.py:153)

Self-Correction работает **вне графа LangGraph**, на уровне `GenerationPipeline`.

### Условия для self-correction

```python
needs_correction = (
    result.status in ("failed", "low_confidence")
    or result.confidence < 0.5
    or not result.answer
    or len(result.answer) < 20
)
```

### Процесс

1. **Первый проход** агента
2. **Проверка качества**: если confidence < 0.5 или статус failed/low_confidence
3. **Формирование истории ошибок**:
   ```python
   correction_history = [
       {"role": "user", "content": question},
       {"role": "assistant", "content": result.answer},
       {"role": "assistant", "content": "Ошибки: rag: ...; executor: ..."},
   ]
   ```
4. **Второй проход** агента с `conversation_history=correction_history`
5. **Флаг**: `result.self_corrected = True`

### Защита от бесконечных retry
- Self-correction выполняется только один раз (проверка `is_retry`)
- Внутри графа — максимум 3 retry через Verifier

---

## 11. Полный цикл запроса

### Пример: "Какая цена меди в январе 2025?"

```
Шаг 1: RAG Node
  → Гибридный поиск по вопросу
  → Найдено 15 релевантных чанков
  → Контекст: лист "цвломна_дек25", колонка "среднерыночная_цена_рубтн"

Шаг 2: Classifier Node
  → Тип: lookup
  → Сущности: ["медь", "январь 2025"]
  → Релевантные листы: [{"id": 1, "name": "цвломна_дек25"}]

Шаг 3: Planner Node
  → Получена схема листа "цвломна_дек25"
  → План: "Найти цену меди в колонке среднерыночная_цена_рубтн"

Шаг 4: CodeGen Node
  → Сгенерирован SQL:
    SELECT c.value_number
    FROM cells c
    JOIN sheets s ON c.sheet_id = s.id
    WHERE s.normalized_name = 'цвломна_дек25'
      AND c.col_index = 10
      AND c.row_num IN (
        SELECT c2.row_num FROM cells c2
        WHERE c2.sheet_id = s.id
          AND c2.col_index = 2
          AND c2.value_text ILIKE '%медь%'
      )
  → Валидация пройдена

Шаг 5: Executor Node
  → SQL выполнен успешно
  → Результат: [{"value_number": 8500.0}]

Шаг 6: Verifier Node
  → LLM проверил: ответ правильный
  → confidence: 0.95
  → needs_retry: false

Шаг 7: Answer Node
  → Финальный ответ: "Цена меди в январе 2025 составляет 8 500 руб/тн."

Шаг 8: Self-Correction (не требуется)
  → confidence 0.95 >= 0.5 → пропуск
```

### Результат агента

```python
@dataclass
class AgentResult:
    answer: str                    # "Цена меди в январе 2025 составляет 8 500 руб/тн."
    confidence: float              # 0.95
    request_id: str                # UUID
    question: str                  # "Какая цена меди в январе 2025?"
    latency_ms: int                # 3420
    trace: Dict                    # Полный трейс всех шагов
    query_type: str                # "lookup"
    sql_query: str                 # SELECT c.value_number ...
    sql_result: List[Dict]         # [{"value_number": 8500.0}]
    retry_count: int               # 0
    status: str                    # "success"
    self_corrected: bool           # False
```

---

## Ключевые файлы

| Файл | Назначение |
|------|-----------|
| [`src/services/agent/graph.py`](src/services/agent/graph.py) | Сборка LangGraph графа + LangGraphAgent |
| [`src/services/agent/graph_state.py`](src/services/agent/graph_state.py) | TypedDict состояния графа + QueryType enum |
| [`src/services/agent/nodes/rag_node.py`](src/services/agent/nodes/rag_node.py) | RAG-узел (гибридный поиск) |
| [`src/services/agent/nodes/classifier_node.py`](src/services/agent/nodes/classifier_node.py) | Классификация запроса |
| [`src/services/agent/nodes/planner_node.py`](src/services/agent/nodes/planner_node.py) | Планирование |
| [`src/services/agent/nodes/codegen_node.py`](src/services/agent/nodes/codegen_node.py) | Генерация SQL + валидация |
| [`src/services/agent/nodes/executor_node.py`](src/services/agent/nodes/executor_node.py) | Выполнение SQL |
| [`src/services/agent/nodes/verifier_node.py`](src/services/agent/nodes/verifier_node.py) | Верификация + retry |
| [`src/services/agent/nodes/answer_node.py`](src/services/agent/nodes/answer_node.py) | Финальный ответ |
| [`src/services/agent/nodes/routing.py`](src/services/agent/nodes/routing.py) | Conditional edges |
| [`src/services/generation/pipeline.py`](src/services/generation/pipeline.py) | GenerationPipeline (запуск агента + self-correction) |
| [`src/api/agent_router.py`](src/api/agent_router.py) | REST API для /ask (режимы auto/rag/agent) |
| [`src/api/schemas.py`](src/api/schemas.py) | Pydantic-схемы запросов/ответов |
| [`src/api/trace_router.py`](src/api/trace_router.py) | Traceability API |