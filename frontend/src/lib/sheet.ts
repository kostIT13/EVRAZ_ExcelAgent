import type { CellResponse, ColumnResponse } from '@/types/api';

export type SheetDataRow = Record<number, string>;

export interface ParsedSheetData {
  columns: ColumnResponse[];
  rows: Record<number, SheetDataRow>;
  rowNums: number[];
  cells: CellResponse[];
}

export function parseSheetCells(cells: CellResponse[], columns: ColumnResponse[]): ParsedSheetData {
  const rowsMap: Record<number, Record<number, string>> = {};
  cells.forEach((cell) => {
    if (!rowsMap[cell.row_num]) {
      rowsMap[cell.row_num] = {};
    }
    const value =
      cell.value_text ?? (cell.value_number !== null && cell.value_number !== undefined ? String(cell.value_number) : cell.original_value ?? '');
    rowsMap[cell.row_num][cell.col_index] = value;
  });

  const rowNums = Object.keys(rowsMap)
    .map(Number)
    .sort((a, b) => a - b);

  return { columns, rows: rowsMap, rowNums, cells };
}

export function columnName(col: ColumnResponse): string {
  return col.original_name || col.normalized_name || `Колонка ${col.col_index}`;
}