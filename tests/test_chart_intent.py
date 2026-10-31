"""Тесты распознавания графического интента и chart-хелперов агента."""
import json
from datetime import date
from decimal import Decimal
from uuid import uuid4

from src.services.agent.chart_intent import (
    build_chart_sql,
    chart_label_field,
    parse_chart_intent,
)
from src.services.agent.graph import (
    _extract_chart_data,
    _extract_chart_data_by_supplier,
)
from src.services.agent.nodes.answer_node import _chart_fallback_answer
from src.services.agent.nodes.executor_node import _json_safe, _sanitize_rows
from src.services.entity_resolution.query_cache import _json_safe_result


# --- parse_chart_intent ---


def test_parse_chart_intent_line_by_months():
    intent = parse_chart_intent(
        "Построй линейный график динамики цены на медь по месяцам"
    )
    assert intent == {"chart_type": "line", "group_by": "period"}


def test_parse_chart_intent_bar_by_suppliers():
    intent = parse_chart_intent(
        "Построй столбчатую диаграмму средней цены по поставщикам"
    )
    assert intent == {"chart_type": "bar", "group_by": "supplier"}


def test_parse_chart_intent_noun_only_defaults():
    # «График цены …» без явного типа: по умолчанию line/period.
    intent = parse_chart_intent("Покажи график цены на латунь")
    assert intent == {"chart_type": "line", "group_by": "period"}


def test_parse_chart_intent_histogram_suppliers():
    intent = parse_chart_intent("Сделай гистограмму цен по поставщикам")
    assert intent is not None
    assert intent["chart_type"] == "bar"
    assert intent["group_by"] == "supplier"


def test_parse_chart_intent_supplier_bar_default():
    # «Диаграмма по поставщикам» без слова «столбчатая» — bar по supplier.
    intent = parse_chart_intent("Построй диаграмму по поставщикам меди")
    assert intent == {"chart_type": "bar", "group_by": "supplier"}


def test_parse_chart_intent_not_chart():
    assert parse_chart_intent("Какая цена меди в январе?") is None
    assert parse_chart_intent("") is None
    assert parse_chart_intent(None) is None


# --- chart SQL helpers ---


def test_chart_label_field():
    assert chart_label_field("period", "mart.price_facts") == "fp.sheet_period"
    assert chart_label_field("period", "mart.metrics") == "period"
    assert chart_label_field("supplier", "mart.price_facts") == "fp.supplier"
    assert chart_label_field("supplier", "mart.metrics") == "supplier"


def test_build_chart_sql_period_grouping():
    sql, params = build_chart_sql(
        "mart.price_facts", "WHERE fp.item_name ILIKE :cat", {"cat": "%медь%"}, "period"
    )
    assert "GROUP BY fp.sheet_period" in sql
    assert "ORDER BY fp.sheet_period ASC" in sql
    assert "LIMIT" not in sql
    assert params == {"cat": "%медь%"}


def test_build_chart_sql_supplier_grouping():
    sql, _ = build_chart_sql("mart.price_facts", "", {}, "supplier")
    assert "GROUP BY fp.supplier" in sql
    assert "ORDER BY value DESC" in sql
    assert "LIMIT 15" in sql


# --- chart data extraction ---


def test_extract_chart_data_timeseries():
    rows = [
        {"sheet_period": "2025-01", "avg_price": 100.0},
        {"sheet_period": "2025-02", "avg_price": 110.0},
    ]
    points = _extract_chart_data(rows)
    assert points == [
        {"period": "2025-01", "value": 100.0},
        {"period": "2025-02", "value": 110.0},
    ]


def test_extract_chart_data_not_timeseries():
    assert _extract_chart_data([{"avg_price": 100.0}]) is None
    assert _extract_chart_data([]) is None


def test_extract_chart_data_by_supplier():
    rows = [
        {"supplier": "Ферроком", "avg_price": 100.0},
        {"supplier": "Сплав-21", "avg_price": 120.0},
    ]
    points = _extract_chart_data_by_supplier(rows)
    assert points == [
        {"period": "Ферроком", "value": 100.0},
        {"period": "Сплав-21", "value": 120.0},
    ]


def test_extract_chart_data_by_supplier_aggregates_and_filters():
    rows = [
        {"поставщик": "Ферроком", "цена": 100.0},
        {"поставщик": "Ферроком", "цена": 50.0},
        {"поставщик": "Сплав-21", "цена": 120.0},
        {"поставщик": None, "цена": 1.0},
    ]
    points = _extract_chart_data_by_supplier(rows)
    assert points == [
        {"period": "Ферроком", "value": 150.0},
        {"period": "Сплав-21", "value": 120.0},
    ]


def test_extract_chart_data_by_supplier_no_supplier_key():
    assert _extract_chart_data_by_supplier([{"a": 1, "b": 2}, {"a": 3, "b": 4}]) is None
    assert _extract_chart_data_by_supplier([]) is None


# --- Decimal-safe extraction (NUMERIC из БД) ---


def test_extract_chart_data_accepts_decimal():
    rows = [
        {"sheet_period": "2025-01", "avg_price": Decimal("100.5")},
        {"sheet_period": "2025-02", "avg_price": Decimal("110.5")},
    ]
    points = _extract_chart_data(rows)
    assert points == [
        {"period": "2025-01", "value": 100.5},
        {"period": "2025-02", "value": 110.5},
    ]


def test_extract_chart_data_by_supplier_accepts_decimal():
    rows = [
        {"supplier": "Ферроком", "avg_price": Decimal("100.0")},
        {"supplier": "Сплав-21", "avg_price": Decimal("120.0")},
    ]
    points = _extract_chart_data_by_supplier(rows)
    assert points == [
        {"period": "Ферроком", "value": 100.0},
        {"period": "Сплав-21", "value": 120.0},
    ]


# --- JSON-safety (исправление 'Object of type Decimal is not JSON serializable') ---


def test_json_safe_converts_decimal_date_uuid():
    u = uuid4()
    assert _json_safe(Decimal("10.25")) == 10.25
    assert _json_safe(date(2025, 12, 1)) == "2025-12-01"
    assert _json_safe(u) == str(u)
    assert _json_safe("text") == "text"


def test_sanitize_rows_makes_result_json_serializable():
    rows = [
        {"supplier": "Ферроком", "avg_price": Decimal("100.5"), "period": date(2025, 1, 1)},
        {"supplier": None, "avg_price": Decimal("0")},
    ]
    safe = _sanitize_rows(rows)
    # Не должно бросить TypeError.
    json.dumps(safe)
    assert safe[0]["avg_price"] == 100.5
    assert safe[0]["period"] == "2025-01-01"


def test_json_safe_result_nested():
    result = {
        "data": [{"value": Decimal("1.5")}],
        "formatted_answer": "ok",
    }
    safe = _json_safe_result(result)
    json.dumps(safe)
    assert safe["data"][0]["value"] == 1.5
    assert _json_safe_result(None) is None


# --- chart fallback answer (объяснение графика без LLM) ---


def test_chart_fallback_answer_line_period():
    rows = [
        {"месяц": "2025-01", "средняя_цена": 100000},
        {"месяц": "2025-02", "средняя_цена": 105000},
    ]
    text = _chart_fallback_answer(
        rows, {"chart_type": "line", "group_by": "period"}
    )
    assert "Линейный график по месяцам" in text
    assert "точек — 2" in text
    assert "минимум — 100 000" in text
    assert "максимум — 105 000" in text


def test_chart_fallback_answer_bar_suppliers():
    rows = [
        {"supplier": "Ферроком", "avg_price": 100.0},
        {"supplier": "Сплав-21", "avg_price": 120.0},
    ]
    text = _chart_fallback_answer(
        rows, {"chart_type": "bar", "group_by": "supplier"}
    )
    assert "Столбчатая диаграмма по поставщикам" in text


def test_chart_fallback_answer_without_numbers():
    text = _chart_fallback_answer([], {"chart_type": "bar", "group_by": "supplier"})
    assert "Построен столбчатая диаграмма по поставщикам" in text
    # Без chart_request — значения по умолчанию (bar/period).
    assert _chart_fallback_answer([], None) == "Построен столбчатая диаграмма по месяцам."
