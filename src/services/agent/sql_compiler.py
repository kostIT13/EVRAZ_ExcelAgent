"""Детерминированный SQL-компилятор: структурированный JSON -> SQL.

Вместо генерации SQL текстом LLM (ненадёжно), агент выдаёт структурированный
JSON (таблица, колонки, фильтры, агрегация), который этот модуль компилирует
в безопасный SELECT. Поддерживает обе mart-таблицы (price_facts, metrics),
агрегации AVG/SUM/MIN/MAX, группировку, сортировку и лимит.

Безопасность: компилятор не позволяет никакие операции кроме SELECT и строго
ограничивает схему (только mart.*) и имена колонок белым списком.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from src.core.logging_settings import logger


class QueryType(str, Enum):
    """Типы структурированных запросов."""
    LOOKUP = "lookup"
    AGGREGATE = "aggregate"
    CROSS_SHEET = "cross_sheet"
    DELTA = "delta"
    SUM_BY_SUPPLIER = "sum_by_supplier"
    FIND_PERIOD = "find_period"


# Белый список колонок для mart.price_facts.
_PRICE_FACTS_COLUMNS = {
    "id", "file_id", "sheet_id", "source_row_ref", "sheet_period", "item_name",
    "supplier", "price_type", "value", "currency", "unit", "is_blank",
}

# Белый список колонок для mart.metrics.
_METRICS_COLUMNS = {
    "id", "file_id", "sheet_id", "source_row_ref", "dimension_type", "dimension",
    "period", "metric_type", "metric", "value", "unit", "is_blank",
}

# Допустимые таблицы (только mart-схема, read-only).
ALLOWED_TABLES = {
    "mart.price_facts": _PRICE_FACTS_COLUMNS,
    "mart.metrics": _METRICS_COLUMNS,
}

# Допустимые агрегатные функции.
AGG_FUNCS = {"AVG", "SUM", "MIN", "MAX", "COUNT"}

# Допустимые операторы сравнения для фильтров.
_COMPARE_OPS = {"=", "!=", "<>", "<", "<=", ">", ">="}
_LIKE_OPS = {"ILIKE", "LIKE"}


def _quote(value: Any) -> str:
    """Безопасно экранирует строковый литерал."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _validate_column(table: str, column: str) -> None:
    allowed = ALLOWED_TABLES.get(table)
    if allowed is None:
        raise ValueError(f"Неизвестная таблица: {table}")
    if column not in allowed:
        raise ValueError(f"Колонка '{column}' не входит в белый список для {table}")


def compile_filter(table: str, cond: Dict[str, Any]) -> str:
    """Компилирует одно условие фильтра в SQL-выражение."""
    column = cond.get("column")
    op = (cond.get("op") or "=").upper()
    value = cond.get("value")

    if not column:
        raise ValueError("Фильтр должен содержать column")
    _validate_column(table, column)

    if op in _COMPARE_OPS:
        return f"{table}.{column} {op} {_quote(value)}"
    if op in _LIKE_OPS:
        return f"{table}.{column} {op} '%{value}%'"
    if op == "IS NULL":
        return f"{table}.{column} IS NULL"
    if op == "IS NOT NULL":
        return f"{table}.{column} IS NOT NULL"
    if op == "IN":
        items = ", ".join(_quote(v) for v in (value or []))
        return f"{table}.{column} IN ({items})"
    if op == "BETWEEN":
        return f"{table}.{column} BETWEEN {_quote(value[0])} AND {_quote(value[1])}"
    raise ValueError(f"Неподдерживаемый оператор фильтра: {op}")


def compile_filters(table: str, filters: List[Dict[str, Any]]) -> List[str]:
    """Компилирует список фильтров (AND-связка)."""
    out = []
    for f in filters or []:
        if "condition" in f and isinstance(f["condition"], (list, tuple)):
            # Несколько условий в одной группе — объединяем через OR.
            group = " OR ".join(compile_filter(table, c) for c in f["condition"])
            out.append(f"({group})")
        elif "or" in f and isinstance(f["or"], list):
            group = " OR ".join(compile_filter(table, c) for c in f["or"])
            out.append(f"({group})")
        else:
            out.append(compile_filter(table, f))
    return out


def compile_select(spec: Dict[str, Any]) -> str:
    """Компилирует структурированный запрос в SELECT SQL.

    Ожидаемая структура spec:
    {
      "table": "mart.price_facts" | "mart.metrics",
      "columns": ["item_name", "value"],          # колонки для SELECT
      "filters": [{column, op, value}, ...],
      "aggregation": {func: "AVG", column: "value", group_by: ["supplier"]},
      "order_by": [{"column": "value", "desc": true}],
      "limit": 50,
      "distinct": false,
      "join": { ... }   # опционально (для delta / cross_sheet) — не реализуется
    }
    """
    table = spec.get("table")
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Таблица должна быть одной из: {list(ALLOWED_TABLES)}")

    # SELECT-часть.
    columns = spec.get("columns") or ["*"]
    select_items: List[str] = []
    aggregation = spec.get("aggregation")
    group_by: List[str] = []

    if aggregation:
        func = aggregation.get("func", "AVG").upper()
        if func not in AGG_FUNCS:
            raise ValueError(f"Недопустимая агрегация: {func}")
        col = aggregation.get("column", "value")
        if col != "*":
            _validate_column(table, col)
        agg_expr = f"{func}({table}.{col})"
        alias = aggregation.get("alias") or f"{func.lower()}_{col.replace('.', '_')}"
        select_items.append(f"{agg_expr} AS {alias}")
        for g in aggregation.get("group_by") or []:
            _validate_column(table, g)
            group_by.append(g)
            select_items.append(f"{table}.{g}")
    else:
        for c in columns:
            if c == "*":
                select_items.append(f"{table}.*")
            else:
                _validate_column(table, c)
                select_items.append(f"{table}.{c}")

    # WHERE-часть.
    where = compile_filters(table, spec.get("filters") or [])
    where_sql = f" WHERE {' AND '.join(where)}" if where else ""

    group_sql = f" GROUP BY {', '.join(table + '.' + g for g in group_by)}" if group_by else ""

    # ORDER BY.
    order_sql = ""
    order_by = spec.get("order_by") or []
    if order_by:
        parts = []
        for o in order_by:
            col = o.get("column")
            _validate_column(table, col)
            direction = " DESC" if o.get("desc") else " ASC"
            parts.append(f"{table}.{col}{direction}")
        order_sql = f" ORDER BY {', '.join(parts)}"

    # LIMIT.
    limit = spec.get("limit")
    if limit is None:
        limit = 100  # безопасный дефолт
    limit_sql = f" LIMIT {int(limit)}"

    distinct = " DISTINCT" if spec.get("distinct") else ""

    sql = (
        f"SELECT{distinct} {', '.join(select_items)}"
        f" FROM {table}"
        f"{where_sql}{group_sql}{order_sql}{limit_sql}"
    )
    return sql


def compile_spec(spec: Dict[str, Any]) -> str:
    """Высокоуровневый компилятор по типу запроса.

    Дополнительно обрабатывает типы CROSS_SHEET / DELTA (сравнение по периодам),
    строя подзапросы по двух периодам.
    """
    qtype = spec.get("query_type")
    try:
        if qtype in (QueryType.CROSS_SHEET, QueryType.DELTA):
            return _compile_period_compare(spec)
        return compile_select(spec)
    except Exception as exc:
        logger.error("compile_spec failed: {}", exc)
        raise


def _compile_period_compare(spec: Dict[str, Any]) -> str:
    """Строит сравнение между двумя периодами (подзапросы)."""
    table = spec.get("table")
    period_from = spec.get("period_from")
    period_to = spec.get("period_to")
    agg = spec.get("aggregation") or {"func": "MAX", "column": "value"}

    if not period_from or not period_to:
        raise ValueError("Для CROSS_SHEET/DELTA нужны period_from и period_to")

    func = agg.get("func", "MAX").upper()
    col = agg.get("column", "value")
    _validate_column(table, col)
    item_filter = ""
    if spec.get("item_name"):
        _validate_column(table, "item_name")
        item_filter = f" AND {table}.item_name ILIKE '%{spec['item_name']}%'"

    sub_from = (
        f"(SELECT {func}({table}.{col}) AS v FROM {table} "
        f"WHERE {table}.sheet_period = {_quote(period_from)}"
        f"{item_filter})"
    )
    sub_to = (
        f"(SELECT {func}({table}.{col}) AS v FROM {table} "
        f"WHERE {table}.sheet_period = {_quote(period_to)}"
        f"{item_filter})"
    )
    select_items = [
        f"{sub_from} AS val_from",
        f"{sub_to} AS val_to",
        f"({sub_to} - {sub_from}) AS delta",
    ]
    return f"SELECT {', '.join(select_items)}"


def validate_generated_sql(sql: str) -> List[str]:
    """Пост-проверка скомпилированного SQL (должен быть уже безопасным)."""
    errors: List[str] = []
    upper = sql.strip().upper()
    if not upper.startswith("SELECT"):
        errors.append("Запрос не начинается с SELECT")
    if ";" in sql.rstrip(";"):
        errors.append("Запрос содержит несколько операторов")
    return errors