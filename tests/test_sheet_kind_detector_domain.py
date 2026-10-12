"""Unit-тесты детектора типа листа (prices / matrix / generic).

Использует реальные заголовки первой таблицы как эталон PRICES-листа
и типовые матричные листы (шихтовочный лист) как эталон MATRIX.
"""
from src.core.excel.sheet_kind_detector import SheetKind, detect_sheet_kind

# Заголовки первого листа data/data_proportional_prices.xlsx (цв.лом(на дек25)).
PRICES_HEADERS = [
    "пп",
    "наименование_лома",
    "врп_у",
    "северозапад_втормет",
    "ферроком",
    "сплав21",
    "цветмет",
    "шамисервис",
    "уралметресурс",
    "среднерыночная_цена_рубтн",
    "результаты_аукциона_271025_стартовая_цена_августа",
    "результаты_аукциона_271025_предлож_победителя",
    "по_результатам_аукциона",
]

SUPPLIER_SAMPLES = ["Лом меди кусок", "892946.25", "Ферроком"]


def test_monthly_prices_sheet_is_prices():
    assert detect_sheet_kind(
        "цв.лом(на дек25)", PRICES_HEADERS, SUPPLIER_SAMPLES
    ) == SheetKind.PRICES


def test_any_month_in_name_with_price_keywords_is_prices():
    assert detect_sheet_kind("цв.лом(на янв25)", PRICES_HEADERS) == SheetKind.PRICES


def test_matrix_шихтовочный_лист():
    headers = ["поставщик", "план_июл25", "факт_июл25", "отклонение_%"]
    assert detect_sheet_kind("Шихтовочный лист 2 блок", headers) == SheetKind.MATRIX


def test_budget_sheet_is_matrix():
    headers = ["статья", "план", "факт", "отклонение"]
    assert detect_sheet_kind("Бюджет на шихту", headers) == SheetKind.MATRIX


def test_generic_fallback():
    assert detect_sheet_kind("Лист1", ["колонка_a", "колонка_b"]) == SheetKind.GENERIC
    assert detect_sheet_kind("", []) == SheetKind.GENERIC