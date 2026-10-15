"""Инспекция структуры существующей презентации EVRAZ_Agent.pptx."""
import sys
from pptx import Presentation
from pptx.util import Emu

OUT = "scripts/pptx_inspect_dump.txt"


def main() -> None:
    path = "data/EVRAZ_Agent.pptx"
    p = Presentation(path)
    lines = []
    lines.append(f"Slide size: {p.slide_width} x {p.slide_height} = "
                 f"{Emu(p.slide_width).inches:.2f} x {Emu(p.slide_height).inches:.2f} in")
    lines.append(f"Num slides: {len(p.slides)}")
    lines.append(f"Num layouts: {len(p.slide_layouts)}")
    for i, layout in enumerate(p.slide_layouts):
        lines.append(f"  layout {i}: {layout.name}")
    lines.append("---")
    for i, slide in enumerate(p.slides):
        lines.append(f"SLIDE {i} | layout: {slide.slide_layout.name}")
        for shape in slide.shapes:
            t = ""
            if shape.has_text_frame:
                t = " | ".join(par.text for par in shape.text_frame.paragraphs if par.text)[:200]
            lines.append(f"   shape: {shape.shape_type} | name: {shape.name!r} | text: {t!r}")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"OK, wrote {len(lines)} lines to {OUT}")


if __name__ == "__main__":
    main()
