# -*- coding: utf-8 -*-
"""Создание LR-версий (горизонтальных) Mermaid-диаграмм для презентации."""
import os

SRC = "diagrams"
DST = "scripts/mermaid"
TARGETS = ["architecture", "agent_pipeline", "excel_ingestion", "deployment"]


def main() -> None:
    for name in TARGETS:
        src = os.path.join(SRC, f"{name}.mmd")
        dst = os.path.join(DST, f"{name}_lr.mmd")
        with open(src, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("flowchart TD", "flowchart LR", 1)
        with open(dst, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"OK: {dst}")


if __name__ == "__main__":
    main()
