# """Что делает CodeGen:

# Берёт вопрос + план + схему листов из AgentState
# Отправляет в LLM — LLM генерирует SQL-запрос
# Validator проверяет SQL без выполнения (через sqlparse)
# Если SQL невалиден — возвращает ошибки, и CodeGen может перегенерировать
# """

# """CodeGen — LLM-генератор SQL-запросов + Validator.

# Генерирует SQL на основе плана и схемы, затем валидирует его.
# """

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from src.core.logging_settings import logger
from src.services.agent.state import AgentState, AgentStep
from src.services.llm.llm_client import LLMClient

CODEGEN_SYSTEM_PROMPT = """Ты — генератор SQL-запросов для базы данных Excel-файла с ценами на металлы.

Схема базы данных:

Таблица sheets:
- id: INTEGER PRIMARY KEY — ID листа
- file_id: INTEGER — ID файла
- sheet_index: INTEGER — порядковый номер листа
- original_name: TEXT — оригинальное название листа (например, "Январь 2025")
- normalized_name: TEXT — нормализованное название (например, "yanvar_2025")
- description: TEXT — описание содержимого листа
- row_count: INTEGER — количество строк
- col_count: INTEGER — количество колонок

Таблица column_metadata:
- id: INTEGER PRIMARY KEY — ID колонки
- sheet_id: INTEGER — ID листа (FK → sheets.id)
- col_index: INTEGER — порядковый номер колонки
- original_name: TEXT — оригинальное название колонки
- normalized_name: TEXT — нормализованное название
- data_type: TEXT — тип данных (price/date/number/text/id)
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
3. Для фильтрации по названию листа используй sheets.normalized_name или sheets.original_name
4. Для числовых значений используй cells.value_number
5. Для текстовых значений используй cells.value_text
6. Для дат используй cells.value_date
7. Не используй SELECT *
8. Используй понятные алиасы (псевдонимы) для колонок
9. Если нужна агрегация — используй GROUP BY
10. Если нужна сортировка — используй ORDER BY
11. Оборачивай названия таблиц и колонок в двойные кавычки если они содержат спецсимволы

Верни ТОЛЬКО SQL-запрос без пояснений.
"""

# Список запрещённых ключевых слов (защита от модификации данных)
FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "GRANT", "REVOKE", "EXECUTE", "EXEC",
    "COPY", "VACUUM", "ANALYZE", "REINDEX",
]

def validate_sql(sql: str) -> List[str]:
    """Валидация SQL-запроса без выполнения.

    Проверяет:
    1. Что запрос начинается с SELECT
    2. Что нет запрещённых ключевых слов
    3. Базовый синтаксис (наличие SELECT и FROM)

    Args:
        sql: SQL-запрос для проверки.

    Returns:
        Список ошибок. Пустой список = запрос валиден.
    """
    errors: List[str] = []
    sql_upper = sql.strip().upper()
    
    # 1. Должен начинаться с SELECT
    if not sql_upper.startswith("SELECT"):
        errors.append("Запрос должен начиналься с SELECT (read-only)")
    
    # 2. Проверка на запрещенные ключенивые слова
    for keyword in FORBIDDEN_KEYWORDS:
        # Ищем слово как отдельный токен (окружённый пробелами или началом/концом строки)
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


async def codegen_step(state: AgentState, llm: Optional[LLMClient] = None) -> AgentState:
    """Шаг CodeGen: генерирует SQL-запрос на основе плана
    Args:
        state: Текущее состояние агента (должен быть заполнен planner'ом).
        llm: LLMClient (создаётся по умолчанию, если не передан).

    Returns:
        AgentState с заполненными sql_query и validation_errors.
    """
    llm = llm or LLMClient()
    logger.info(
        "CodeGen [{}]: generating SQL for type={}",
        state.request_id[:8],
        state.query_type.value,
    )
    
    # 1. Формируем промпт с планом и схемой
    schema_json = json.dumps(
        state.trace.get("planner", {}).get("schema_used", []),
        ensure_ascii=False,
        indent=2
    )
    
    user_message = f"""Вопрос пользователя: {state.question}

Тип запроса: {state.query_type.value}
Сущности: {', '.join(state.entities) if state.entities else 'не определены'}

План действий:
{state.plan}

Схема релевантных листов:
{schema_json}

Сгенерируй SQL-запрос для получения ответа на вопрос."""

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

        # Убираем точку с запятой в конце (если есть)
        sql = sql.rstrip(";")

        state.sql_query = sql

        logger.info(
            "CodeGen [{}]: SQL generated ({} chars)",
            state.request_id[:8],
            len(sql),
        )
        
    except Exception as exc:
        logger.error(
            "CodeGen [{}]: LLM call failed: {}",
            state.request_id[:8],
            exc,
        )
        state.sql_query = ""
        state.validation_errors = [f"Ошибка LLM: {exc}"]
        state.trace["codegen"] = {"error": str(exc)}
        state.current_step = "codegen"
        return state
    
    # 3. Валидируем SQL
    if state.sql_query:
        state.validation_errors = validate_sql(state.sql_query)
        logger.info(
            "CodeGen [{}]: validation errors: {}",
            state.request_id[:8],
            len(state.validation_errors),
        )
    else:
        state.validation_errors = ["SQL-запрос пуст."]
        
    # 4. Сохраняем trace (след)
    state.trace["codegen"] = {
        "sql_query": state.sql_query,
        "validation_errors": state.validation_errors
    }
    
    # 5. Если валидация не пройдена — остаёмся на codegen для retry
    #    (оркестратор будет решать, делать retry или нет)
    if state.validation_errors:
        state.current_step = AgentStep.CODEGEN  # остаёмся для retry
    else:
        state.current_step = AgentStep.EXECUTOR  # идём дальше

    return state