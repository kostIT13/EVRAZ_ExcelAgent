import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  Check,
  ClipboardCopy,
  Clock,
  Download,
  FileJson2,
  Gauge,
  Hash,
  Layers,
  MessageSquare,
  RefreshCw,
  RotateCcw,
  Search,
  SearchX,
  Timer,
} from 'lucide-react';
import api from '@/api';
import type { TraceListItem, TraceResponse, TraceStepInfo } from '@/types/api';
import { useToast } from '@/hooks/useToast';
import { ToastContainer } from '@/components/ui/Toast';
import EmptyState from '@/components/ui/EmptyState';
import TraceWaterfall, { STEP_COLORS } from '@/components/trace/TraceWaterfall';
import StepInspector from '@/components/trace/StepInspector';
import SqlBlock from '@/components/chat/SqlBlock';
import { confidenceLabel, formatDate, formatMs } from '@/lib/utils';

const QUERY_TYPE_LABELS: Record<string, string> = {
  lookup: 'поиск значения',
  aggregate: 'агрегат',
  cross_sheet: 'сквозной по листам',
  delta: 'дельта',
  sum_by_supplier: 'сумма по поставщику',
  find_period: 'поиск периода',
  unknown: 'тип не определён',
};

const PAGE_SIZE = 20;

const PERIODS: { value: number; label: string }[] = [
  { value: 1, label: 'За час' },
  { value: 24, label: 'За сутки' },
  { value: 168, label: 'За неделю' },
  { value: 0, label: 'За всё время' },
];

const stepData = (step: TraceStepInfo) => (step.data as Record<string, unknown>) || {};
const stepLabel = (step: TraceStepInfo) => (stepData(step).label as string) || step.step || '';
const stepDuration = (step: TraceStepInfo) =>
  Number((stepData(step).duration_ms as number) || 0);
const stepErrorText = (step: TraceStepInfo) =>
  typeof stepData(step).error === 'string' ? (stepData(step).error as string).trim() : '';

export default function TracePage() {
  const { toasts, showToast, dismiss } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [requestId, setRequestId] = useState(searchParams.get('request_id') || '');
  const [history, setHistory] = useState<TraceListItem[]>([]);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [stepQuery, setStepQuery] = useState('');
  const [stepFilter, setStepFilter] = useState<'all' | 'ok' | 'error'>('all');
  const [copiedTrace, setCopiedTrace] = useState(false);

  const [query, setQuery] = useState('');
  const [appliedQuery, setAppliedQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [hours, setHours] = useState(24);
  const [total, setTotal] = useState(0);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const steps = trace?.steps || [];
  const stepsTotalMs = steps.reduce((acc, s) => acc + stepDuration(s), 0);
  const stepsCoveredPct =
    stepsTotalMs > 0 && trace?.latency_ms ? Math.round((stepsTotalMs / trace.latency_ms) * 100) : 0;
  const activeStep = activeIndex != null ? steps[activeIndex] ?? null : null;

  const filteredSteps = useMemo(() => {
    const q = stepQuery.trim().toLowerCase();
    return steps
      .map((s, i) => ({ s, i }))
      .filter(({ s }) => {
        if (q) {
          const hay = `${stepLabel(s)} ${s.step} ${JSON.stringify(s.data)}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }
        if (stepFilter === 'error' && !stepErrorText(s)) return false;
        if (stepFilter === 'ok' && stepErrorText(s)) return false;
        return true;
      });
  }, [steps, stepQuery, stepFilter]);

  const loadHistory = useCallback(async (offset = 0) => {
    setLoadingHistory(true);
    try {
      const data = await api.listTraces({
        limit: PAGE_SIZE,
        offset,
        q: appliedQuery || undefined,
        status: statusFilter || undefined,
        since: hours > 0 ? new Date(Date.now() - hours * 3600_000).toISOString() : undefined,
      });
      const items = data?.items ?? [];
      setHistory((prev) => (offset === 0 ? items : [...prev, ...items]));
      setTotal(data?.total ?? 0);
    } catch (err) {
      showToast(`Ошибка загрузки истории: ${(err as Error).message}`, 'error');
    } finally {
      setLoadingHistory(false);
    }
  }, [appliedQuery, statusFilter, hours, showToast]);

  useEffect(() => {
    loadHistory(0);
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
    setActiveIndex(null);
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

  const copyTraceJson = async () => {
    if (!trace) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(trace, null, 2));
      setCopiedTrace(true);
      setTimeout(() => setCopiedTrace(false), 1600);
    } catch {
      showToast('Не удалось скопировать', 'error');
    }
  };

  const downloadTraceJson = () => {
    if (!trace) return;
    const blob = new Blob([JSON.stringify(trace, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${trace.request_id}.trace.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const selectStep = (index: number) => {
    setActiveIndex((prev) => (prev === index ? null : index));
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
          <button className="btn btn--ghost" onClick={() => loadHistory(0)} title="Обновить историю">
            <RefreshCw size={16} />
          </button>
        </div>

        <div className="trace-filters">
          <input
            className="chat-input__field"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') setAppliedQuery(query.trim());
            }}
            placeholder="Поиск по тексту вопроса"
          />
          <div className="trace-filters__row">
            <select
              className="trace-filters__select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">Любой статус</option>
              <option value="success">success</option>
              <option value="low_confidence">low_confidence</option>
              <option value="failed">failed</option>
            </select>
            <select
              className="trace-filters__select"
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            >
              {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="trace-history">
          <div className="trace-history__header">
            <span>История запросов</span>
            <span className="trace-history__count">{history.length} из {total}</span>
          </div>
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
                    <span className="trace-history__meta">
                      {formatMs(t.latency_ms)}
                      {!!t.confidence && ` · ${Math.round(t.confidence * 100)}%`}
                    </span>
                    <span className="trace-history__time">
                      {t.created_at ? formatDate(t.created_at) : ''}
                    </span>
                  </motion.div>
                );
              })
            )}
          </div>

          {history.length < total && (
            <button
              className="btn btn--ghost trace-history__more"
              onClick={() => loadHistory(history.length)}
              disabled={loadingHistory}
            >
              <RefreshCw size={14} className={loadingHistory ? 'spin' : undefined} />
              Показать ещё ({total - history.length})
            </button>
          )}
        </div>
      </aside>

      <section className="panel panel--trace">
        {loading ? (
          <EmptyState icon={<Clock className="spin" size={40} />} text="Загружаем трассировку..." />
        ) : !trace ? (
          <EmptyState icon={<Search size={40} />} text="Выберите запрос из истории или введите request_id" />
        ) : (
          <div className="trace-detail">
            <div className="trace-detail__topbar">
              <div className="trace-detail__head">
                <span className="trace-detail__q">
                  <MessageSquare size={13} />
                  {trace.question}
                </span>
                <span className="trace-detail__rid">
                  <Hash size={12} /> {trace.request_id}
                </span>
              </div>
              <div className="trace-detail__actions">
                <button className="btn btn--ghost" onClick={() => loadTraceDetail(trace.request_id)} title="Обновить трассировку">
                  <RefreshCw size={14} />
                </button>
                <button className="btn btn--ghost" onClick={copyTraceJson} title="Скопировать JSON трассировки">
                  {copiedTrace ? <Check size={14} className="trace-detail__ok" /> : <ClipboardCopy size={14} />}
                  {copiedTrace ? 'Скопировано' : 'JSON'}
                </button>
                <button className="btn btn--ghost" onClick={downloadTraceJson} title="Скачать JSON трассировки">
                  <Download size={14} /> .json
                </button>
              </div>
            </div>

            <div className="trace-detail__statusline">
              Статус:{' '}
              <strong style={{ color: trace.status === 'success' ? 'var(--color-success)' : 'var(--color-error)' }}>
                {trace.status || '?'}
              </strong>
              {trace.created_at && (
                <span className="trace-detail__when">
                  <Clock size={12} /> {formatDate(trace.created_at)}
                </span>
              )}
            </div>

            {trace.error_message && (
              <div className="trace-error">
                <AlertTriangle size={16} />
                <span>{trace.error_message}</span>
              </div>
            )}

            <div className="trace-kpis">
              <div className="trace-kpi trace-kpi--status">
                <span className="trace-kpi__label">Статус</span>
                <span className={`trace-kpi__value trace-kpi__value--${trace.status === 'success' ? 'ok' : trace.status === 'low_confidence' ? 'warn' : 'bad'}`}>
                  {trace.status || '?'}
                </span>
              </div>
              <div className="trace-kpi">
                <span className="trace-kpi__label">Латентность</span>
                <span className="trace-kpi__value"><Timer size={13} /> {formatMs(trace.latency_ms)}</span>
              </div>
              <div className="trace-kpi">
                <span className="trace-kpi__label">Шагов агента</span>
                <span className="trace-kpi__value"><Layers size={13} /> {steps.length}</span>
              </div>
              <div className="trace-kpi">
                <span className="trace-kpi__label">Уверенность</span>
                <span className={`trace-kpi__value trace-kpi__value--${confidenceLabel(trace.confidence || 0).cls}`}>
                  <Gauge size={13} /> {((trace.confidence || 0) * 100).toFixed(0)}%
                </span>
              </div>
              {trace.query_type && (
                <div className="trace-kpi">
                  <span className="trace-kpi__label">Тип запроса</span>
                  <span className="trace-kpi__value">{QUERY_TYPE_LABELS[trace.query_type] || trace.query_type}</span>
                </div>
              )}
              {!!trace.retry_count && (
                <div className="trace-kpi">
                  <span className="trace-kpi__label">Повторы</span>
                  <span className="trace-kpi__value"><RotateCcw size={13} /> {trace.retry_count}</span>
                </div>
              )}
              {trace.from_cache && (
                <div className="trace-kpi">
                  <span className="trace-kpi__label">Кэш</span>
                  <span className="trace-kpi__value trace-kpi__value--ok"><Clock size={13} /> из кэша</span>
                </div>
              )}
              {stepsTotalMs > 0 && trace?.latency_ms ? (
                <div className="trace-kpi">
                  <span className="trace-kpi__label">Покрытие шагами</span>
                  <span className="trace-kpi__value">
                    {stepsCoveredPct}%
                    <em className="trace-kpi__hint">({formatMs(stepsTotalMs)})</em>
                  </span>
                </div>
              ) : null}
            </div>

            {trace.answer && <div className="trace-detail__answer">{trace.answer}</div>}

            {steps.length > 0 && (
              <div className="trace-toolbar">
                <div className="trace-toolbar__search">
                  <Search size={13} />
                  <input
                    type="text"
                    value={stepQuery}
                    onChange={(e) => setStepQuery(e.target.value)}
                    placeholder="Поиск по шагам..."
                  />
                </div>
                <div className="trace-toolbar__filters">
                  <select
                    className="trace-filters__select"
                    value={stepFilter}
                    onChange={(e) => setStepFilter(e.target.value as 'all' | 'ok' | 'error')}
                  >
                    <option value="all">Все шаги ({steps.length})</option>
                    <option value="error">С ошибкой</option>
                    <option value="ok">Без ошибок</option>
                  </select>
                  <span className="trace-toolbar__count">
                    показано {filteredSteps.length}
                  </span>
                </div>
              </div>
            )}

            {steps.length > 1 && (trace.latency_ms > 0 || stepsTotalMs > 0) && (
              <div className="twc-wrap">
                <div className="twc-wrap__title">
                  <Timer size={12} /> Водопад шагов по времени
                  {trace?.latency_ms ? (
                    <span className="twc-wrap__sub">
                      {formatMs(stepsTotalMs)} из {formatMs(trace.latency_ms)} · остальное — вне узлов графа
                    </span>
                  ) : null}
                </div>
                <TraceWaterfall steps={steps} totalMs={trace?.latency_ms || 0} activeIndex={activeIndex} onSelect={selectStep} />
              </div>
            )}

            <div className="trace-body">
              <div className="trace-steps">
                {filteredSteps.length === 0 ? (
                  <div className="trace-steps__empty">
                    <SearchX size={22} />
                    Ничего не найдено
                  </div>
                ) : (
                  filteredSteps.map(({ s, i }) => {
                    const label = stepLabel(s);
                    const duration = stepDuration(s);
                    const error = stepErrorText(s);
                    const color = STEP_COLORS[s.step] || '#8a97a6';
                    const isActive = activeIndex === i;
                    return (
                      <motion.button
                        key={i}
                        className={`trace-step-row${isActive ? ' trace-step-row--active' : ''}${error ? ' trace-step-row--error' : ''}`}
                        onClick={() => selectStep(i)}
                        initial={{ opacity: 0, x: -6 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: Math.min(i * 0.02, 0.3) }}
                      >
                        <span className="trace-step-row__dot" style={{ background: color }} />
                        <span className="trace-step-row__num">#{i + 1}</span>
                        <span className="trace-step-row__label">{label}</span>
                        {error ? (
                          <span className="trace-step-row__err" title={error}>
                            <AlertTriangle size={12} />
                          </span>
                        ) : null}
                        <span className="trace-step-row__time">
                          {duration > 0 ? `${formatMs(duration)} · ${Math.round((duration / Math.max(stepsTotalMs, 1)) * 100)}%` : '—'}
                        </span>
                        <span className="trace-step-row__chev">
                          {isActive ? <SearchX size={13} /> : <Layers size={13} />}
                        </span>
                      </motion.button>
                    );
                  })
                )}
              </div>

              <StepInspector
                step={activeStep}
                index={activeIndex ?? 0}
                totalMs={trace?.latency_ms || 0}
                onClose={() => setActiveIndex(null)}
              />
            </div>

            {trace.sql_query && (
              <div className="trace-detail__sql">
                <div className="trace-detail__sql-title">
                  <FileJson2 size={12} /> Выполненный SQL
                </div>
                <SqlBlock sql={trace.sql_query} onCopy={() => showToast('SQL скопирован', 'success')} />
              </div>
            )}
          </div>
        )}
      </section>

      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}