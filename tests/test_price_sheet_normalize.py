from types import SimpleNamespace
from src.core.excel.normalize import (
    COLUMN_TYPE_NUMBER,
    COLUMN_TYPE_PRICE,
    COLUMN_TYPE_TEXT,
    ExcelNormalizer,
)
from src.core.excel.schemas import ParsedHeader


def _header(col_name: str, full_name: str | None = None) -> SimpleNamespace:
    name = full_name or col_name
    return SimpleNamespace(col_name=col_name, full_name=name, levels=[name])


def test_item_column_detected_as_text():
    header = _header("наименование_лома")
    assert ExcelNormalizer.infer_column_type(
        header, ["Лом меди кусок", "Лом латуни"]
    ) == COLUMN_TYPE_TEXT


def test_price_column_detected_as_price():
    header = _header("среднерыночная_цена_рубтн", "Среднерыночная цена, руб./тн")
    assert ExcelNormalizer.infer_column_type(header, [892946.25]) == COLUMN_TYPE_PRICE


def test_supplier_column_without_keywords_is_text_by_samples():
    header = _header("ферроком")
    assert ExcelNormalizer.infer_column_type(
        header, ["844560", "920805"]
    ) == COLUMN_TYPE_TEXT


def test_numeric_column_detected_by_samples():
    header = _header("колонка_без_ключевых_слов")
    assert ExcelNormalizer.infer_column_type(header, [1, 2, 3]) == COLUMN_TYPE_NUMBER


def test_normalize_value_parses_price_with_spaces_and_comma():
    assert ExcelNormalizer.normalize_value("1 234,5", COLUMN_TYPE_PRICE) == 1234.5
    assert ExcelNormalizer.normalize_value("12 345", COLUMN_TYPE_NUMBER) == 12345.0


def test_normalize_value_trims_text():
    assert ExcelNormalizer.normalize_value("  Лом меди кусок  ") == "Лом меди кусок"


def test_normalize_value_collapses_extra_spaces():
    assert ExcelNormalizer.normalize_value("Лом меди   кусок") == "Лом меди кусок"


def test_normalize_value_none_is_preserved():
    assert ExcelNormalizer.normalize_value(None) is None


def test_extract_sample_values_dedups_until_limit():
    rows = [
        {"наименование_лома": "A"},
        {"наименование_лома": "B"},
        {"наименование_лома": "A"},
        {"наименование_лома": None},
    ]
    assert ExcelNormalizer.extract_sample_values(rows, "наименование_лома") == ["A", "B"]


def test_real_first_sheet_column_types():
    """Типы колонок первой таблицы на реальных заголовках и выборках."""
    from pathlib import Path

    import pytest

    from src.core.excel.parser import ExcelParser

    data_file = Path(__file__).resolve().parent.parent / "data" / "data_proportional_prices.xlsx"
    if not data_file.exists():
        pytest.skip("нет файла данных")

    sheet = ExcelParser(data_file).parse().sheets[0]
    types = {}
    for header in sheet.headers:
        samples = ExcelNormalizer.extract_sample_values(sheet.data, header.col_name)
        types[header.col_name] = ExcelNormalizer.infer_column_type(header, samples)

    assert types["наименование_лома"] == COLUMN_TYPE_TEXT
    assert types["среднерыночная_цена_рубтн"] == COLUMN_TYPE_PRICE