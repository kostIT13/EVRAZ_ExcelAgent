import { motion, AnimatePresence } from 'framer-motion';
import { FileText, RefreshCw, Trash2, CheckCircle2, AlertCircle, Clock, FolderOpen } from 'lucide-react';
import type { FileResponse } from '@/types/api';
import { formatDate } from '@/lib/utils';

interface FileListProps {
  files: FileResponse[];
  selectedId?: number | null;
  loading?: boolean;
  onSelect: (file: FileResponse) => void;
  onDelete: (fileId: number) => void;
  onRefresh?: () => void;
}

function statusIcon(status: string) {
  if (status === 'processed') return <CheckCircle2 size={14} className="file-item__status-icon ok" />;
  if (status === 'error') return <AlertCircle size={14} className="file-item__status-icon err" />;
  return <Clock size={14} className="file-item__status-icon pending" />;
}

export default function FileList({ files, selectedId, loading, onSelect, onDelete, onRefresh }: FileListProps) {
  return (
    <div className="file-list">
      <div className="file-list__header">
        <span>
          <FolderOpen size={15} style={{ verticalAlign: 'middle', marginRight: 6 }} />
          Файлы данных
        </span>
        {onRefresh && (
          <button className="btn btn--sm btn--ghost" onClick={onRefresh} title="Обновить список">
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
        )}
      </div>

      {files.length === 0 ? (
        <div className="file-list__empty">Файлы не загружены</div>
      ) : (
        <AnimatePresence>
          {files.map((f) => (
            <motion.div
              key={f.id}
              className={`file-item${f.id === selectedId ? ' file-item--active' : ''}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25 }}
              onClick={() => onSelect(f)}
            >
              <FileText size={18} className="file-item__icon" />
              <div className="file-item__info">
                <div className="file-item__name">{f.filename}</div>
                <div className="file-item__meta">
                  {f.total_sheets} листов • {formatDate(f.uploaded_at)}
                </div>
              </div>
              {statusIcon(f.status)}
              <button
                className="file-item__delete"
                title="Удалить"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(f.id);
                }}
              >
                <Trash2 size={14} />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      )}
    </div>
  );
}