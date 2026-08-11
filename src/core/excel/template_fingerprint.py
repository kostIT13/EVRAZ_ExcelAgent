"""Отпечаток структуры листа (fingerprint) для кэширования LLM-схем.

Считает детерминированный хэш структуры листа по набору непустых координат
(первые N строк) + паттерну merged cells. При повторной загрузке файла того же
формата fingerprint совпадает, и сохранённая подтверждённая схема применяется
без повторного вызова LLM (schema inference).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional


def compute_sheet_fingerprint(
    cells: Dict[str, Any],
    merged_cells: Optional[List[str]] = None,
    max_rows: int = 30,
) -> str:
    """Считает fingerprint листа.

    Args:
        cells: словарь {координата (например, 'B3') → значение}.
        merged_cells: список строк-описаний merged cells (например, ['A1:B2']).
        max_rows: сколько верхних строк учитывать для определения шапки.

    Returns:
        SHA-256 hex строка.
    """
    # Нормализуем координаты: фильтруем первые max_rows строк.
    prefix_cells: List[str] = []
    for coord in sorted(cells.keys()):
        row_num = _row_index(coord)
        if row_num <= max_rows:
            prefix_cells.append(f"{coord}")

    payload: Dict[str, Any] = {
        "cells": prefix_cells,
        "merged": sorted(merged_cells or []),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _row_index(coord: str) -> int:
    """Извлекает номер строки из координаты вида 'B3' → 3."""
    digits = "".join(ch for ch in coord if ch.isdigit())
    try:
        return int(digits)
    except ValueError:
        return 0