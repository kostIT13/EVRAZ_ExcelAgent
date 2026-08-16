from __future__ import annotations
import hashlib
import json
from typing import Any, Dict, List, Optional


def compute_sheet_fingerprint(
    cells: Dict[str, Any],
    merged_cells: Optional[List[str]] = None,
    max_rows: int = 30,
) -> str:
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
    digits = "".join(ch for ch in coord if ch.isdigit())
    try:
        return int(digits)
    except ValueError:
        return 0