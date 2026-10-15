# -*- coding: utf-8 -*-
"""Извлечение реальных данных о ценах из data/data_proportional_prices.xlsx для графика."""
import sys
import traceback

try:
    import pandas as pd
except Exception:
    traceback.print_exc()
    sys.exit(1)

OUT = "scripts/price_chart_data.txt"


def main() -> None:
    path = "data/data_proportional_prices.xlsx"
    xl = pd.ExcelFile(path)
    lines = [f"Sheets: {xl.sheet_names}"]
    for name in xl.sheet_names:
        df = xl.parse(name, header=None, nrows=8)
        lines.append(f"--- {name} ---")
        lines.append(df.head(8).to_string(max_colwidth=30))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"OK, wrote {len(lines)} lines to {OUT}")


if __name__ == "__main__":
    main()
