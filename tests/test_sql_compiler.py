import pytest

from src.services.agent.sql_compiler import (
    compile_select,
    compile_spec,
    validate_generated_sql,
    QueryType,
)


def test_lookup_compile():
    sql = compile_select({
        "table": "mart.price_facts",
        "columns": ["value"],
        "filters": [
            {"column": "sheet_period", "op": "=", "value": "2025-01"},
            {"column": "item_name", "op": "ILIKE", "value": "медь"},
        ],
        "limit": 1,
    })
    assert sql.startswith("SELECT mart.price_facts.value FROM mart.price_facts")
    assert "sheet_period = '2025-01'" in sql
    assert "item_name ILIKE '%медь%'" in sql
    assert "LIMIT 1" in sql


def test_aggregate_compile():
    sql = compile_select({
        "table": "mart.price_facts",
        "aggregation": {"func": "AVG", "column": "value", "group_by": ["sheet_period"]},
        "filters": [
            {"column": "price_type", "op": "=", "value": "среднерыночная"},
        ],
    })
    assert "AVG(mart.price_facts.value) AS avg_value" in sql
    assert "GROUP BY mart.price_facts.sheet_period" in sql
    assert "price_type = 'среднерыночная'" in sql


def test_metrics_table_compile():
    sql = compile_select({
        "table": "mart.metrics",
        "columns": ["dimension", "value"],
        "filters": [
            {"column": "metric_type", "op": "=", "value": "факт"},
        ],
    })
    assert "FROM mart.metrics" in sql
    assert "metric_type = 'факт'" in sql


def test_spec_delta_compile():
    sql = compile_spec({
        "query_type": QueryType.DELTA,
        "table": "mart.price_facts",
        "period_from": "2025-01",
        "period_to": "2025-02",
        "item_name": "медь",
    })
    assert "SELECT" in sql
    assert "val_from" in sql
    assert "val_to" in sql
    assert "delta" in sql


def test_validation_rejects_bad_table():
    with pytest.raises(ValueError):
        compile_select({"table": "raw.cells", "columns": ["*"]})


def test_validation_rejects_bad_column():
    with pytest.raises(ValueError):
        compile_select({"table": "mart.price_facts", "columns": ["information_schema.tables"]})


def test_generated_sql_validation():
    errors = validate_generated_sql("SELECT * FROM mart.price_facts LIMIT 5")
    assert errors == []

    errors = validate_generated_sql("DROP TABLE mart.price_facts")
    assert errors != []


def test_metrics_aggregate_by_dimension_and_metric():
    sql = compile_select({
        "table": "mart.metrics",
        "aggregation": {"func": "SUM", "column": "value", "alias": "суммарный_расход"},
        "filters": [
            {"column": "dimension", "op": "ILIKE", "value": "краснокаменская"},
            {"column": "metric", "op": "ILIKE", "value": "%расход%силос%"},
            {"column": "value", "op": "IS NOT NULL"},
        ],
    })
    assert "FROM mart.metrics" in sql
    assert "SUM(mart.metrics.value) AS суммарный_расход" in sql
    assert "dimension ILIKE '%краснокаменская%'" in sql
    assert "metric ILIKE '%%расход%силос%%'" in sql
    assert "value IS NOT NULL" in sql