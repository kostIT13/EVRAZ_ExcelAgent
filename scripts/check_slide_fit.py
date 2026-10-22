# -*- coding: utf-8 -*-
"""Грубая оценка переполнения текстовых полей на слайдах 4, 5, 11, 12.

Оценка: ширина символа ~0.5 * size_pt / 72 (дюйма), высота строки ~1.22 * size_pt / 72.
Если текст не помещается в выделенную высоту бокса и word_wrap включён — выводим предупреждение.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pptx import Presentation
from pptx.util import Emu

SLIDES_TO_CHECK = {4, 5, 11, 12}  # 1-based номера в собранном файле


def inches(emu_value):
    return emu_value / 914400.0


def estimate(text: str, size_pt: float, box_w_in: float):
    """(оценка ширины текста в дюймах, оценка числа строк при wrap)"""
    char_w_in = 0.52 * size_pt / 72.0
    # Учитываем только первые 500 символов для скорости
    t = text[:500]
    width = 0.0
    for ch in t:
        if ch == " ":
            width += 0.30 * size_pt / 72.0
        else:
            width += char_w_in
    # ширина в дюймах при линейном наборе
    lines = max(1, -(-len(text) // max(1, int(box_w_in / char_w_in))))
    return width, lines


def main():
    prs = Presentation("data/EVRAZ_Agent_defense.pptx")
    for idx, slide in enumerate(prs.slides, start=1):
        if idx not in SLIDES_TO_CHECK:
            continue
        print(f"===== Слайд {idx} =====")
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            tf = shape.text_frame
            text = "\n".join(p.text for p in tf.paragraphs)
            if not text.strip():
                continue
            # определяем размер шрифта первого run первого параграфа
            size_pt = 18.0
            for p in tf.paragraphs:
                for r in p.runs:
                    if r.font.size is not None:
                        size_pt = r.font.size.pt
                        break
                if size_pt != 18.0:
                    break
            w = inches(shape.width)
            h = inches(shape.height)
            _, lines = estimate(text, size_pt, w)
            line_h = 1.25 * size_pt / 72.0
            needed = lines * line_h
            overflow = needed > h
            flag = "  <-- ПЕРЕПОЛНЕНИЕ?" if overflow else ""
            print(f"  [x={inches(shape.left):.2f}, y={inches(shape.top):.2f}, "
                  f"w={w:.2f}, h={h:.2f}] size={size_pt:.0f} lines~{lines} need={needed:.2f}{flag}")
            print(f"      '{text[:90].replace(chr(10), ' / ')}'")
    print("Готово.")


if __name__ == "__main__":
    main()
