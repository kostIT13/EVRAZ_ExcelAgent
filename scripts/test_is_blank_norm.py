"""Временный скрипт: проверка нормализации is_blank."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.agent.nodes.codegen_node import _normalize_is_blank_filters

OUT = "scripts/is_blank_norm_dump.txt"
lines = []
tests = [
    "AND m.is_blank = FALSE",
    "AND COALESCE(m.is_blank, FALSE) = FALSE",
    "AND fp.is_blank = TRUE",
    "AND is_blank IS FALSE",
    "AND m.is_blank = 0",
]
for t in tests:
    lines.append(f"{t!r} -> {_normalize_is_blank_filters(t)!r}")

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print("written", OUT)