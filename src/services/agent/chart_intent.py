"""Распознавание графического интента в вопросе пользователя.

Позволяет агенту строить графики по прямому запросу, например:
  * «Построй линейный график динамики цены на медь по месяцам»
  * «Построй столбчатую диаграмму средней цены по поставщикам»

Распознавание детерминированное (regex/ключевые слова), без LLM —
дёшево и стабильно. Результат кладётся в GraphState.chart_request
и переиспользуется в graph.LangGraphAgent для формирования chart_data.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

# Глаголы/существительные, указывающие на запрос визуализации.
_CHART_NOUNS = (
    "график",
    "диаграмм",
    "гистограмм",
    "визуализ",
)

# Явные указания типа графика.
_LINE_MARKERS = ("линейн", "динамик", "линия", "тренд")
_BAR_MARKERS = ("столбчат", "гистограмм", "столбик", "диаграмм", "сравнен")

# Группировка данных.
_SUPPLIER_MARKERS = ("поставщик",)
_PERIOD_MARKERS = ("месяц", "период", "динамик", "по времени", "помесяц")

_LIMIT_SUPPLIERS = 15


def parse_chart_intent(question: str) -> Optional[Dict[str, str]]:
    """Определяет, просит ли пользователь построить график.

    Возвращает ``None``, если запрос не графический, иначе dict:
      * ``chart_type`` — 'line' (линейный) | 'bar' (столбчатая);
      * ``group_by``   — 'period' (по месяцам) | 'supplier' (по поставщикам).
    """
    q = (question or "").lower()
    if not q:
        return None

    if not any(noun in q for noun in _CHART_NOUNS):
        return None

    is_line = any(m in q for m in _LINE_MARKERS)
    is_bar = any(m in q for m in _BAR_MARKERS)
    by_supplier = any(m in q for m in _SUPPLIER_MARKERS)
    by_period = any(m in q for m in _PERIOD_MARKERS)

    if is_line:
        chart_type = "line"
    elif is_bar:
        chart_type = "bar"
    else:
        # Без явного типа: временные ряды логичнее показывать линией,
        # распределения по поставщикам — столбцами.
        chart_type = "line" if not by_supplier else "bar"

    if by_supplier and not by_period:
        group_by = "supplier"
    else:
        # «по месяцам»/«динамика» или отсутствие явной группировки → период.
        group_by = "period"

    return {
        "chart_type": chart_type,
        "group_by": group_by,
    }


def chart_label_field(group_by: str, table: str) -> str:
    """SQL-выражение для оси X в зависимости от группировки и таблицы."""
    if group_by == "supplier":
        return "fp.supplier" if "price_facts" in table else "supplier"
    if "price_facts" in table:
        return "fp.sheet_period"
    return "period"


def build_chart_sql(
    table: str,
    where_sql: str,
    params: Dict[str, Any],
    group_by: str,
) -> tuple[str, Dict[str, Any]]:
    """Собирает SQL для графика: ряд по периодам или по поставщикам.

    Возвращает (sql, params).
    """
    label = chart_label_field(group_by, table)
    # Поставщики: сортируем по убыванию значения (топ-N), периоды — по времени.
    order = "value DESC" if group_by == "supplier" else f"{label} ASC"
    limit = f"\nLIMIT {_LIMIT_SUPPLIERS}" if group_by == "supplier" else ""
    sql = f"""
SELECT {label} AS period, AVG(fp.value) AS value
FROM {table} fp
{where_sql}
GROUP BY {label}
ORDER BY {order}{limit}"""
    return sql, params


__all__ = [
    "parse_chart_intent",
    "chart_label_field",
    "build_chart_sql",
]
