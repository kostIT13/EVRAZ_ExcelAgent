"""Unit-тесты структурирования первой таблицы (TableStructurer).

Проверяют извлечение периода из имени листа и построение фактов цен:
наименование лома, источники цен (среднерыночная / аукцион_старт /
аукцион_победитель / поставщики), пропуск служебных строк.
"""
from pathlib import Path

import pytest

from src.core.excel.parser import ExcelParser
from src.core.excel.table_structurer import TableStructurer, extract_period_from_sheet_name

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PRICES_FILE = DATA_DIR / "data_proportional_prices.xlsx"

pytestmark = pytest.mark.skipif(
    not PRICES_FILE.exists(),
    reason="нет файла данных",
)


@pytest.fixture(scope="module")
def factual_rows():
    parsed = ExcelParser(PRICES_FILE).parse()
    sheet = parsed.sheets[0]
    return TableStructurer(sheet).structure()


def test_period_from_month_abbreviation():
    assert extract_period_from_sheet_name("цв.лом(на дек25)") == "2025-12"
    assert extract_period_from_sheet_name("цв.лом(на янв25)") == "2025-01"
    assert extract_period_from_sheet_name("цв.лом(на окт25)") == "2025-10"


def test_period_unknown_for_generic_name():
    assert extract_period_from_sheet_name("Сводный лист") == "unknown"


def test_structure_exports_expected_row_count(factual_rows):
    # 78 строк данных × колонки цен (поставщики + среднерыночная + аукцион).
    assert len(factual_rows) == 369


def test_first_item_prices_present(factual_rows):
    first = factual_rows[0]
    assert first.item_name_raw == "Лом меди кусок"
    assert first.period == "2025-12"
    assert first.row_num == 1


def test_market_and_auction_prices_resolved(factual_rows):
    rows_for_item = [r for r in factual_rows if r.item_name_raw == "Лом меди кусок"]

    market = [r.price_value for r in rows_for_item if r.price_source == "среднерыночная"]
    assert market == [892946.25]

    start = [r.price_value for r in rows_for_item if r.price_source == "аукцион_старт"]
    assert 868020.0 in start

    winner = [r.price_value for r in rows_for_item if r.price_source == "аукцион_победитель"]
    # Побеждает предложение победителя (не вычисленное среднее).
    assert 985906.5 in winner


def test_supplier_columns_kept_as_sources(factual_rows):
    sources = {(r.item_name_raw, r.price_source) for r in factual_rows}
    assert ("Лом меди кусок", "Ферроком") in sources
    assert ("Лом меди кусок", "Сплав-21") in sources


def test_separator_rows_are_skipped(factual_rows):
    separators = {"итого", "итог", "всего", "сумма", ""}
    assert all(
        r.item_name_normalized.lower() not in separators
        for r in factual_rows
    )


def test_all_facts_have_numeric_prices(factual_rows):
    assert all(isinstance(r.price_value, (int, float)) for r in factual_rows)