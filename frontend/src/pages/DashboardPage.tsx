import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { FileText, Files, CheckCircle2, AlertCircle, Clock, Database, Activity, BarChart3 } from 'lucide-react';
import api from '@/api';
import type { FileResponse } from '@/types/api';
import { useToast } from '@/hooks/useToast';
import { ToastContainer } from '@/components/ui/Toast';

interface StatCardProps {
  title: string;
  value: string | number;
  icon: typeof FileText;
  accent: 'red' | 'gold' | 'cyan' | 'green';
}

function StatCard({ title, value, icon: Icon, accent }: StatCardProps) {
  return (
    <motion.div
      className={`stat-card stat-card--${accent}`}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -4 }}
      transition={{ duration: 0.3 }}
    >
      <div className="stat-card__icon">
        <Icon size={24} />
      </div>
      <div className="stat-card__value">{value}</div>
      <div className="stat-card__title">{title}</div>
    </motion.div>
  );
}

export default function DashboardPage() {
  const { toasts, showToast, dismiss } = useToast();
  const [files, setFiles] = useState<FileResponse[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listFiles({ limit: 1000 });
      setFiles(data.files || []);
    } catch (err) {
      showToast(`Ошибка загрузки: ${(err as Error).message}`, 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    load();
  }, [load]);

  const totalFiles = files.length;
  const totalSheets = files.reduce((acc, f) => acc + (f.total_sheets || 0), 0);
  const totalRows = files.reduce((acc, f) => acc + (f.total_rows || 0), 0);
  const totalCells = files.reduce((acc, f) => acc + (f.total_cells || 0), 0);
  const processed = files.filter((f) => f.status === 'processed').length;
  const errors = files.filter((f) => f.status === 'error').length;
  const pending = files.filter((f) => f.status !== 'processed' && f.status !== 'error').length;

  const statusCount = [
    { label: 'Обработанные', value: processed, color: 'var(--color-success)', icon: CheckCircle2 },
    { label: 'В обработке', value: pending, color: 'var(--color-warning)', icon: Clock },
    { label: 'С ошибками', value: errors, color: 'var(--color-error)', icon: AlertCircle },
  ];

  const total = Math.max(processed + pending + errors, 1);

  return (
    <div className="dashboard">
      <motion.div
        className="dashboard__header"
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h2 className="dashboard__title">
          <BarChart3 size={26} style={{ verticalAlign: 'middle', marginRight: 8 }} />
          Дашборд
        </h2>
        <span className="dashboard__subtitle">Сводка по загруженным данным</span>
      </motion.div>

      <div className="dashboard__stats">
        <StatCard title="Файлов загружено" value={totalFiles} icon={Files} accent="red" />
        <StatCard title="Листов" value={totalSheets} icon={FileText} accent="gold" />
        <StatCard title="Строк данных" value={totalRows.toLocaleString('ru-RU')} icon={Database} accent="cyan" />
        <StatCard title="Ячеек" value={totalCells.toLocaleString('ru-RU')} icon={Activity} accent="green" />
      </div>

      <div className="dashboard__row">
        <motion.div
          className="panel dashboard__panel"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <h3 className="dashboard__panel-title">Статусы файлов</h3>
          {loading ? (
            <div className="modal-loading">Загружаем данные...</div>
          ) : (
            <div className="status-bars">
              {statusCount.map(({ label, value, color }) => (
                <div className="status-bar" key={label}>
                  <div className="status-bar__row">
                    <span className="status-bar__label">{label}</span>
                    <span className="status-bar__value">{value}</span>
                  </div>
                  <div className="status-bar__track">
                    <motion.div
                      className="status-bar__fill"
                      style={{ background: color }}
                      initial={{ width: 0 }}
                      animate={{ width: `${(value / total) * 100}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </motion.div>

        <motion.div
          className="panel dashboard__panel"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <h3 className="dashboard__panel-title">Последние файлы</h3>
          {loading ? (
            <div className="modal-loading">Загружаем данные...</div>
          ) : files.length === 0 ? (
            <div className="dashboard__empty">Файлы ещё не загружены</div>
          ) : (
            <div className="recent-files">
              {files.slice(0, 8).map((f, i) => (
                <motion.div
                  key={f.id}
                  className="recent-file"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.05 }}
                >
                  <FileText size={16} className="recent-file__icon" />
                  <span className="recent-file__name">{f.filename}</span>
                  <span className="recent-file__sheets">{f.total_sheets} листов</span>
                </motion.div>
              ))}
            </div>
          )}
        </motion.div>
      </div>

      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}