"""Детектор типа листа (sheet_kind): prices / matrix / generic.

По названию листа, шапке и наличию ключевых слов определяет семантический тип
таблицы. Это позволяет выбирать правильный extractor и правильную mart-таблицу
(price_facts для цен лома, metrics для план/факт/отклонение, generic как fallback).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# Ключевые слова, характерные для формата "цены лома".
_PRICE_KEYWORDS = (
    "цена", "руб", "тн", "аукцион", "старт", "победител", "среднерыночн",
    "лом", "цвет", "медь", "латун", "бронз", "никел", "алюмин", "металл",
)

# Ключевые слова, характерные для формата "шихта/план/факт/отклонение".
_MATRIX_KEYWORDS = (
    "план", "факт", "отклонен", "шихт", "процент", "%", "бюджет",
    "состав", "масса", "тонн", "кг",
)

# Шаблоны названий листов с месяцем/годом (формат цен лома).
_MONTH_PATTERN = re.compile(
    r"(янв|фев|мар|апр|май|июн|июл|авг|сен|окт|ноя|дек|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    re.IGNORECASE,
)


class SheetKind:
    """Константы типов листов."""
    PRICES = "prices"
    MATRIX = "matrix"
    GENERIC = "generic"


def detect_sheet_kind(
    sheet_name: str,
    headers: Optional[Iterable[str]] = None,
    sample_values: Optional[Iterable[Optional[str]]] = None,
) -> str:
    """Определяет тип листа.

    Args:
        sheet_name: исходное/нормализованное имя листа.
        headers: итерация заголовков колонок (нормализованных).
        sample_values: итерация примеров значений (для проверки числовых).

    Returns:
        Один из SheetKind.*: prices / matrix / generic.
    """
    name_lower = (sheet_name or "").lower()

    # 1. Доминирующий сигнал — явные слова формата matrix (план/факт/отклонение).
    matrix_text = " ".join(h or "" for h in (headers or [])) + " " + name_lower
    matrix_hits = sum(1 for kw in _MATRIX_KEYWORDS if kw in matrix_text)

    # 2. Сигнал формата prices (аукцион/цена/лом + месячное имя листа).
    price_text = " ".join(h or "" for h in (headers or [])) + " " + name_lower
    price_hits = sum(1 for kw in _PRICE_KEYWORDS if kw in price_text)

    # Если в заголовках явно "план"/"факт"/"отклонение" — это matrix.
    if matrix_hits >= 2 or any(k in name_lower for k in ("план", "факт", "отклонен", "бюджет")):
        return SheetKind.MATRIX

    # Если имя листа содержит месяц/год и есть "цена"/"лом"/"аукцион" — prices.
    if _MONTH_PATTERN.search(name_lower) and price_hits >= 1:
        return SheetKind.PRICES

    if price_hits >= 2:
        return SheetKind.PRICES

    # Fallback.
    return SheetKind.GENERIC