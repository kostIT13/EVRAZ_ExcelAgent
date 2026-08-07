import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Search, RefreshCw, Clock, Hash, MessageSquare, Timer } from 'lucide-react';
import api from '@/api';
import type { TraceListItem, TraceResponse } from '@/types/api';
import { useToast } from '@/hooks/useToast';
import { ToastContainer } from '@/components/ui/Toast';
import EmptyState from '@/components/ui/EmptyState';
import TraceStepCard from '@/components/trace/TraceStepCard';
import { formatDate, formatMs } from '@/lib/utils';

export default function TracePage() {
  const { toasts, showToast, dismiss } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [requestId, setRequestId] = useState(searchParams.get('request_id') || '');
  const [history, setHistory] = useState<TraceListItem[]>([]);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadHistory = useCallback(async () => {
    try {
      const traces = await api.listTraces({ limit: 20 });
      setHistory(Array.isArray(traces) ? traces : []);
    } catch (err) {
      showToast(`Ошибка загрузки истории: ${(err as Error).message}`, 'error');
    }
  }, [showToast]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    const rid = searchParams.get('request_id');
    if (rid) {
      setRequestId(rid);
      loadTraceDetail(rid);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadTraceDetail = async (rid: string) => {
    if (!rid) return;
    setLoading(true);
    try {
      const t = await api.getTrace(rid);
      setTrace(t);
    } catch (err) {
      showToast(`Ошибка: ${(err as Error).message}`, 'error');
      setTrace(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    if (!requestId.trim()) return;
    setSearchParams({ request_id: requestId.trim() });
    loadTraceDetail(requestId.trim());
  };

  return (
    <div className="layout" style={{ gridTemplateColumns: '320px 1fr' }}>
      <aside className="panel panel--trace-side">
        <div className="trace-search">
          <input
            className="chat-input__field"
            type="text"
            value={requestId}
            onChange={(e) => setRequestId(e.target.value)}
            placeholder="Введите request_id..."
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSearch();
            }}
          />
          <button className="btn btn--primary" onClick={handleSearch}>
            <Search size={16} />
          </button>
          <button className="btn btn--ghost" onClick={loadHistory} title="Обновить историю">
            <RefreshCw size={16} />
          </button>
        </div>

        <div className="trace-history">
          <div className="trace-history__header">История запросов</div>
          <div className="trace-history__list">
            {history.length === 0 ? (
              <div className="trace-history__empty">История пуста</div>
            ) : (
              history.map((t) => {
                const statusClass =
                  t.status === 'success' ? 'success' : t.status === 'low_confidence' ? 'low_confidence' : 'failed';
                return (
                  <motion.div
                    key={t.request_id}
                    className="trace-history__item"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    onClick={() => {
                      setRequestId(t.request_id);
                      loadTraceDetail(t.request_id);
                    }}
                  >
                    <MessageSquare size={13} className="trace-history__qicon" />
                    <span className="trace-history__question">
                      {(t.question || t.request_id).slice(0, 60)}
                    </span>
                    <span className={`trace-history__status trace-history__status--${statusClass}`}>
                      {t.status || '?'}
                    </span>
                    <span className="trace-history__time">
                      {t.created_at ? formatDate(t.created_at) : ''}
                    </span>
                  </motion.div>
                );
              })
            )}
          </div>
        </div>
      </aside>

      <section className="panel panel--trace">
        {loading ? (
          <EmptyState icon={<Clock className="spin" size={40} />} text="Загружаем трассировку..." />
        ) : !trace ? (
          <EmptyState icon={<Search size={40} />} text="Выберите запрос из истории или введите request_id" />
        ) : (
          <div className="trace-detail">
            <div className="trace-detail__header">
              <span className="details-meta__item">
                <Hash size={12} /> {trace.request_id}
              </span>
              <span className="details-meta__item">
                <MessageSquare size={12} /> {trace.question}
              </span>
              <span className="details-meta__item">
                <Timer size={12} /> {formatMs(trace.latency_ms)}
              </span>
            </div>

            <div className="trace-detail__status">
              Статус:{' '}
              <strong style={{ color: trace.status === 'success' ? 'var(--color-success)' : 'var(--color-error)' }}>
                {trace.status || '?'}
              </strong>
            </div>

            {trace.answer && <div className="trace-detail__answer">{trace.answer}</div>}

            <div className="trace-steps">
              {(trace.steps || []).map((step, i) => (
                <TraceStepCard key={i} step={step} index={i} />
              ))}
            </div>
          </div>
        )}
      </section>

      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}