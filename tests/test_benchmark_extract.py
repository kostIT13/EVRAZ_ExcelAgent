"""Тесты extract_number из бенчмарка (парсинг чисел из ответов агента)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmark"))

from benchmark.benchmark_core import extract_number  # noqa: E402


def test_extract_number_skips_hyphenated_names():
    """«Сплав-21» в тексте ответа не должен приниматься за ответ (-21)."""
    text = (
        "Дельта между минимальной и максимальной ценой на все виды медного лома "
        "по данным компаний Ферроком, Сплав-21, ЦветМет и Шами-сервис в феврале "
        "2025 года составила 438 350,1 руб/тн."
    )
    assert extract_number(text) == 438350.1


def test_extract_number_negative_word():
    assert extract_number("Цена снизилась на 100 руб/тн") == -100.0
    assert extract_number("цена упала на 21,5") == -21.5


def test_extract_number_plain():
    assert extract_number("Средняя цена составила 2 697 900 руб./тн.") == 2697900.0
    assert extract_number("696 625,15") == 696625.15
    assert extract_number("25 219,5") == 25219.5


def test_extract_number_skips_years():
    assert extract_number("В 2025 году цена составила 164 220 руб/тн") == 164220.0


def test_extract_number_name_before_number():
    """Название с дефисом перед реальным числом — число берётся."""
    assert extract_number("ВРП-1 цена 25 219,5 руб/тн") == 25219.5


def test_extract_number_none():
    assert extract_number("") is None
    assert extract_number("нет данных") is None
