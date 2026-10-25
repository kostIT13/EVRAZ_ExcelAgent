from src.services.agent.nodes.codegen_node import (
    _clean_sql_text,
    _normalize_is_blank_filters,
    _refine_all_kinds_filter,
    _refine_supplier_ilike_any,
    _refine_supplier_in_filter,
    validate_sql,
)


def test_validate_sql_accepts_select():
    assert validate_sql("SELECT value FROM mart.price_facts LIMIT 1") == []


def test_validate_sql_rejects_non_select():
    errors = validate_sql("DROP TABLE mart.price_facts")
    assert any("SELECT" in e for e in errors)


def test_validate_sql_rejects_forbidden_keywords():
    for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"):
        errors = validate_sql(f"SELECT 1; {kw} TABLE x")
        assert any("запрещённое" in e for e in errors), kw


def test_validate_sql_rejects_missing_from():
    errors = validate_sql("SELECT 1")
    assert any("FROM" in e for e in errors)


def test_validate_sql_rejects_unbalanced_parens():
    errors = validate_sql("SELECT (1 FROM mart.price_facts")
    assert any("скобки" in e for e in errors)


def test_clean_sql_text_markdown_wrapper():
    raw = "```sql\nSELECT value FROM mart.price_facts;\n```"
    assert _clean_sql_text(raw) == "SELECT value FROM mart.price_facts"


def test_clean_sql_text_preamble():
    raw = "Вот SQL:\nSELECT value FROM mart.price_facts LIMIT 1"
    assert _clean_sql_text(raw) == "SELECT value FROM mart.price_facts LIMIT 1"


def test_clean_sql_text_trailing_semicolon():
    assert _clean_sql_text("SELECT 1;") == "SELECT 1"


def test_clean_sql_text_empty_and_no_sql():
    assert _clean_sql_text("") == ""
    assert _clean_sql_text("просто текст без SQL") == ""


def test_refine_all_kinds_filter_narrows_to_prefix():
    sql = "SELECT fp.value FROM mart.price_facts fp WHERE fp.item_name ILIKE '%мед%'"
    refined = _refine_all_kinds_filter("Какая средняя цена на все виды меди?", sql)
    assert "item_name ILIKE 'Лом меди%'" in refined
    assert "%мед%" not in refined


def test_refine_all_kinds_filter_ignores_non_all_kinds():
    sql = "SELECT fp.value FROM mart.price_facts fp WHERE fp.item_name ILIKE '%мед%'"
    assert _refine_all_kinds_filter("Цена на медь?", sql) == sql


def test_refine_supplier_in_filter_to_ilike_group():
    sql = (
        "SELECT fp.value FROM mart.price_facts fp "
        "WHERE fp.supplier IN ('шами-сервис', 'сплав-21')"
    )
    refined = _refine_supplier_in_filter(sql)
    assert "fp.supplier ILIKE '%шамисервис%'" in refined
    assert "fp.supplier ILIKE '%сплав21%'" in refined
    assert "IN" not in refined


def test_refine_supplier_ilike_any_normalizes_dashes():
    sql = (
        "SELECT m.value FROM mart.metrics m "
        "WHERE m.supplier ILIKE ANY (ARRAY['%шами-сервис%', '%сплав-21%'])"
    )
    refined = _refine_supplier_ilike_any(sql)
    assert "'%шамисервис%'" in refined
    assert "'%сплав21%'" in refined
    assert "'%шами-сервис%'" not in refined


def test_normalize_is_blank_filters_boolean_to_int():
    assert _normalize_is_blank_filters("WHERE is_blank = FALSE") == "WHERE is_blank = 0"
    assert _normalize_is_blank_filters("WHERE is_blank = TRUE") == "WHERE is_blank = 1"
    assert _normalize_is_blank_filters("WHERE m.is_blank IS FALSE") == "WHERE m.is_blank = 0"
    assert _normalize_is_blank_filters(
        "WHERE COALESCE(m.is_blank, FALSE) = FALSE"
    ) == "WHERE m.is_blank = 0"