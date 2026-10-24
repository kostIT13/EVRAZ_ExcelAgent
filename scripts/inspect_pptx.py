# -*- coding: utf-8 -*-
"""Инспектор презентации: печатает содержимое слайдов в scripts/pptx_dump.txt (UTF-8)."""
import sys
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

PATH = sys.argv[1] if len(sys.argv) > 1 else "data/EVRAZ_Agent_main.pptx"
RANGE = sys.argv[2] if len(sys.argv) > 2 else "all"
OUT = "scripts/pptx_dump.txt"

prs = Presentation(PATH)
rng = range(1, len(prs.slides) + 1) if RANGE == "all" else [int(x) for x in RANGE.split(",")]


def shape_info(sh, idx):
    info = [f"  [{idx}] name={sh.shape_type!s} id={sh.shape_id} '{sh.name}'"]
    try:
        info.append(f"      pos=({sh.left},{sh.top}) size=({sh.width},{sh.height}) rot={sh.rotation}")
    except Exception:
        pass
    if sh.shape_type == MSO_SHAPE_TYPE.TABLE:
        tbl = sh.table
        info.append(f"      TABLE {len(tbl.rows)}x{len(tbl.columns)}")
        for r in tbl.rows:
            info.append(f"      ROW: {' | '.join(c.text.replace(chr(10), '⏎') for c in r.cells)}")
    elif sh.has_text_frame:
        t = sh.text_frame.text.replace("\n", " ⏎ ")
        if t.strip():
            info.append(f"      TEXT: {t}")
    return "\n".join(info)


with open(OUT, "w", encoding="utf-8") as f:
    for n in rng:
        slide = prs.slides[n - 1]
        f.write(f"\n{'='*70}\nSLIDE {n}\n")
        for i, sh in enumerate(slide.shapes):
            f.write(shape_info(sh, i) + "\n")
print(f"written -> {OUT}")
