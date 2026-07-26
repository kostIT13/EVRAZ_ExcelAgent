"""CodeGen Node — узел генерации SQL в графе LangGraph.

Генерирует SQL-запрос на основе плана, схемы и RAG-контекста.
Выполняет валидацию SQL без выполнения.

Поддерживает две схемы:
1. Новая нормализованная: fact_prices (период | наименование | источник_цены | значение)
2. Старая generic: sheets → columns → cells (для обратной совместимости)
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional

from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_CODEGEN
from src.services.llm.llm_client import LLMClient

# ---------------------------------------------------------------------------
# Few-shot examples для text-to-SQL
# ---------------------------------------------------------------------------

FEW_SHOT_EXAMPLES = [
    {
        "question": "Какая среднерыночная цена на лом меди в январе 2025?",
        "sql": """SELECT fp.price_value
FROM fact_prices fp
WHERE fp.period = '2025-01'
  AND fp.price_source = 'среднерыночная'
  AND fp.item_name_normalized ILIKE '%медь%'
LIMIT 1""",
    },
    {
        "question": "Сравни цены на латунь у всех поставщиков в декабре 2025",
        "sql": """SELECT fp.price_source, fp.price_value
FROM fact_prices fp
WHERE fp.period = '2025-12'
  AND fp.price_source NOT IN ('среднерыночная', 'аукцион_старт', 'аукцион_победитель')
  AND fp.item_name_normalized ILIKE '%латун%'
ORDER BY fp.price_source""",
    },
    {
        "question": "Какая средняя цена на никель по всем месяцам?",
        "sql": """SELECT fp.period, AVG(fp.price_value) as avg_price
FROM fact_prices fp
WHERE fp.price_source = 'среднерыночная'
  AND fp.item_name_normalized ILIKE '%никел%'
GROUP BY fp.period
ORDER BY fp.period""",
    },
    {
        "question": "На сколько изменилась цена на медь между январем и февралем 2025?",
        "sql": """SELECT
  jan.price_value as цена_январь,
  feb.price_value as цена_февраль,
  (feb.price_value - jan.price_value) as изменение
FROM
  (SELECT price_value FROM fact_prices
   WHERE period = '2025-01' AND price_source = 'среднерыночная'
     AND item_name_normalized ILIKE '%медь%' LIMIT 1) jan,
  (SELECT price_value FROM fact_prices
   WHERE period = '2025-02' AND price_source = 'среднерыночная'
     AND item_name_normalized ILIKE '%медь%' LIMIT 1) feb""",
    },
    {
        "question": "Какая стартовая цена аукциона на лом меди в марте 2025?",
        "sql": """SELECT fp.price_value
FROM fact_prices fp
WHERE fp.period = '2025-03'
  AND fp.price_source = 'аукцион_старт'
  AND fp.item_name_normalized ILIKE '%медь%'
LIMIT 1""",
    },
    {
        "question": "Кто победил в аукционе по латуни в январе 2025 и по какой цене?",
        "sql": """SELECT fp.price_source, fp.price_value
FROM fact_prices fp
WHERE fp.period = '2025-01'
  AND fp.price_source = 'аукцион_победитель'
  AND fp.item_name_normalized ILIKE '%латун%'
LIMIT 1""",
    },
    {
        "question": "Покажи все цены на бронзу в апреле 2025",
        "sql": """SELECT fp.price_source, fp.price_value
FROM fact_prices fp
WHERE fp.period = '2025-04'
  AND fp.item_name_normalized ILIKE '%бронз%'
ORDER BY fp.price_source""",
    },
    {
        "question": "Какая цена на лом меди кусок у поставщика ООО Металл в январе 2025?",
        "sql": """SELECT fp.price_value
FROM fact_prices fp
WHERE fp.period = '2025-01'
  AND fp.price_source ILIKE '%металл%'
  AND fp.item_name_normalized ILIKE '%медь%'
LIMIT 1""",
    },
    {
        "question": "О скольки месяцах у тебя есть информация?",
        "sql": """SELECT COUNT(*) AS количество_месяцев
FROM sheets
WHERE period IS NOT NULL""",
    },
    {
        "question": "Сколько всего листов в базе данных?",
        "sql": """SELECT COUNT(*) AS количество_листов
FROM sheets""",
    },
]

CODEGEN_SYSTEM_PROMPT = """Ты — генератор SQL-запросов для базы данных с ценами на металлы.

Схема базы данных (основная — нормализованная):

Таблица fact_prices (НОРМАЛИЗОВАННАЯ ФАКТ-ТАБЛИЦА):
- id: INTEGER PRIMARY KEY
- sheet_id: INTEGER — ID листа (FK → sheets.id)
- item_id: INTEGER — ID сущности (FK → entity_dictionary.id)
- period: TEXT — период (например, '2025-01', '2025-12')
- item_name_raw: TEXT — оригинальное название лома
- item_name_normalized: TEXT — нормализованное название (для ILIKE-поиска)
- price_source: TEXT — источник цены:
    * 'среднерыночная' — среднерыночная цена
    * 'аукцион_старт' — стартовая цена аукциона
    * 'аукцион_победитель' — цена победителя аукциона
    * Другие значения — названия поставщиков (например, 'ООО Металл', 'ИП Иванов')
- price_value: DOUBLE PRECISION — значение цены в руб/тн
- row_num: INTEGER — номер строки в исходном листе

Таблица entity_dictionary (СПРАВОЧНИК СУЩНОСТЕЙ):
- id: INTEGER PRIMARY KEY
- canonical_name: TEXT — каноническое название (уникальное)
- aliases: JSONB — список алиасов (синонимов)
- category: TEXT — категория (например, 'цветной_лом', 'черный_лом')

Таблица sheets:
- id: INTEGER PRIMARY KEY
- normalized_name: TEXT — нормализованное название листа
- period: TEXT — период листа
- description: TEXT — описание

Таблица excel_comments:
- id: INTEGER PRIMARY KEY
- sheet_id: INTEGER — ID листа
- cell_ref: TEXT — ссылка на ячейку (например, 'B12')
- author: TEXT — автор комментария
- text: TEXT — текст комментария

ПРАВИЛА:
1. Только SELECT запросы (read-only)
2. Для вопросов о ценах используй fact_prices — она содержит все цены в плоском формате
3. Для вопросов о количестве листов/месяцев используй sheets
4. Для фильтрации по названию лома используй ILIKE с item_name_normalized
5. Для фильтрации по периоду используй period (формат: 'YYYY-MM')
6. Для фильтрации по источнику цены используй price_source
7. Если нужна агрегация (AVG, SUM, MIN, MAX) — используй GROUP BY
8. Если нужно сравнение между периодами — используй подзапросы или JOIN fact_prices
9. Для поиска по названию поставщика используй price_source ILIKE '%текст%'
10. Не используй SELECT *
11. Используй понятные алиасы для колонок

ПРИМЕРЫ ЗАПРОСОВ (few-shot):
{few_shot_examples}

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

    # Форматируем few-shot примеры
    few_shot_text = "\n\n".join(
        f"Вопрос: {ex['question']}\nSQL: {ex['sql']}"
        for ex in FEW_SHOT_EXAMPLES
    )

    user_message = f"""Вопрос пользователя: {question}{rag_section}

Тип запроса: {query_type.value if query_type else 'unknown'}
Сущности: {', '.join(entities) if entities else 'не определены'}

План действий:
{plan}

Схема релевантных листов:
{schema_json}

Сгенерируй SQL-запрос для получения ответа на вопрос.

ВАЖНО: Выбери правильную таблицу в зависимости от вопроса:
- Для вопросов о ценах, поставщиках, аукционах → используй fact_prices
- Для вопросов о количестве листов/месяцев/периодов → используй sheets (SELECT COUNT(*) FROM sheets)
- Для вопросов о сущностях/справочниках → используй entity_dictionary

Для поиска по названию лома используй ILIKE с item_name_normalized.

ВАЖНО: В схеме релевантных листов есть поле "fact_prices_samples" — это реальные данные из fact_prices для этих листов. Используй их чтобы:
1. Убедиться, что данные существуют (если fact_prices_samples пуст — данных нет)
2. Посмотреть точный формат item_name_normalized для правильного ILIKE-поиска
3. Посмотреть точный формат period для правильной фильтрации
4. Посмотреть какие price_source доступны

Пример: если fact_prices_samples содержит item_name_normalized = "лом меди стружка", то ILIKE '%медь%' или ILIKE '%стружка%' сработает."""

    messages = [
        {"role": "system", "content": CODEGEN_SYSTEM_PROMPT.format(
            few_shot_examples=few_shot_text
        )},
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