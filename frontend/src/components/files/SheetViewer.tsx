import { useCallback, useEffect, useMemo, useState } from 'react';
import { getSheetCells, getSheetDetail } from '@/api';
import type { CellResponse, ColumnResponse } from '@/types/api';
import { columnName } from '@/lib/sheet';
import Modal from '@/components/ui/Modal';
import EmptyState from '@/components/ui/EmptyState';
import { ChevronLeft, ChevronRight, Download, Search, Rows3, Columns3 } from 'lucide-react';
import { formatMs } from '@/lib/utils';

interface SheetViewerProps {
  fileId: number;
  sheetId: number;
  sheetName: string;
  open: boolean;
  onClose: () => void;
}

const PAGE_SIZE = 50;

export default function SheetViewer({ fileId, sheetId, sheetName, open, onClose }: SheetViewerProps) {
  const [columns, setColumns] = useState<ColumnResponse[]>([]);
  const [allCells, setAllCells] = useState<CellResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [totalRows, setTotalRows] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setPage(0);
    setSearch('');
    try {
      const [detail, cellData] = await Promise.all([
        getSheetDetail(fileId, sheetId),
        getSheetCells(fileId, sheetId, { limit: 10000 }),
      ]);
      setColumns(detail.columns || []);
      setAllCells(cellData || []);
      const rows = new Set((cellData || []).map((c) => c.row_num));
      setTotalRows(rows.size);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [fileId, sheetId]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  // Группируем ячейки по строкам
  const rowsMap = useMemo(() => {
    const map: Record<number, Record<number, string>> = {};
    allCells.forEach((cell) => {
      if (!map[cell.row_num]) map[cell.row_num] = {};
      const value =
        cell.value_text ??
        (cell.value_number !== null && cell.value_number !== undefined ? String(cell.value_number) : cell.original_value ?? '');
      map[cell.row_num][cell.col_index] = value;
    });
    return map;
  }, [allCells]);

  const rowNums = useMemo(() => Object.keys(rowsMap).map(Number).sort((a, b) => a - b), [rowsMap]);

  // Поиск по всем ячейкам
  const filteredRowNums = useMemo(() => {
    if (!search.trim()) return rowNums;
    const q = search.trim().toLowerCase();
    return rowNums.filter((rn) =>
      columns.some((col) => (rowsMap[rn]?.[col.col_index] ?? '').toLowerCase().includes(q))
    );
  }, [rowNums, rowsMap, columns, search]);

  const pageCount = Math.max(1, Math.ceil(filteredRowNums.length / PAGE_SIZE));
  const pageRows = filteredRowNums.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  useEffect(() => {
    if (page >= pageCount && pageCount > 0) setPage(0);
  }, [page, pageCount]);

  const exportCsv = () => {
    const header = columns.map(columnName).join(';');
    const lines = filteredRowNums.map((rn) =>
      columns.map((col) => (rowsMap[rn]?.[col.col_index] ?? '').replace(/;/g, ',')).join(';')
    );
    const csv = [header, ...lines].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${sheetName}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Modal
      open={open}
      title={
        <span className="sheet-modal-title">
          <Rows3 size={18} /> {sheetName}
          <span className="sheet-modal-title__dim">{filteredRowNums.length} строк · {columns.length} колонок</span>
        </span>
      }
      onClose={onClose}
    >
      {loading ? (
        <div className="modal-loading">Загружаем данные листа...</div>
      ) : columns.length === 0 || filteredRowNums.length === 0 ? (
        <EmptyState icon={<Search size={40} />} text={search ? 'Ничего не найдено' : 'Нет данных для отображения'} />
      ) : (
        <div className="sheet-viewer">
          <div className="sheet-viewer__toolbar">
            <div className="sheet-viewer__search">
              <Search size={14} />
              <input
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
                placeholder="Поиск по данным..."
              />
            </div>
            <div className="sheet-viewer__counts">
              <span title="Строк">
                <Rows3 size={13} /> {totalRows}
              </span>
              <span title="Колонок">
                <Columns3 size={13} /> {columns.length}
              </span>
            </div>
            <button className="btn btn--sm btn--ghost" onClick={exportCsv} title="Экспорт CSV">
              <Download size={14} /> CSV
            </button>
          </div>

          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th key={col.id}>
                      <div className="data-table__th">
                        <span>{columnName(col)}</span>
                        <span className={`data-table__type data-table__type--${col.data_type.toLowerCase()}`}>
                          {col.data_type}
                        </span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pageRows.map((rowNum) => (
                  <tr key={rowNum}>
                    {columns.map((col) => (
                      <td key={col.id}>{rowsMap[rowNum]?.[col.col_index] ?? ''}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="sheet-viewer__footer">
            <div className="sheet-viewer__pagination">
              <button
                className="btn btn--sm btn--ghost"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft size={14} />
              </button>
              <span className="sheet-viewer__page">
                {filteredRowNums.length === 0 ? 0 : page + 1} / {pageCount}
              </span>
              <button
                className="btn btn--sm btn--ghost"
                disabled={page >= pageCount - 1}
                onClick={() => setPage((p) => p + 1)}
              >
                <ChevronRight size={14} />
              </button>
            </div>
            <div className="sheet-viewer__loadtime">загрузка {formatMs(0)}</div>
          </div>
        </div>
      )}
    </Modal>
  );
}