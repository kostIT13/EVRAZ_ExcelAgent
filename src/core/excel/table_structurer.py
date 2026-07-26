"""Table Structurer — превращает generic cells-grid в нормализованную факт-таблицу.

На входе: ParsedSheet с сырыми данными (data, headers, cells)
На выходе: список FactPriceRow (период | наименование_лома | источник_цены | значение)

Логика:
1. Определяет период из названия листа (например, "цвломна_дек25" → "2025-12")
2. Находит колонку с наименованием лома (обычно col_index=2)
3. Для каждой строки извлекает:
   - наименование лома (нормализованное: strip, lowercase, сжатие пробелов)
   - цены из разных источников (среднерыночная, поставщики, аукцион)
4. Возвращает список плоских записей для вставки в fact_prices
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from src.core.excel.schemas import ParsedSheet, ParsedHeader
from src.core.logging_settings import logger


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FactPriceRow:
    """Одна запись в нормализованной факт-таблице."""
    period: str
    item_name_raw: str
    item_name_normalized: str
    price_source: str
    price_value: Optional[float]
    row_num: int


# ---------------------------------------------------------------------------
# Constants: column index mapping for the known Excel structure
# ---------------------------------------------------------------------------

# Based on the actual Excel file structure:
# Col 1: № п/п (id)
# Col 2: Наименование лома
# Col 3: Ед. изм.
# Col 4: Кол-во
# Col 5: Среднерыночная цена, руб/тн (с НДС)
# Col 6-N: Поставщики (каждый со своей ценой)
# Last cols: Результаты аукциона (стартовая цена, предложение победителя)

COL_ITEM_NAME = 2
COL_UNIT = 3
COL_QUANTITY = 4
COL_MARKET_PRICE = 5

# Паттерны для определения источника цены по заголовку колонки
PRICE_SOURCE_PATTERNS: List[Tuple[str, str]] = [
    # (pattern, source_name)
    (r'среднерыночн', 'среднерыночная'),
    (r'средн[её]?рыночн', 'среднерыночная'),
    (r'стартов[ая]?', 'аукцион_старт'),
    (r'старт', 'аукцион_старт'),
    (r'победител', 'аукцион_победитель'),
    (r'итог', 'аукцион_победитель'),
    (r'результат', 'аукцион_победитель'),
]

# Паттерны для извлечения периода из названия листа
# Например: "цвломна_дек25" → период "2025-12"
MONTH_MAP: Dict[str, str] = {
    'янв': '01', 'фев': '02', 'мар': '03', 'апр': '04',
    'май': '05', 'июн': '06', 'июл': '07', 'авг': '08',
    'сен': '09', 'окт': '10', 'ноя': '11', 'дек': '12',
}

MONTH_MAP_RU: Dict[str, str] = {
    'январь': '01', 'февраль': '02', 'март': '03', 'апрель': '04',
    'май': '05', 'июнь': '06', 'июль': '07', 'август': '08',
    'сентябрь': '09', 'октябрь': '10', 'ноябрь': '11', 'декабрь': '12',
}


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_item_name(name: str) -> str:
    """Нормализует наименование лома: strip, lowercase, сжатие пробелов."""
    if not name:
        return ""
    name = str(name).strip()
    name = re.sub(r'\s+', ' ', name)
    return name


def extract_period_from_sheet_name(sheet_name: str) -> str:
    """Извлекает период из названия листа.

    Примеры:
        "цвломна_дек25" → "2025-12"
        "цвломна_янв25" → "2025-01"
        "Лист1" → "unknown"
    """
    name_lower = sheet_name.lower().strip()

    # Паттерн: месяц_год (дек25, янв2025, etc.)
    for ru_month, month_num in MONTH_MAP.items():
        pattern = rf'{ru_month}\s*(\d{{2,4}})'
        match = re.search(pattern, name_lower)
        if match:
            year_str = match.group(1)
            if len(year_str) == 2:
                year = f"20{year_str}"
            else:
                year = year_str
            return f"{year}-{month_num}"

    # Паттерн: полное название месяца
    for ru_month, month_num in MONTH_MAP_RU.items():
        if ru_month in name_lower:
            # Ищем год рядом
            year_match = re.search(r'(20\d{2}|\d{2})', name_lower)
            year_str = year_match.group(1) if year_match else "2025"
            if len(year_str) == 2:
                year = f"20{year_str}"
            else:
                year = year_str
            return f"{year}-{month_num}"

    # Паттерн: номер месяца (01_25, 01.2025)
    match = re.search(r'(0[1-9]|1[0-2])[._]?(20\d{2}|\d{2})', name_lower)
    if match:
        parts = re.split(r'[._]', match.group(0))
        if len(parts) == 2:
            month_num = parts[0]
            year_str = parts[1]
            if len(year_str) == 2:
                year = f"20{year_str}"
            else:
                year = year_str
            return f"{year}-{month_num}"

    return "unknown"


def infer_price_source(header: ParsedHeader, col_index: int) -> str:
    """Определяет источник цены по заголовку колонки.

    Returns:
        - 'среднерыночная'
        - 'аукцион_старт'
        - 'аукцион_победитель'
        - Имя поставщика (если не подходит под паттерны)
    """
    full_name = header.full_name.lower() if header.full_name else ""
    col_name = header.col_name.lower() if header.col_name else ""

    for pattern, source in PRICE_SOURCE_PATTERNS:
        if re.search(pattern, full_name) or re.search(pattern, col_name):
            return source

    # Если это не стандартная колонка — считаем поставщиком
    # Используем original_name как имя поставщика
    original = header.full_name or header.col_name or f"поставщик_{col_index}"
    return original.strip()


# ---------------------------------------------------------------------------
# Main structurer
# ---------------------------------------------------------------------------

class TableStructurer:
    """Превращает ParsedSheet в список FactPriceRow."""

    def __init__(self, sheet: ParsedSheet):
        self.sheet = sheet
        self.period = extract_period_from_sheet_name(sheet.sheet_name)

    def structure(self) -> List[FactPriceRow]:
        """Основной метод: структурирует лист в факт-таблицу."""
        rows: List[FactPriceRow] = []
        period = self.period

        logger.debug(
            "Structuring sheet '{}' (period={}, {} data rows)",
            self.sheet.sheet_name,
            period,
            len(self.sheet.data),
        )

        for row_idx, row_data in enumerate(self.sheet.data):
            # Извлекаем наименование лома
            item_name_raw = self._get_item_name(row_data)
            if not item_name_raw:
                continue

            item_name_normalized = normalize_item_name(item_name_raw)

            # Пропускаем строки-разделители (пустые, "0", "Итого")
            if self._is_separator_row(item_name_normalized):
                continue

            row_num = row_idx + 1  # 1-based

            # Для каждой ценовой колонки создаём запись
            for header in self.sheet.headers:
                col_index = header.col_index

                # Пропускаем не-ценовые колонки
                if not self._is_price_column(header, col_index):
                    continue

                price_value = self._get_price_value(row_data, header.col_name)
                if price_value is None:
                    continue

                price_source = infer_price_source(header, col_index)

                rows.append(FactPriceRow(
                    period=period,
                    item_name_raw=item_name_raw,
                    item_name_normalized=item_name_normalized,
                    price_source=price_source,
                    price_value=price_value,
                    row_num=row_num,
                ))

        logger.debug(
            "Sheet '{}': produced {} fact price rows",
            self.sheet.sheet_name,
            len(rows),
        )
        return rows

    def _get_item_name(self, row_data: Dict[str, Any]) -> Optional[str]:
        """Извлекает наименование лома из строки данных."""
        # Ищем колонку с col_index = COL_ITEM_NAME
        for header in self.sheet.headers:
            if header.col_index == COL_ITEM_NAME:
                val = row_data.get(header.col_name)
                if val is not None:
                    return str(val).strip()
        return None

    def _is_separator_row(self, name: str) -> bool:
        """Проверяет, является ли строка разделителем/итогом."""
        if not name:
            return True
        name_lower = name.lower().strip()
        if name_lower in ('', '0', 'итого', 'итог', 'всего', 'сумма'):
            return True
        return False

    def _is_price_column(self, header: ParsedHeader, col_index: int) -> bool:
        """Определяет, является ли колонка ценовой."""
        # Колонки 1-4 — не ценовые (id, наименование, ед.изм., кол-во)
        if col_index <= 4:
            return False

        # Все остальные колонки с числами — ценовые
        return True

    def _get_price_value(self, row_data: Dict[str, Any], col_name: str) -> Optional[float]:
        """Извлекает числовое значение цены из строки."""
        val = row_data.get(col_name)
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            val = val.strip()
            if not val:
                return None
            try:
                cleaned = val.replace(' ', '').replace(',', '.')
                return float(cleaned)
            except ValueError:
                return None
        return None