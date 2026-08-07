import { useCallback, useEffect, useState } from 'react';
import {
  BarChart3,
  CheckCircle2,
  Clock,
  AlertCircle,
  Eye,
  FileText,
  Inbox,
  ChevronDown,
  Search,
  Loader2,
} from 'lucide-react';
import api from '@/api';
import type { ColumnResponse, FileDetailResponse, FileResponse, SheetResponse } from '@/types/api';
import { useToast } from '@/hooks/useToast';
import { ToastContainer } from '@/components/ui/Toast';
import FileList from '@/components/files/FileList';
import FileUpload from '@/components/files/FileUpload';
import SheetViewer from '@/components/files/SheetViewer';
import EmptyState from '@/components/ui/EmptyState';
import { columnName } from '@/lib/sheet';
import { formatDate } from '@/lib/utils';

const TYPE_ICONS: Record<string, string> = {
  number: '#',
  text: 'Aa',
  date: '📅',
  datetime: '🕒',
  bool: '☑',
};

export default function FilesPage() {
  const { toasts, showToast, dismiss } = useToast();
  const [files, setFiles] = useState<FileResponse[]>([]);
  const [detail, setDetail] = useState<FileDetailResponse | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [viewer, setViewer] = useState<{ fileId: number; sheetId: number; name: string } | null>(null);
  const [expandedSheet, setExpandedSheet] = useState<number | null>(null);

  const loadFiles = useCallback(async () => {
    try {
      const data = await api.listFiles({ limit: 100 });
      setFiles(data.files || []);
    } catch (err) {
      showToast(`Ошибка загрузки файлов: ${(err as Error).message}`, 'error');
    }
  }, [showToast]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const loadDetail = useCallback(async (fileId: number) => {
    try {
      const d = await api.getFile(fileId);
      setDetail(d);
      setExpandedSheet(null);
    } catch (err) {
      showToast(`Ошибка загрузки деталей: ${(err as Error).message}`, 'error');
    }
  }, [showToast]);

  const handleSelect = (file: FileResponse) => {
    setSelectedId(file.id);
    loadDetail(file.id);
  };

  const handleDelete = async (fileId: number) => {
    if (!window.confirm('Удалить файл?')) return;
    try {
      await api.deleteFile(fileId);
      showToast('Файл удалён', 'success');
      if (selectedId === fileId) {
        setSelectedId(null);
        setDetail(null);
      }
      loadFiles();
    } catch (err) {
      showToast(`Ошибка удаления: ${(err as Error).message}`, 'error');
    }
  };

  const handleUpload = async (file: File) => {
    try {
      await api.uploadFile(file);
      showToast('Файл загружен успешно', 'success');
      loadFiles();
    } catch (err) {
      showToast(`Ошибка загрузки: ${(err as Error).message}`, 'error');
    }
  };

  const sheets = (detail?.sheets ?? []) as Array<SheetResponse & { columns?: ColumnResponse[] }>;

  return (
    <div className="layout" style={{ gridTemplateColumns: '320px 1fr' }}>
      <aside className="panel panel--files">
        <FileUpload onUpload={handleUpload} compact />
        <FileList
          files={files}
          selectedId={selectedId}
          onSelect={handleSelect}
          onDelete={handleDelete}
          onRefresh={loadFiles}
        />
      </aside>

      <section className="panel panel--details">
        {!detail ? (
          <EmptyState icon={<Inbox size={40} />} text="Выберите файл для просмотра детальной информации" />
        ) : (
          <div className="details-content">
            <div className="details-header">
              <h3 className="details-header__title">
                <FileText size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
                {detail.filename}
              </h3>
              <div className="details-meta">
                <span className="details-meta__item">
                  <BarChart3 size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} /> {detail.total_sheets} листов
                </span>
                <span className="details-meta__item">
                  <Clock size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} /> {formatDate(detail.uploaded_at)}
                </span>
                <span className="details-meta__item">
                  {detail.status === 'processed' ? (
                    <><CheckCircle2 size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} /> Обработан</>
                  ) : detail.status === 'error' ? (
                    <><AlertCircle size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} /> Ошибка</>
                  ) : (
                    <><Loader2 size={12} className="spin" style={{ verticalAlign: 'middle', marginRight: 4 }} /> Обработка</>
                  )}
                </span>
              </div>
            </div>

            <div className="details-sheets">
              {sheets.length === 0 ? (
                <EmptyState icon={<Search size={32} />} text="Нет данных о листах" />
              ) : (
                sheets.map((sheet) => {
                  const isOpen = expandedSheet === sheet.id;
                  const cols = sheet.columns ?? [];
                  return (
                    <div key={sheet.id} className={`details-sheet${isOpen ? ' details-sheet--open' : ''}`}>
                      <button
                        className="details-sheet__header"
                        onClick={() => setExpandedSheet(isOpen ? null : sheet.id)}
                      >
                        <span className="details-sheet__header-left">
                          <FileText size={16} className="details-sheet__fileicon" />
                          <span className="details-sheet__name">{sheet.original_name || sheet.normalized_name}</span>
                        </span>
                        <span className="details-sheet__header-right">
                          <span className="details-sheet__badge">
                            <Rows3Icon /> {sheet.row_count}
                          </span>
                          <span className="details-sheet__badge">
                            <ColumnsIcon /> {sheet.col_count}
                          </span>
                          <ChevronDown
                            size={16}
                            className={`details-sheet__chevron${isOpen ? ' details-sheet__chevron--open' : ''}`}
                          />
                        </span>
                      </button>

                      {isOpen && (
                        <div className="details-sheet__body">
                          {cols.length > 0 ? (
                            <div className="details-columns">
                              {cols.map((col) => (
                                <div className="details-column" key={col.id}>
                                  <span className="details-column__name">{columnName(col)}</span>
                                  <span className={`details-column__type details-column__type--${col.data_type.toLowerCase()}`}>
                                    <span className="details-column__type-badge">
                                      {TYPE_ICONS[col.data_type.toLowerCase()] ?? col.data_type.slice(0, 2)}
                                    </span>
                                    {col.data_type}
                                  </span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="details-sheet__no-columns">Информация о колонках отсутствует</div>
                          )}
                          <button
                            className="btn btn--sm btn--gold details-sheet__view-btn"
                            onClick={() =>
                              setViewer({ fileId: detail.id, sheetId: sheet.id, name: sheet.original_name })
                            }
                          >
                            <Eye size={14} /> Просмотр данных
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}
      </section>

      {viewer && (
        <SheetViewer
          fileId={viewer.fileId}
          sheetId={viewer.sheetId}
          sheetName={viewer.name}
          open={!!viewer}
          onClose={() => setViewer(null)}
        />
      )}
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}

function Rows3Icon() {
  return <span className="details-sheet__badge-icon">↕</span>;
}

function ColumnsIcon() {
  return <span className="details-sheet__badge-icon">↔</span>;
}