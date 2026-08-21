from pathlib import Path

import pytest

from src.core.excel.parser import ExcelParser

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PRICES_FILE = DATA_DIR / "data_proportional_prices.xlsx"
FAKED_FILE = DATA_DIR / "Faked_List_proportional (2).xlsx"


def _header_rows_for(file_path: Path, sheet_name: str) -> int:
    parsed = ExcelParser(file_path).parse()
    for sheet in parsed.sheets:
        if sheet.sheet_name == sheet_name:
            return sheet.header_rows
    raise AssertionError(f"Лист '{sheet_name}' не найден")


def _sheet_columns(file_path: Path, sheet_name: str):
    parsed = ExcelParser(file_path).parse()
    for sheet in parsed.sheets:
        if sheet.sheet_name == sheet_name:
            return {h.col_index: h.col_name for h in sheet.headers}
    raise AssertionError(f"Лист '{sheet_name}' не найден")


@pytest.mark.skipif(not PRICES_FILE.exists(), reason="нет файла данных")
def test_prices_header_rows_unchanged():
    assert _header_rows_for(PRICES_FILE, "цв.лом(на дек25)") >= 1


@pytest.mark.skipif(not PRICES_FILE.exists(), reason="нет файла данных")
def test_prices_has_item_and_price_columns():
    cols = _sheet_columns(PRICES_FILE, "цв.лом(на дек25)")
    names = {v for v in cols.values()}
    assert any("наименование" in n for n in names)
    assert any("среднерыночн" in n for n in names)


@pytest.mark.skipif(not FAKED_FILE.exists(), reason="нет файла данных")
def test_faked_2_blok_parses_real_headers():
    assert _header_rows_for(FAKED_FILE, "2 блок") == 11
    cols = _sheet_columns(FAKED_FILE, "2 блок")
    names = {v for v in cols.values()}
    assert any("поставщик" in n for n in names), names
    assert any("расход" in n for n in names), names


@pytest.mark.skipif(not FAKED_FILE.exists(), reason="нет файла данных")
def test_faked_3_blok_parses_real_headers():
    assert _header_rows_for(FAKED_FILE, "3 блок") == 4
    cols = _sheet_columns(FAKED_FILE, "3 блок")
    names = {v for v in cols.values()}
    assert any("поставщик" in n for n in names), names