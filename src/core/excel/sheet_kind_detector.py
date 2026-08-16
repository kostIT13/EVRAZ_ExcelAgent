from __future__ import annotations
import re
from typing import Iterable, Optional

_PRICE_KEYWORDS = (
    "цена", "руб", "тн", "аукцион", "старт", "победител", "среднерыночн",
    "лом", "цвет", "медь", "латун", "бронз", "никел", "алюмин", "металл",
)

_MATRIX_KEYWORDS = (
    "план", "факт", "отклонен", "шихт", "процент", "%", "бюджет",
    "состав", "масса", "тонн", "кг",
)

_MONTH_PATTERN = re.compile(
    r"(янв|фев|мар|апр|май|июн|июл|авг|сен|окт|ноя|дек|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    re.IGNORECASE,
)


class SheetKind:
    PRICES = "prices"
    MATRIX = "matrix"
    GENERIC = "generic"


def detect_sheet_kind(
    sheet_name: str,
    headers: Optional[Iterable[str]] = None,
    sample_values: Optional[Iterable[Optional[str]]] = None,
) -> str:
    name_lower = (sheet_name or "").lower()

    matrix_text = " ".join(h or "" for h in (headers or [])) + " " + name_lower
    matrix_hits = sum(1 for kw in _MATRIX_KEYWORDS if kw in matrix_text)

    price_text = " ".join(h or "" for h in (headers or [])) + " " + name_lower
    price_hits = sum(1 for kw in _PRICE_KEYWORDS if kw in price_text)

    if matrix_hits >= 2 or any(k in name_lower for k in ("план", "факт", "отклонен", "бюджет")):
        return SheetKind.MATRIX

    if _MONTH_PATTERN.search(name_lower) and price_hits >= 1:
        return SheetKind.PRICES

    if price_hits >= 2:
        return SheetKind.PRICES

    return SheetKind.GENERIC