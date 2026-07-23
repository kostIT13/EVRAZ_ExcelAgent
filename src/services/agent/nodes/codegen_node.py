"""CodeGen Node — узел генерации SQL в графе LangGraph.

Генерирует SQL-запрос на основе плана, схемы и RAG-контекста.
Выполняет валидацию SQL без выполнения.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional

from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_CODEGEN
from src.services.llm.llm_client import LLMClient

CODEGEN_SYSTEM_PROMPT = """Ты — генератор SQL-запросов для базы данных Excel-файла с ценами на металлы.

Схема базы данных:

Таблица sheets:
- id: INTEGER PRIMARY KEY — ID листа
- file_id: INTEGER — ID файла
- sheet_index: INTEGER — порядковый номер листа
- original_name: TEXT — оригинальное название листа
- normalized_name: TEXT — нормализованное название (например, "цвломна_дек25")
- description: TEXT — описание содержимого листа
- row_count: INTEGER — количество строк
- col_count: INTEGER — количество колонок

Таблица column_metadata:
- id: INTEGER PRIMARY KEY — ID колонки
- sheet_id: INTEGER — ID листа (FK → sheets.id)
- col_index: INTEGER — порядковый номер колонки
- original_name: TEXT — оригинальное название колонки
- normalized_name: TEXT — нормализованное название (например, "среднерыночная_цена_рубтн")
- data_type: TEXT — тип данных
- description: TEXT — описание колонки
- sample_values: JSONB — примеры значений

Таблица cells:
- id: BIGINT PRIMARY KEY — ID ячейки
- sheet_id: INTEGER — ID листа (FK → sheets.id)
- row_num: INTEGER — номер строки
- col_index: INTEGER — номер колонки
- value_text: TEXT — текстовое значение
- value_number: DOUBLE PRECISION — числовое значение
- value_date: TIMESTAMP — дата
- original_value: TEXT — оригинальное значение из Excel

ПРАВИЛА:
1. Только SELECT запросы (read-only)
2. Всегда используй JOIN с sheets для фильтрации по листу
3. Для фильтрации по названию листа используй sheets.normalized_name
4. ВАЖНО: Для числовых значений (цены, суммы) ВСЕГДА используй cells.value_number
5. Для текстовых значений (названия, описания) используй cells.value_text
6. Для дат используй cells.value_date
7. Не используй SELECT *
8. Используй понятные алиасы для колонок
9. Если нужна агрегация (SUM, AVG, MIN, MAX) — используй GROUP BY
10. Если нужна сортировка — используй ORDER BY

КРИТИЧЕСКИ ВАЖНО: ИСПОЛЬЗУЙ sheets.normalized_name ИЗ RAG-КОНТЕКСТА БЕЗ ИЗМЕНЕНИЙ!
НЕ ТРАНСЛИТЕРИРУЙ normalized_name!
Например, если в RAG-контексте написано "Лист: цвломна_дек25", то в SQL пиши:
  sheets.normalized_name = 'цвломна_дек25'
НЕ пиши 'tsvlonma_dek25' — это неправильно!

То же самое для column_metadata.normalized_name:
Если в RAG-контексте написано "среднерыночная_цена_рубтн", то в SQL пиши:
  cm.normalized_name = 'среднерыночная_цена_рубтн'

ВАЖНОЕ ПРАВИЛО ДЛЯ ПОИСКА ЦЕНЫ ПО НАИМЕНОВАНИЮ:
- Цена хранится в cells.value_number, колонка с col_index = 10 (среднерыночная_цена_рубтн)
- Наименование материала хранится в cells.value_text, колонка с col_index = 2 (наименование_лома)
- Для поиска цены конкретного материала используй ПОДЗАПРОС:
  SELECT c.value_number FROM cells c JOIN sheets s ...
  WHERE s.normalized_name = '...'
    AND c.col_index = 10
    AND c.row_num IN (SELECT c2.row_num FROM cells c2 WHERE c2.sheet_id = s.id AND c2.col_index = 2 AND c2.value_text ILIKE '%материал%')
- Для агрегации по нескольким листам используй UNION ALL или IN с несколькими sheet_id

Верни ТОЛЬКО SQL-запрос без пояснений. Без markdown-обёртки ```sql.
"""

# Запрещённые ключевые слова (защита от модификации данных)
FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "GRANT", "REVOKE", "EXECUTE", "EXEC",
    "COPY", "VACUUM", "ANALYZE", "REINDEX",
]


def validate_sql(sql: str) -> List[str]:
    """Валидация SQL-запроса без выполнения.

    Args:
        sql: SQL-запрос для проверки.

    Returns:
        Список ошибок. Пустой список = запрос валиден.
    """
    errors: List[str] = []
    sql_upper = sql.strip().upper()

    # 1. Должен начинаться с SELECT
    if not sql_upper.startswith("SELECT"):
        errors.append("Запрос должен начинаться с SELECT (read-only)")

    # 2. Проверка на запрещённые ключевые слова
    for keyword in FORBIDDEN_KEYWORDS:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, sql_upper):
            errors.append(f"Запрос содержит запрещённое ключевое слово: {keyword}")

    # 3. Должен содержать FROM
    if "FROM" not in sql_upper:
        errors.append("Запрос должен содержать FROM")

    # 4. Базовая проверка баланса скобок
    if sql.count("(") != sql.count(")"):
        errors.append("Несбалансированные круглые скобки")

    return errors


async def codegen_node(
    state: GraphState,
    llm: Optional[LLMClient] = None,
    **kwargs: Any,
) -> GraphState:
    """Узел CodeGen: генерирует SQL-запрос на основе плана и RAG-контекста.

    Args:
        state: Состояние с заполненными question, plan, query_type,
               entities, rag_context, schema.
        llm: LLMClient.
        **kwargs: Дополнительные аргументы (config от LangGraph).

    Returns:
        Обновлённое состояние с sql_query и validation_errors.
    """
    llm = llm or LLMClient()
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")
    query_type = state.get("query_type")
    entities = state.get("entities", [])
    plan = state.get("plan", "")
    rag_context = state.get("rag_context", "")
    schema = state.get("schema", [])

    logger.info(
        "CodeGen Node [{}]: generating SQL for type={}",
        request_id,
        query_type.value if query_type else "?",
    )

    # 1. Формируем промпт с планом, схемой и RAG-контекстом
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
    rag_section = (
        f"\nRAG-контекст (релевантные данные):\n{rag_context[:20000]}"
        if rag_context
        else ""
    )

    # Извлекаем normalized_name из RAG-контекста для явной подсказки LLM
    rag_names_hint = ""
    if rag_context:
        sheet_names = set(re.findall(r'(?:Лист|лист)[:\s]+(\S+)', rag_context))
        col_names = set(re.findall(r'(?:колонк[иа]|колонки):\s*([^\n]+)', rag_context))
        if sheet_names:
            rag_names_hint += "\nЯвные normalized_name листов из RAG-контекста (используй их БЕЗ транслитерации):\n"
            for nm in sorted(sheet_names):
                rag_names_hint += f"  - '{nm}'\n"
        if col_names:
            for col_line in col_names:
                parts = [p.strip() for p in col_line.split(",")]
                rag_names_hint += "\nЯвные normalized_name колонок из RAG-контекста (используй их БЕЗ транслитерации):\n"
                for p in parts:
                    if p and not p.startswith("строк") and not p.startswith("колон"):
                        rag_names_hint += f"  - '{p}'\n"

    user_message = f"""Вопрос пользователя: {question}{rag_section}

Тип запроса: {query_type.value if query_type else 'unknown'}
Сущности: {', '.join(entities) if entities else 'не определены'}

План действий:
{plan}

Схема релевантных листов:
{schema_json}
{rag_names_hint}
Сгенерируй SQL-запрос для получения ответа на вопрос.

ВАЖНО: Используй sheets.normalized_name и column_metadata.normalized_name в точности как они указаны в RAG-контексте выше. НЕ ТРАНСЛИТЕРИРУЙ их!"""

    messages = [
        {"role": "system", "content": CODEGEN_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # 2. Вызываем LLM
    try:
        raw_sql = await llm.chat(
            messages=messages,
            model=None,
            temperature=0.1,
            max_tokens=2048,
        )

        # Очищаем SQL от markdown-обёртки
        sql = raw_sql.strip()
        if sql.startswith("```sql"):
            sql = sql[6:]
        elif sql.startswith("```"):
            sql = sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        sql = sql.strip()
        sql = sql.rstrip(";")

        state["sql_query"] = sql
        logger.info(
            "CodeGen Node [{}]: SQL generated ({} chars)",
            request_id,
            len(sql),
        )

    except Exception as exc:
        logger.error("CodeGen Node [{}]: LLM failed: {}", request_id, exc)
        state["sql_query"] = ""
        state["validation_errors"] = [f"Ошибка LLM: {exc}"]
        state["trace"] = state.get("trace", {})
        state["trace"][NODE_CODEGEN] = {"error": str(exc)}
        return state

    # 3. Валидируем SQL
    if state["sql_query"]:
        state["validation_errors"] = validate_sql(state["sql_query"])
        logger.info(
            "CodeGen Node [{}]: validation errors: {}",
            request_id,
            len(state["validation_errors"]),
        )
    else:
        state["validation_errors"] = ["SQL-запрос пуст."]

    # 4. Trace
    state["trace"] = state.get("trace", {})
    state["trace"][NODE_CODEGEN] = {
        "sql_query": state["sql_query"],
        "validation_errors": state["validation_errors"],
    }

    return state