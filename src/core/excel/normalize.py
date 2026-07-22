import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from src.core.excel.schemas import ParsedSheet, ParsedHeader


COLUMN_TYPE_NUMBER = "number"
COLUMN_TYPE_PRICE = "price"
COLUMN_TYPE_DATE = "date"
COLUMN_TYPE_TEXT = "text"
COLUMN_TYPE_ID = "id"


class ExcelNormalizer:
    PRICE_PATTERNS = [
        r'цена', r'price', r'стоим', r'руб', r'usd', r'eur',
        r'сумма', r'итого', r'cost', r'amount',
    ]
    DATE_PATTERNS = [
        r'дата', r'date', r'период', r'месяц', r'год', r'год',
        r'день', r'day', r'month', r'year', r'period',
    ]
    ID_PATTERNS = [
        r'№', r'номер', r'id', r'код', r'артикул', r'sku',
        r'п/п', r'number',
    ]

    @staticmethod
    def normalize_value(value: Any, col_type: Optional[str] = None) -> Any:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return value

        if isinstance(value, str):
            value = value.strip()
            value = re.sub(r'\s+', ' ', value)

            if col_type in (COLUMN_TYPE_NUMBER, COLUMN_TYPE_PRICE):
                try:
                    cleaned = value.replace(' ', '').replace(',', '.')
                    return float(cleaned)
                except ValueError:
                    pass

        return value


    @staticmethod
    def infer_column_type(header: ParsedHeader, sample_values: List[Any]) -> str:
        full_name_lower = header.full_name.lower()

        for pattern in ExcelNormalizer.ID_PATTERNS:
            if re.search(pattern, full_name_lower):
                return COLUMN_TYPE_ID

        for pattern in ExcelNormalizer.PRICE_PATTERNS:
            if re.search(pattern, full_name_lower):
                return COLUMN_TYPE_PRICE

        for pattern in ExcelNormalizer.DATE_PATTERNS:
            if re.search(pattern, full_name_lower):
                return COLUMN_TYPE_DATE

        non_none_values = [v for v in sample_values if v is not None]
        if not non_none_values:
            return COLUMN_TYPE_TEXT

        all_numbers = all(isinstance(v, (int, float)) for v in non_none_values)
        if all_numbers:
            return COLUMN_TYPE_NUMBER

        for v in non_none_values:
            if isinstance(v, datetime):
                return COLUMN_TYPE_DATE
            if isinstance(v, str):
                for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%Y/%m/%d'):
                    try:
                        datetime.strptime(v.strip(), fmt)
                        return COLUMN_TYPE_DATE
                    except ValueError:
                        pass

        return COLUMN_TYPE_TEXT

    @staticmethod
    def extract_sample_values(data: List[Dict[str, Any]], col_name: str, max_samples: int = 5) -> List[Any]:
        seen = set()
        samples = []
        for row in data:
            val = row.get(col_name)
            if val is not None and val not in seen:
                seen.add(val)
                samples.append(val)
                if len(samples) >= max_samples:
                    break
        return samples


    @staticmethod
    def prepare_cell_for_db(value: Any, col_type: str) -> Dict[str, Any]:
        result = {
            "value_text": None,
            "value_number": None,
            "value_date": None,
            "original_value": str(value) if value is not None else None,
        }

        if value is None:
            return result

        if isinstance(value, datetime):
            result["value_date"] = value
            result["value_text"] = value.isoformat()
            return result

        if isinstance(value, (int, float)):
            result["value_number"] = float(value)
            result["value_text"] = str(value)
            return result

        if isinstance(value, str):
            result["value_text"] = value
            if col_type in (COLUMN_TYPE_NUMBER, COLUMN_TYPE_PRICE):
                try:
                    cleaned = value.replace(' ', '').replace(',', '.')
                    result["value_number"] = float(cleaned)
                except ValueError:
                    pass
            if col_type == COLUMN_TYPE_DATE:
                for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%Y/%m/%d'):
                    try:
                        result["value_date"] = datetime.strptime(value.strip(), fmt)
                        break
                    except ValueError:
                        pass
            return result

        result["value_text"] = str(value)
        return result


    @staticmethod
    def normalize_header(header: ParsedHeader) -> ParsedHeader:
        cleaned_levels = []
        for level in header.levels:
            if level:
                cleaned = ' '.join(level.split())
                cleaned_levels.append(cleaned)

        full_name = ' > '.join(cleaned_levels) if cleaned_levels else header.full_name

        return ParsedHeader(
            levels=cleaned_levels,
            full_name=full_name,
            col_index=header.col_index,
            col_name=header.col_name,
        )


    @staticmethod
    def flatten_sheet(sheet: ParsedSheet) -> List[Dict[str, Any]]:
        result = []
        for row in sheet.data:
            flat_row = {}
            for key, value in row.items():
                if value is not None:
                    flat_row[key] = ExcelNormalizer.normalize_value(value)
            if flat_row:
                result.append(flat_row)
        return result