# -*- coding: utf-8 -*-
"""Финальная проверка сгенерированной презентации."""
import os
from pptx import Presentation

OUT = "scripts/final_check.txt"


def main() -> None:
    path = "data/EVRAZ_Agent_updated.pptx"
    p = Presentation(path)
    lines = [
        f"Slides: {len(p.slides)}",
        f"Size: {os.path.getsize(path)} bytes",
        "Valid PPTX: OK",
        f"Slide size: {p.slide_width} x {p.slide_height}",
    ]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("done")


if __name__ == "__main__":
    main()
