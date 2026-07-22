"""
Нормализация распарсенных данных: из широкой таблицы в длинную.
"""
from src.ingestion.parser import parse_excel
import pandas as pd
from typing import Any


def normalize(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """
    Превращает широкую таблицу вида:
    месяц | № | Наименование | Ферроком | Сплав-21 | ... | аукцион_старт | аукцион_победитель | по результатам аукциона
    
    В длинную:
    месяц | наименование | поставщик | цена | тип_цены
    """
    records = []
    
    name_col = 'Наименование лома'
    month_col = 'месяц'
    
    # Колонки поставщиков — все, кроме служебных
    skip_cols = {month_col, name_col, '№ п/п', 'ВРП У', 'северо-запад ВторМет * (921)341-19-36 (Алла)'}
    auction_cols = {'аукцион_старт', 'аукцион_победитель', 'по результатам аукциона'}
    
    supplier_cols = [c for c in df.columns if c not in skip_cols and c not in auction_cols]
    
    for _, row in df.iterrows():
        item_name = row.get(name_col)
        month = row.get(month_col)
        
        if pd.isna(item_name) or pd.isna(month):
            continue
        
        item_name = str(item_name).strip()
        month = str(month).strip()
        
        # Цены от поставщиков
        for supplier in supplier_cols:
            price = row.get(supplier)
            if pd.notna(price) and price != 0:
                records.append({
                    'месяц': month,
                    'наименование': item_name,
                    'поставщик': supplier,
                    'цена': float(price),
                    'тип_цены': 'рыночная'
                })
        
        # Цены аукциона
        for auction_type, col_name in [('аукцион_старт', 'аукцион_старт'), 
                                        ('аукцион_победитель', 'аукцион_победитель'),
                                        ('аукцион_результат', 'по результатам аукциона')]:
            price = row.get(col_name)
            if pd.notna(price) and price != 0:
                records.append({
                    'месяц': month,
                    'наименование': item_name,
                    'поставщик': 'аукцион',
                    'цена': float(price),
                    'тип_цены': auction_type
                })
    
    return pd.DataFrame(records)


def normalize_all(parsed_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Нормализует все листы и объединяет."""
    all_dfs = []
    for sheet_name, df in parsed_data.items():
        normalized = normalize(df, sheet_name)
        all_dfs.append(normalized)
    
    if all_dfs:
        return pd.concat(all_dfs, ignore_index=True)
    return pd.DataFrame()


if __name__ == '__main__':
    
    parsed = parse_excel('data/data_proportional_prices.xlsx')
    normalized = normalize_all(parsed)
    
    print(f'Всего записей: {len(normalized)}')
    print(f'Колонки: {list(normalized.columns)}')
    print(f'\nПервые 10 строк:')
    print(normalized.head(10).to_string())
    print(f'\nСтатистика по типам цен:')
    print(normalized['тип_цены'].value_counts())
    print(f'\nСтатистика по поставщикам:')
    print(normalized['поставщик'].value_counts())
