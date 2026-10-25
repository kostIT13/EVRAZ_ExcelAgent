import pytest

from src.services.agent.sql_compiler import (
    QueryType,
    _compile_period_compare,
    _quote,
    compile_filter,
    compile_filters,
    compile_select,
    compile_spec,
    validate_generated_sql,
)


def test_quote_escapes_single_quotes():
    assert _quote("O'Brien") == "'O''Brien'"
    assert _quote("медь") == "'медь'"
    assert _quote(42) == "42"
    assert _quote(3.14) == "3.14"
    assert _quote(True) == "TRUE"
    assert _quote(False) == "FALSE"


def test_compile_filter_in_operator():
    sql = compile_filter("mart.price_facts", {
        "column": "item_name",
        "op": "IN",
        "value": ["Лом меди", "Лом латуни"],
    })
    assert sql == "mart.price_facts.item_name IN ('Лом меди', 'Лом латуни')"


def test_compile_filter_between_operator():
    sql = compile_filter("mart.price_facts", {
        "column": "value",
        "op": "BETWEEN",
        "value": [100, 200],
    })
    assert sql == "mart.price_facts.value BETWEEN 100 AND 200"


def test_compile_filter_null_operators():
    assert compile_filter("mart.price_facts", {"column": "supplier", "op": "IS NULL"}) == (
        "mart.price_facts.supplier IS NULL"
    )
    assert compile_filter("mart.price_facts", {"column": "supplier", "op": "IS NOT NULL"}) == (
        "mart.price_facts.supplier IS NOT NULL"
    )


def test_compile_filter_unsupported_operator_raises():
    with pytest.raises(ValueError):
        compile_filter("mart.price_facts", {"column": "value", "op": "FOO", "value": 1})


def test_compile_filters_or_group():
    filters = [
        {"or": [
            {"column": "item_name", "op": "=", "value": "Лом меди"},
            {"column": "item_name", "op": "=", "value": "Лом латуни"},
        ]},
        {"column": "price_type", "op": "=", "value": "среднерыночная"},
    ]
    out = compile_filters("mart.price_facts", filters)
    assert len(out) == 2
    assert out[0] == (
        "(mart.price_facts.item_name = 'Лом меди' OR "
        "mart.price_facts.item_name = 'Лом латуни')"
    )
    assert out[1] == "mart.price_facts.price_type = 'среднерыночная'"


def test_compile_select_distinct_and_order_by():
    sql = compile_select({
        "table": "mart.price_facts",
        "columns": ["supplier"],
        "distinct": True,
        "order_by": [{"column": "supplier", "desc": True}],
        "limit": 5,
    })
    assert sql.startswith("SELECT DISTINCT mart.price_facts.supplier")
    assert "ORDER BY mart.price_facts.supplier DESC" in sql
    assert "LIMIT 5" in sql


def test_compile_select_default_limit_100():
    sql = compile_select({"table": "mart.price_facts", "columns": ["value"]})
    assert "LIMIT 100" in sql


def test_compile_select_invalid_aggregation_func_raises():
    with pytest.raises(ValueError):
        compile_select({
            "table": "mart.price_facts",
            "aggregation": {"func": "MEDIAN", "column": "value"},
        })


def test_compile_select_aggregation_group_by_validation():
    with pytest.raises(ValueError):
        compile_select({
            "table": "mart.price_facts",
            "aggregation": {"func": "AVG", "column": "value", "group_by": ["evil_col"]},
        })


def test_period_compare_missing_period_raises():
    with pytest.raises(ValueError):
        _compile_period_compare({
            "table": "mart.price_facts",
            "period_from": "2025-01",
        })


def test_period_compare_with_item_filter():
    sql = _compile_period_compare({
        "table": "mart.price_facts",
        "period_from": "2025-01",
        "period_to": "2025-02",
        "item_name": "медь",
    })
    assert "val_from" in sql
    assert "val_to" in sql
    assert "delta" in sql
    assert "item_name ILIKE '%медь%'" in sql


def test_compile_spec_delta_uses_period_compare():
    sql = compile_spec({
        "query_type": QueryType.DELTA,
        "table": "mart.price_facts",
        "period_from": "2025-01",
        "period_to": "2025-02",
    })
    assert "val_from" in sql
    assert "delta" in sql


def test_validate_generated_sql_multiple_statements():
    errors = validate_generated_sql("SELECT 1; SELECT 2")
    assert any("несколько операторов" in e for e in errors)


def test_validate_generated_sql_not_select():
    errors = validate_generated_sql("UPDATE mart.price_facts SET value = 0")
    assert any("SELECT" in e for e in errors)