from __future__ import annotations

import json
import re
from typing import Any, List, Optional

from src.core.config import settings
from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_CODEGEN
from src.services.llm.llm_client import LLMClient


FEW_SHOT_EXAMPLES = [
    {
        "question": "Какая среднерыночная цена на лом меди в январе 2025?",
        "sql": """SELECT fp.value
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-01'
  AND fp.price_type = 'среднерыночная'
  AND fp.item_name ILIKE '%медь%'
LIMIT 1""",
    },
    {
        "question": "Сравни цены на латунь у всех поставщиков в декабре 2025",
        "sql": """SELECT fp.supplier, fp.value
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-12'
  AND fp.price_type = 'поставщик'
  AND fp.item_name ILIKE '%латун%'
ORDER BY fp.supplier""",
    },
    {
        "question": "Какая средняя цена на никель по всем месяцам?",
        "sql": """SELECT fp.sheet_period, AVG(fp.value) as avg_price
FROM mart.price_facts fp
WHERE fp.price_type = 'среднерыночная'
  AND fp.item_name ILIKE '%никел%'
GROUP BY fp.sheet_period
ORDER BY fp.sheet_period""",
    },
    {
        "question": "На сколько изменилась цена на медь между январем и февралем 2025?",
        "sql": """SELECT
  jan.value as цена_январь,
  feb.value as цена_февраль,
  (feb.value - jan.value) as изменение
FROM
  (SELECT value FROM mart.price_facts
   WHERE sheet_period = '2025-01' AND price_type = 'среднерыночная'
     AND item_name ILIKE '%медь%' LIMIT 1) jan,
  (SELECT value FROM mart.price_facts
   WHERE sheet_period = '2025-02' AND price_type = 'среднерыночная'
     AND item_name ILIKE '%медь%' LIMIT 1) feb""",
    },
    {
        "question": "Какая стартовая цена аукциона на лом меди в марте 2025?",
        "sql": """SELECT fp.value
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-03'
  AND fp.price_type = 'аукцион_старт'
  AND fp.item_name ILIKE '%медь%'
LIMIT 1""",
    },
    {
        "question": "Кто победил в аукционе по латуни в январе 2025 и по какой цене?",
        "sql": """SELECT fp.supplier, fp.value
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-01'
  AND fp.price_type = 'аукцион_победитель'
  AND fp.item_name ILIKE '%латун%'
LIMIT 1""",
    },
    {
        "question": "Покажи все цены на бронзу в апреле 2025",
        "sql": """SELECT fp.price_type, fp.supplier, fp.value
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-04'
  AND fp.item_name ILIKE '%бронз%'
ORDER BY fp.price_type, fp.supplier""",
    },
    {
        "question": "Какая цена на лом меди кусок у поставщика ООО Металл в январе 2025?",
        "sql": """SELECT fp.value
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-01'
  AND fp.supplier ILIKE '%металл%'
  AND fp.item_name ILIKE '%медь%'
LIMIT 1""",
    },
    {
        "question": "О скольки месяцах у тебя есть информация?",
        "sql": """SELECT COUNT(DISTINCT period) AS количество_месяцев
FROM sheets
WHERE period IS NOT NULL""",
    },
    {
        "question": "Сколько всего листов в базе данных?",
        "sql": """SELECT COUNT(*) AS количество_листов
FROM sheets""",
    },
]

CODEGEN_SYSTEM_PROMPT = """Ты — генератор SQL-запросов для нормализованной факт-таблицы цен на металлы.

Схема базы данных (единственная таблица для вопросов о ценах):

Таблица mart.price_facts (НОРМАЛИЗОВАННАЯ LONG-ФАКТ-ТАБЛИЦА):
- id: INTEGER PRIMARY KEY
- file_id: INTEGER — ID файла
- sheet_id: INTEGER — ID листа (необязательно)
- source_row_ref: TEXT — ссылка на исходную строку raw-таблицы
- sheet_period: TEXT — период (например, '2025-01', '2025-12')
- item_name: TEXT — нормализованное название лома (для ILIKE-поиска)
- supplier: TEXT — название поставщика (или NULL)
- price_type: TEXT — тип цены:
    * 'среднерыночная' — среднерыночная цена
    * 'аукцион_старт' — стартовая цена аукциона
    * 'аукцион_победитель' — цена победителя аукциона
    * 'поставщик' — цена от конкретного поставщика (см. колонку supplier)
- value: DOUBLE PRECISION — значение цены в руб/тн
- currency: TEXT — валюта (обычно 'RUB')
- unit: TEXT — единица измерения (обычно 'тн')

ПРАВИЛА:
1. Только SELECT запросы (read-only)
2. Для вопросов о ценах используй mart.price_facts — единственная таблица
3. Для фильтрации по названию лома используй ILIKE с item_name
4. Для фильтрации по периоду используй sheet_period (формат: 'YYYY-MM')
5. Для фильтрации по типу цены используй price_type
6. Для фильтрации по поставщику используй supplier ILIKE '%текст%'
7. Если нужна агрегация (AVG, SUM, MIN, MAX) — используй GROUP BY
8. Если нужно сравнение между периодами — используй подзапросы или JOIN mart.price_facts
9. Не выдумывай значения item_name/supplier — используй сущности-кандидаты из вопроса
10. Не используй SELECT *
11. Используй понятные алиасы для колонок
12. Схема всегда квалифицируется как mart.price_facts

ПРИМЕРЫ ЗАПРОСОВ (few-shot):
{few_shot_examples}

Верни ТОЛЬКО SQL-запрос без пояснений. Без markdown-обёртки ```sql.
"""

FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "GRANT", "REVOKE", "EXECUTE", "EXEC",
    "COPY", "VACUUM", "ANALYZE", "REINDEX",
]


def validate_sql(sql: str) -> List[str]:
    errors: List[str] = []
    sql_upper = sql.strip().upper()

    if not sql_upper.startswith("SELECT"):
        errors.append("Запрос должен начинаться с SELECT (read-only)")

    for keyword in FORBIDDEN_KEYWORDS:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, sql_upper):
            errors.append(f"Запрос содержит запрещённое ключевое слово: {keyword}")

    if "FROM" not in sql_upper:
        errors.append("Запрос должен содержать FROM")

    if sql.count("(") != sql.count(")"):
        errors.append("Несбалансированные круглые скобки")

    return errors


async def codegen_node(
    state: GraphState,
    llm: Optional[LLMClient] = None,
    **kwargs: Any,
) -> GraphState:
    llm = llm or LLMClient()
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")
    query_type = state.get("query_type")
    entities = state.get("entities", [])
    plan = state.get("plan", "")
    entity_candidates = state.get("entity_candidates", [])
    schema = state.get("schema", [])
    retry_count = state.get("retry_count", 0)
    retry_reason = state.get("retry_reason", "")
    prev_sql = state.get("sql_query", "")

    logger.info(
        "CodeGen Node [{}]: generating SQL for type={}, retry #{}, reason='{}'",
        request_id,
        query_type.value if query_type else "?",
        retry_count,
        retry_reason,
    )

    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
    candidates_text = json.dumps(entity_candidates[:15], ensure_ascii=False, indent=2)
    candidates_section = (
        f"\nСущности-кандидаты (item_name/supplier/sheet_period):\n{candidates_text}"
        if entity_candidates
        else ""
    )

    few_shot_text = "\n\n".join(
        f"Вопрос: {ex['question']}\nSQL: {ex['sql']}"
        for ex in FEW_SHOT_EXAMPLES
    )

    # Секция с информацией о предыдущей неудачной попытке
    retry_section = ""
    if retry_count > 0 and prev_sql:
        retry_section = f"""
ПРЕДЫДУЩАЯ ПОПЫТКА (ретрай #{retry_count}):
Причина ретрая: {retry_reason or 'не указана'}
Предыдущий SQL (не нашёл данных):
{prev_sql}

ИСПРАВЬ предыдущий SQL с учётом причины ретрая. Возможные исправления:
- Если причина 'empty_result' — попробуй убрать или смягчить условия WHERE (особенно price_source),
  используй более короткие ILIKE-маски для item_name_normalized (без лишних цифр и символов),
  или убери LIMIT чтобы увидеть все доступные данные
- Если причина 'wrong_filter' — исправь условия фильтрации
- Если причина 'wrong_table' — используй правильную таблицу
"""

    user_message = f"""Вопрос пользователя: {question}{candidates_section}{retry_section}

Тип запроса: {query_type.value if query_type else 'unknown'}
Сущности: {', '.join(entities) if entities else 'не определены'}

План действий:
{plan}

Схема mart.price_facts:
{schema_json}

Сгенерируй SQL-запрос для получения ответа на вопрос.

ВАЖНО: Для всех вопросов о ценах используй mart.price_facts — это единственная
нормализованная факт-таблица. Не используй fact_prices, entity_dictionary или cells.

Для поиска по названию лома используй ILIKE с item_name.
Для поиска по поставщику используй supplier ILIKE (если price_type = 'поставщик').

КРИТИЧЕСКОЕ ПРАВИЛО ДЛЯ ILIKE:
- Используй ТОЛЬКО те значения item_name/supplier, которые реально перечислены
  в сущностях-кандидатах (entity_candidates) в начале вопроса.
- НЕ выдумывай свои ILIKE-маски — если в кандидатах нет названия, не включай его.
- Если в кандидатах есть "лом алюминия стружка", используй ILIKE '%стружка%'
  или '%лом алюминия%', но не выдумывай лишние фрагменты.

Пример: если entity_candidates содержит item_name = "лом меди стружка", то
ILIKE '%медь%' или ILIKE '%стружка%' сработает."""

    messages = [
        {"role": "system", "content": CODEGEN_SYSTEM_PROMPT.format(
            few_shot_examples=few_shot_text
        )},
        {"role": "user", "content": user_message},
    ]

    try:
        # CodeGen — самый дорогой по цене ошибки узел для финансовых данных,
        # поэтому всегда используем основную (primary) модель, без cheap-fallback.
        raw_sql = await llm.chat(
            messages=messages,
            model=settings.LLM_MODEL_PRIMARY,
            temperature=0.1,
            max_tokens=2048,
        )

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

    if state["sql_query"]:
        state["validation_errors"] = validate_sql(state["sql_query"])
        logger.info(
            "CodeGen Node [{}]: validation errors: {}",
            request_id,
            len(state["validation_errors"]),
        )
    else:
        state["validation_errors"] = ["SQL-запрос пуст."]

    state["trace"] = state.get("trace", {})
    state["trace"][NODE_CODEGEN] = {
        "sql_query": state["sql_query"],
        "validation_errors": state["validation_errors"],
    }

    return state