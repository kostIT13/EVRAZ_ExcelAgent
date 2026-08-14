"""Системные промпты агента, вынесенные в шаблоны.

Идея (plan.md, этап 6): промпты — не хардкод в узлах, а версионируемые шаблоны
с подстановкой псевдосхемы. Это позволяет:
- править промпты в одном месте;
- добавлять псевдосхему (пример данных) чтобы LLM не выдумывал значения;
- версионировать через PROMPT_VERSION.
"""
from __future__ import annotations

PROMOPT_VERSION = "1.0.0"

# Псевдосхема для mart.price_facts — пример данных, чтобы LLM не выдумывал.
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

# Псевдосхема для mart.metrics.
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
    """Возвращает секцию псевдосхемы для заданного домена."""
    if domain == "metrics":
        return METRICS_SCHEMA
    return PRICE_FACTS_SCHEMA


def build_table_for_domain(domain: str) -> str:
    """Возвращает mart-таблицу для домена."""
    if domain == "metrics":
        return "mart.metrics"
    return "mart.price_facts"