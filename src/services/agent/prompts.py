from __future__ import annotations

PROMOPT_VERSION = "1.0.0"

PRICE_FACTS_SCHEMA = """Таблица mart.price_facts (нормализованная long-факт-таблица цен лома):
- sheet_period: TEXT — период 'YYYY-MM' (например, '2025-01', '2025-12')
- item_name: TEXT — нормализованное название лома (для ILIKE-поиска)
- supplier: TEXT — название поставщика (или NULL)
- price_type: TEXT — 'среднерыночная' | 'аукцион_старт' | 'аукцион_победитель' | 'поставщик'
- value: FLOAT — значение цены в руб/тн
- currency: TEXT — валюта (обычно 'RUB')
- unit: TEXT — единица измерения (обычно 'тн')
- is_blank: BOOL — TRUE если ячейка была пустой (не считать в средних)

ПРИМЕРЫ реальных данных:
- item_name: 'лом меди стружка', 'латунь лом', 'бронза', 'никель', 'алюминий стружка'
- supplier: 'северо-запад', 'ЦветМет', 'ООО Металл'
"""

METRICS_SCHEMA = """Таблица mart.metrics (универсальная long-таблица для план/факт/отклонение):
- period: TEXT — период 'YYYY-MM'
- dimension: TEXT — измерение (материал/шихта, например 'медь', 'алюминий')
- dimension_type: TEXT — тип измерения (например, 'item')
- metric_type: TEXT — 'план' | 'факт' | 'отклонение' | 'percent' | 'value'
- metric: TEXT — наименование метрики
- value: FLOAT — значение метрики
- unit: TEXT — единица измерения (например, '%')
- is_blank: BOOL — TRUE если ячейка была пустой
"""


def build_schema_section(domain: str) -> str:
    if domain == "metrics":
        return METRICS_SCHEMA
    return PRICE_FACTS_SCHEMA


def build_table_for_domain(domain: str) -> str:
    if domain == "metrics":
        return "mart.metrics"
    return "mart.price_facts"


def build_memory_context(
    conversation_history,
    max_steps: int = 6,
) -> str:
    """Формирует текстовый блок контекста из истории диалога.

    Память агента: берутся последние ``max_steps`` пар «вопрос-ответ»
    (т.е. до ``max_steps * 2`` реплик). Используется в промптах нод
    classifier / planner / answer, чтобы агент мог опираться на
    предыдущие запросы при уточнении.

    ``conversation_history`` — список dict вида ``{"role", "content"}``.
    """
    if not conversation_history:
        return ""

    recent = list(conversation_history)[-(max_steps * 2):]
    lines: list[str] = []
    for turn in recent:
        role_label = "Пользователь" if turn.get("role") == "user" else "Ассистент"
        content = (turn.get("content") or "").strip()
        if content:
            lines.append(f"{role_label}: {content}")

    if not lines:
        return ""

    return "\n".join(lines)