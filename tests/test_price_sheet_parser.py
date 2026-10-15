from pathlib import Path
import pytest
from src.core.excel.parser import ExcelParser
from src.core.excel.sheet_kind_detector import detect_sheet_kind
from src.core.excel.table_structurer import extract_period_from_sheet_name

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PRICES_FILE = DATA_DIR / "data_proportional_prices.xlsx"

pytestmark = pytest.mark.skipif(
    not PRICES_FILE.exists(),
    reason="нет файла данных",
)


@pytest.fixture(scope="module")
def prices_parsed():
    return ExcelParser(PRICES_FILE).parse()


@pytest.fixture(scope="module")
def first_sheet(prices_parsed):
    return prices_parsed.sheets[0]


def test_file_has_twelve_monthly_sheets(prices_parsed):
    assert len(prices_parsed.sheets) == 12
    assert prices_parsed.sheets[0].sheet_name == "цв.лом(на дек25)"


def test_first_sheet_header_rows_detected(first_sheet):
    # 3 объединённые строки шапки: титул, поставщики, цены аукциона.
    assert first_sheet.header_rows == 3


def test_first_sheet_key_columns(first_sheet):
    by_name = {h.col_name: h for h in first_sheet.headers}
    assert "наименование_лома" in by_name
    assert by_name["наименование_лома"].full_name == "Наименование лома"
    assert "среднерыночная_цена_рубтн" in by_name
    assert by_name["среднерыночная_цена_рубтн"].full_name.startswith("Среднерыночная цена")
    # Вычисляемая колонка аукциона тоже присутствует в шапке.
    assert "по_результатам_аукциона" in by_name


def test_first_sheet_supplier_columns(first_sheet):
    names = {h.col_name for h in first_sheet.headers}
    assert {"ферроком", "сплав21", "цветмет", "шамисервис"}.issubset(names)


def test_first_sheet_data_rows(first_sheet):
    assert first_sheet.row_count == 78


def test_first_sheet_item_column_values(first_sheet):
    items = [row.get("наименование_лома") for row in first_sheet.data]
    assert items[0] == "Лом меди кусок"
    assert all(it is not None and str(it).strip() for it in items)


def test_first_sheet_period_and_kind(first_sheet):
    assert extract_period_from_sheet_name(first_sheet.sheet_name) == "2025-12"
    headers = [h.col_name for h in first_sheet.headers]
    assert detect_sheet_kind(first_sheet.sheet_name, headers) == "prices"


def test_parser_is_deterministic():
    """Повторный парсинг даёт тот же хэш файла (идемпотентность ingest)."""
    first = ExcelParser(PRICES_FILE).parse()
    second = ExcelParser(PRICES_FILE).parse()
    assert first.file_hash == second.file_hash
    assert first.file_hash