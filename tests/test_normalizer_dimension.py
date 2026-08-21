from types import SimpleNamespace

from src.services.mart.normalizer import _pick_dimension_column


def _col(index: int, name: str):
    return SimpleNamespace(col_index=index, normalized_name=name)


def test_picks_supplier_column_over_numeric_leftmost():
    columns = [
        _col(1, "59823"),
        _col(2, "шихтовочный_лист_поставщики"),
        _col(14, "расход_в"),
        _col(15, "запас_угля_сут"),
    ]
    assert _pick_dimension_column(columns) == 2


def test_fallback_to_text_column():
    columns = [_col(1, "59823"), _col(14, "расход_в"), _col(15, "запас_угля_сут")]
    assert _pick_dimension_column(columns) == 14


def test_fallback_to_leftmost_when_all_numeric():
    columns = [_col(1, "59823"), _col(2, "182988")]
    assert _pick_dimension_column(columns) == 1


def test_empty_returns_none():
    assert _pick_dimension_column([]) is None