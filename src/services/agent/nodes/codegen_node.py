from __future__ import annotations

import json
import re
from typing import Any, List, Optional

from src.core.config import settings
from src.core.logging_settings import logger
from src.services.agent.graph_state import Domain, GraphState, NODE_CODEGEN
from src.services.agent.sql_compiler import compile_spec, validate_generated_sql
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
        "question": "Какова средняя цена на все виды медного лома в феврале 2025?",
        "sql": """SELECT AVG(fp.value) AS средняя_цена
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-02'
  AND fp.item_name ILIKE 'Лом меди%'""",
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


# Словоформы металлов в родительном падеже для префиксного поиска "все виды".
_MATERIAL_FORMS = {
    "мед": "меди",
    "алюмин": "алюминия",
    "латун": "латуни",
    "бронз": "бронзы",
    "никел": "никеля",
    "цинк": "цинка",
    "свинц": "свинца",
    "баббит": "баббита",
}


def _refine_all_kinds_filter(question: str, sql: str) -> str:
    """Сужает широкий item_name ILIKE '%X%' до префикса 'Лом <металл>%'
    для запросов 'все виды <металла>', чтобы не захватывать составные/легированные
    материалы (медно-никелевые сплавы, сложные сплавы, оребрение и т.п.)."""
    if not re.search(r"\bвсе\s+виды?\b", question, re.IGNORECASE):
        return sql
    m = re.search(r"(?i)item_name\s+ILIKE\s+'%([^']+)%'", sql)
    if not m:
        return sql
    root = m.group(1).lower()
    form = next((v for k, v in _MATERIAL_FORMS.items() if k in root), None)
    if not form:
        return sql
    prefix = f"Лом {form}"
    return sql[: m.start()] + f"item_name ILIKE '{prefix}%'" + sql[m.end():]


def _refine_supplier_in_filter(sql: str) -> str:
    """Заменяет <prefix>supplier IN ('a','b',...) на группу OR
    <prefix>supplier ILIKE '%a%', убирая дефисы/пробелы, чтобы перекрыть
    реальные названия поставщиков (например 'шами-сервис' -> 'шамисервис',
    'сплав-21' -> 'сплав21')."""
    pattern = re.compile(r"(?i)(([\w.]*)supplier\s+IN\s*\()([^)]*)(\))")

    def _repl(m: re.Match) -> str:
        prefix = m.group(2)  # например 'fp.'
        inner = m.group(3)
        items = re.findall(r"'([^']*)'", inner)
        if not items:
            return m.group(0)
        clauses = []
        for it in items:
            norm = re.sub(r"[\s-]+", "", it).lower()
            if norm:
                clauses.append(f"{prefix}supplier ILIKE '%{norm}%'")
        if not clauses:
            return m.group(0)
        return "(" + " OR ".join(clauses) + ")"

    return pattern.sub(_repl, sql)


def _refine_supplier_ilike_any(sql: str) -> str:
    """Нормализует дефисы/пробелы в значениях массива
    supplier ILIKE ANY (ARRAY['%x%', ...]), чтобы перекрыть реальные названия
    поставщиков (например '%шами-сервис%' -> '%шамисервис%', '%сплав-21%' -> '%сплав21%')."""
    pattern = re.compile(r"(?i)(supplier\s+ILIKE\s+ANY\s*\(ARRAY\[)([^\]]*)(\])")

    def _repl(m: re.Match) -> str:
        inner = m.group(2)
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        cleaned = []
        for p in parts:
            s = p.strip()
            if len(s) >= 2 and s.startswith("'"):
                core = s[1:-1]
                core = re.sub(r"[\s-]+", "", core)
                cleaned.append(f"'{core}'")
            else:
                cleaned.append(s)
        return m.group(1) + ", ".join(cleaned) + m.group(3)

    return pattern.sub(_repl, sql)


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
    domain = state.get("domain")
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
нормализованная факт-таблица. Не используй entity_dictionary или cells.

Для поиска по названию лома используй ILIKE с item_name.
Для поиска по поставщику используй supplier ILIKE (если price_type = 'поставщик').

КРИТИЧЕСКОЕ ПРАВИЛО РАЗЛИЧЕНИЯ ВИДОВ ЛОМА:
- item_name — ЭТО ТОЧНОЕ название конкретного вида лома (например, "Лом меди кусок",
  "Лом меди трубка с оребрением медь 87,2%", "Лом алюминия (блоки УБРС)" — это
  РАЗНЫЕ виды с разными ценами).
- Используй ТОЛЬКО ТОЧНЫЕ значения item_name из entity_candidates, СИМВОЛ-В-СИМВОЛ.
  НЕ сокращай, НЕ переставляй и НЕ переписывай названия. Даже если в кандидате есть
  спецсимволы (запятые, %, скобки, пробелы) — копируй название целиком.
- Если вопрос перечисляет несколько видов (IN-список) — каждый элемент IN берётся
  РОВНО из entity_candidates, а не выдумывается.
- Для каждого вида выбирай ТОЧНОЕ совпадение с конкретным кандидатом:
    WHERE fp.item_name = 'Лом меди кусок'
  или для нескольких:
    WHERE fp.item_name IN ('Лом меди кусок', 'Лом меди микс', 'Лом меди трубка с оребрением медь 87,2%')
- ILIKE '%...%' применяй ТОЛЬКО если пользователь явно просит "все виды"/"любой"/обобщение.
- НЕ выдумывай название вида, которого нет в entity_candidates — если его нет, значит
  такого вида в данных нет, и его не нужно включать в запрос.

КРИТИЧЕСКОЕ ПРАВИЛО ДЛЯ "ВСЕХ ВИДОВ" МЕТАЛЛА:
Когда пользователь просит "все виды <металла>" (например, "все виды меди",
"все виды медного лома", "все виды алюминия") — используй ПРЕФИКСНЫЙ поиск по
item_name в родительном падеже: item_name ILIKE 'Лом <металл>%'.
НЕ используй широкую подстроку вида item_name ILIKE '%мед%' — она захватывает
НЕ подходящие материалы: медно-никелевые сплавы, сложные сплавы с небольшим
содержанием металла, трубки с оребрением другого металла.

ПРИМЕРЫ:
- "все виды меди" → item_name ILIKE 'Лом меди%'  (а НЕ '%мед%')
- "все виды алюминия" → item_name ILIKE 'Лом алюминия%'  (а НЕ '%алюмин%')
- "все виды латуни" → item_name ILIKE 'Лом латуни%'
- "цена на лом алюминия" → item_name = 'Лом алюминия'

Выбирай из entity_candidates РОВНО те значения, которые соответствуют словам
пользователя, и применяй к ним точное сравнение (не ILIKE) во всех случаях,
кроме явного запроса на все виды."""

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

        # Детерминированная правка: для "все виды <металла>" сужаем широкий
        # %металл% до префикса 'Лом <металл>%', чтобы не включать сплавы/оребрение.
        refined = _refine_all_kinds_filter(question, sql)
        if refined != sql:
            sql = refined
            logger.info(
                "CodeGen Node [{}]: refined 'all kinds' item filter to prefix",
                request_id,
            )

        # Детерминированная правка: supplier IN (...) -> OR supplier ILIKE '%x%'
        # (нормализуем дефисы/пробелы в названиях поставщиков).
        refined_suppliers = _refine_supplier_in_filter(sql)
        if refined_suppliers != sql:
            sql = refined_suppliers
            logger.info(
                "CodeGen Node [{}]: refined supplier IN(...) to ILIKE group",
                request_id,
            )

        # Нормализуем дефисы/пробелы в supplier ILIKE ANY (ARRAY[...])
        refined_any = _refine_supplier_ilike_any(sql)
        if refined_any != sql:
            sql = refined_any
            logger.info(
                "CodeGen Node [{}]: normalized supplier ILIKE ANY(ARRAY[...]) values",
                request_id,
            )

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
        # Инкремент счётчика ретраев, чтобы не зациклить codegen при ошибке.
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["trace"] = state.get("trace", {})
        state["trace"][NODE_CODEGEN] = {"error": str(exc)}
        return state

    # --- Детерминированный SQL-компилятор ---
    # Если Classifier/Planner дал структурированный spec (строку JSON), компилируем
    # его в безопасный SELECT напрямую, что надёжнее LLM-генерации текстом.
    compiled_spec = state.get("sql_spec") or state.get("compiled_spec")
    if compiled_spec:
        try:
            spec = compiled_spec if isinstance(compiled_spec, dict) else json.loads(compiled_spec)
            state["sql_query"] = compile_spec(spec)
            state["validation_errors"] = validate_generated_sql(state["sql_query"])
            logger.info(
                "CodeGen Node [{}]: SQL compiled from spec ({} chars)",
                request_id,
                len(state["sql_query"]),
            )
            state["trace"] = state.get("trace", {})
            state["trace"][NODE_CODEGEN] = {
                "sql_query": state["sql_query"],
                "validation_errors": state["validation_errors"],
                "compiled_from_spec": True,
            }
            if state["validation_errors"]:
                state["retry_count"] = state.get("retry_count", 0) + 1
            return state
        except Exception as exc:
            logger.warning(
                "CodeGen Node [{}]: spec compile failed ({}), falling back to LLM SQL",
                request_id,
                exc,
            )

    if state["sql_query"]:
        state["validation_errors"] = validate_sql(state["sql_query"])
        logger.info(
            "CodeGen Node [{}]: validation errors: {}",
            request_id,
            len(state["validation_errors"]),
        )
    else:
        state["validation_errors"] = ["SQL-запрос пуст."]

    # Инкремент счётчика ретраев, чтобы не зациклить codegen при ошибках валидации.
    if state["validation_errors"]:
        state["retry_count"] = state.get("retry_count", 0) + 1

    state["trace"] = state.get("trace", {})
    state["trace"][NODE_CODEGEN] = {
        "sql_query": state["sql_query"],
        "validation_errors": state["validation_errors"],
    }

    return state