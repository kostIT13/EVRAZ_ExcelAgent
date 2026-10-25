import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity,
  BarChart3,
  Coins,
  Database,
  Gauge,
  Layers,
  Pause,
  Play,
  RefreshCw,
  ServerCrash,
  ShieldCheck,
  Timer,
  TrendingUp,
} from 'lucide-react';
import { Chart, registerables } from 'chart.js';
import { Chart as ChartJS } from 'chart.js';
import api from '@/api';
import type { MetricsHistory, MetricsSummary, NodeLatency } from '@/types/api';
import { CHART_COLORS } from '@/lib/utils';

Chart.register(...registerables);

// Палитра в стиле презентации EVRAZ / Grafana
const C_ORANGE = '#FF5A36';
const C_BLUE = '#2FA6C9';
const C_GREEN = '#3FBF8A';
const C_RED = '#E5484D';
const C_GOLD = '#E5B53D';
const C_GRAY = '#8A97A6';
const C_GRID = 'rgba(138,151,166,0.14)';

const PERIODS: { value: number; label: string }[] = [
  { value: 1, label: '1 час' },
  { value: 6, label: '6 часов' },
  { value: 24, label: '24 часа' },
  { value: 168, label: '7 дней' },
];

const NODE_LABELS: Record<string, string> = {
  classifier: 'Классификатор',
  disambiguation: 'Уточнение',
  planner: 'Планировщик',
  codegen: 'Генерация SQL',
  executor: 'Выполнение SQL',
  verifier: 'Верификатор',
  answer: 'Ответ',
  llm: 'LLM',
};

const fmt = (ms: number) => `${Math.round(ms).toLocaleString('ru-RU')} мс`;
const fmtPct = (v: number | undefined) => (v == null ? '—' : `${v.toFixed(1)} %`);
const fmtNum = (v: number | undefined) => (v == null ? '0' : v.toLocaleString('ru-RU'));
const hourLabels = (labels: string[]) =>
  labels.map((hh) => new Date(hh).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }));

interface StatCardProps {
  title: string;
  value: string;
  sub: string;
  icon: typeof Activity;
  accent: 'red' | 'gold' | 'cyan' | 'green' | 'blue';
  delay?: number;
}

function StatCard({ title, value, sub, icon: Icon, accent, delay = 0 }: StatCardProps) {
  return (
    <motion.div
      className={`stat-card stat-card--${accent}`}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -4 }}
      transition={{ duration: 0.3, delay }}
    >
      <div className="stat-card__icon">
        <Icon size={24} />
      </div>
      <div className="stat-card__value">{value}</div>
      <div className="stat-card__title">{title}</div>
      <div className="stat-card__sub">{sub}</div>
    </motion.div>
  );
}

interface PanelProps {
  title: string;
  now: string;
  wide?: boolean;
  children: React.ReactNode;
  delay?: number;
}

function Panel({ title, now, wide, children, delay = 0 }: PanelProps) {
  return (
    <motion.div
      className={`panel metrics__panel${wide ? ' metrics__panel--wide' : ''}`}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
    >
      <div className="metrics__panel-head">
        <h3 className="metrics__panel-title">{title}</h3>
        <span className="metrics__panel-now">{now}</span>
      </div>
      {children}
    </motion.div>
  );
}

export default function MetricsPage() {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [history, setHistory] = useState<MetricsHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState(24);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string>('');

  const latencyRef = useRef<HTMLCanvasElement>(null);
  const statusRef = useRef<HTMLCanvasElement>(null);
  const errorsRef = useRef<HTMLCanvasElement>(null);
  const rpsRef = useRef<HTMLCanvasElement>(null);
  const nodeLatRef = useRef<HTMLCanvasElement>(null);
  const tokensRef = useRef<HTMLCanvasElement>(null);
  const costRef = useRef<HTMLCanvasElement>(null);
  const statusAllRef = useRef<HTMLCanvasElement>(null);
  const accuracyRef = useRef<HTMLCanvasElement>(null);
  const charts = useRef<ChartJS[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, h] = await Promise.all([
        api.getMetricsSummary(),
        api.getMetricsHistory({ hours }),
      ]);
      setSummary(s);
      setHistory(h);
      setUpdatedAt(new Date().toLocaleTimeString('ru-RU'));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hours]);

  useEffect(() => {
    if (!autoRefresh) return;
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [autoRefresh, load]);

  useEffect(() => {
    return () => {
      charts.current.forEach((c) => c.destroy());
      charts.current = [];
    };
  }, []);

  const nowTrend = (arr: number[] | undefined) =>
    arr && arr.length ? Math.round((arr[arr.length - 1] ?? 0) * 10) / 10 : 0;
  const nowP95 = history?.latency_p95_ms ? `${nowTrend(history.latency_p95_ms)} мс` : '—';

  const problemsTotal =
    (summary?.requests_by_status?.failed || 0) + (summary?.requests_by_status?.low_confidence || 0);

  useEffect(() => {
    charts.current.forEach((c) => c.destroy());
    charts.current = [];

    // 1) Латентность по часам (p95 / p50 / средняя)
    const latC = latencyRef.current;
    if (latC && history) {
      const labels = hourLabels(history.labels);
      charts.current.push(new ChartJS(latC, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'p95', data: history.latency_p95_ms, borderColor: C_ORANGE,
              backgroundColor: 'rgba(255,90,54,0.18)', fill: true, tension: 0.35,
              borderWidth: 3, pointRadius: 0,
            },
            {
              label: 'p50', data: history.latency_p50_ms, borderColor: C_BLUE,
              backgroundColor: 'rgba(47,166,201,0.10)', fill: true, tension: 0.35,
              borderWidth: 2, pointRadius: 0,
            },
            {
              label: 'средняя', data: history.avg_latency_ms, borderColor: C_GRAY,
              borderDash: [5, 4], borderWidth: 1.5, tension: 0.35, pointRadius: 0,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: { legend: { labels: { color: '#E8EAF0', boxWidth: 12 } }, tooltip: { mode: 'index', intersect: false } },
          scales: {
            x: { ticks: { color: C_GRAY, maxTicksLimit: 12 }, grid: { color: C_GRID } },
            y: { ticks: { color: C_GRAY }, grid: { color: C_GRID }, title: { display: true, text: 'мс', color: C_GRAY } },
          },
        },
      }));
    }

    // 2) Запросы по статусам (стек-бар) по часам
    const stC = statusRef.current;
    if (stC && history) {
      const labels = hourLabels(history.labels);
      const bs = history.by_status || {};
      charts.current.push(new ChartJS(stC, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: 'успех', data: bs.success || [], backgroundColor: C_GREEN, borderRadius: 3 },
            { label: 'failed', data: bs.failed || [], backgroundColor: C_RED, borderRadius: 3 },
            { label: 'low_confidence', data: bs.low_confidence || [], backgroundColor: C_GOLD, borderRadius: 3 },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: { legend: { labels: { color: '#E8EAF0', boxWidth: 12 } }, tooltip: { mode: 'index', intersect: false } },
          scales: {
            x: { stacked: true, ticks: { color: C_GRAY, maxTicksLimit: 12 }, grid: { color: C_GRID } },
            y: { stacked: true, ticks: { color: C_GRAY }, grid: { color: C_GRID } },
          },
        },
      }));
    }

    // 3) Проблемные ответы по часам
    const errC = errorsRef.current;
    if (errC && history) {
      const labels = hourLabels(history.labels);
      const bs = history.by_status || {};
      const problems = history.labels.map((_, i) =>
        (bs.failed?.[i] || 0) + (bs.low_confidence?.[i] || 0));
      charts.current.push(new ChartJS(errC, {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: 'failed + low_confidence', data: problems, borderColor: C_RED,
            backgroundColor: 'rgba(229,72,77,0.16)', fill: true, tension: 0.35,
            borderWidth: 2, pointRadius: 0,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#E8EAF0', boxWidth: 12 } } },
          scales: {
            x: { ticks: { color: C_GRAY, maxTicksLimit: 12 }, grid: { color: C_GRID } },
            y: { beginAtZero: true, ticks: { color: C_GRAY }, grid: { color: C_GRID } },
          },
        },
      }));
    }

    // 4) Пропускная способность: запросов в минуту по часам
    const rpsC = rpsRef.current;
    if (rpsC && history) {
      const labels = hourLabels(history.labels);
      const perMinute = history.requests.map((r) => Math.round((r / 60) * 10) / 10);
      charts.current.push(new ChartJS(rpsC, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label: 'запросов/мин', data: perMinute,
            backgroundColor: 'rgba(47,166,201,0.55)', borderRadius: 3,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#E8EAF0', boxWidth: 12 } } },
          scales: {
            x: { ticks: { color: C_GRAY, maxTicksLimit: 12 }, grid: { color: C_GRID } },
            y: { beginAtZero: true, ticks: { color: C_GRAY }, grid: { color: C_GRID } },
          },
        },
      }));
    }

    // 5) Латентность по узлам графа (p50 / p95, горизонтальный бар)
    const nodeC = nodeLatRef.current;
    const latencyByNode = summary?.latency_by_node || {};
    if (nodeC && Object.keys(latencyByNode).length) {
      const nodes = Object.keys(latencyByNode);
      const labels = nodes.map((n) => NODE_LABELS[n] || n);
      charts.current.push(new ChartJS(nodeC, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              label: 'p50',
              data: nodes.map((n) => latencyByNode[n]?.p50_ms || 0),
              backgroundColor: C_BLUE,
              borderRadius: 4,
            },
            {
              label: 'p95',
              data: nodes.map((n) => latencyByNode[n]?.p95_ms || 0),
              backgroundColor: C_ORANGE,
              borderRadius: 4,
            },
          ],
        },
        options: {
          indexAxis: 'y' as const,
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#E8EAF0', boxWidth: 12 } } },
          scales: {
            x: { ticks: { color: C_GRAY }, grid: { color: C_GRID }, title: { display: true, text: 'мс', color: C_GRAY } },
            y: { ticks: { color: C_GRAY }, grid: { display: false } },
          },
        },
      }));
    }

    // 6) Токены по узлам
    const tokenCanvas = tokensRef.current;
    if (tokenCanvas && summary) {
      const nodes = Object.keys(summary.tokens_by_node || {});
      charts.current.push(new ChartJS(tokenCanvas, {
        type: 'bar',
        data: {
          labels: nodes.map((n) => NODE_LABELS[n] || n),
          datasets: [
            { label: 'Prompt', data: nodes.map((n) => summary.tokens_by_node[n]?.prompt || 0), backgroundColor: C_BLUE, borderRadius: 5 },
            { label: 'Completion', data: nodes.map((n) => summary.tokens_by_node[n]?.completion || 0), backgroundColor: C_ORANGE, borderRadius: 5 },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#E8EAF0', boxWidth: 12 } } },
          scales: {
            x: { ticks: { color: C_GRAY }, grid: { color: C_GRID } },
            y: { ticks: { color: C_GRAY }, grid: { color: C_GRID } },
          },
        },
      }));
    }

    // 7) Статусы запросов (донат, всего)
    const allC = statusAllRef.current;
    if (allC && summary && Object.keys(summary.requests_by_status || {}).length) {
      const statuses = Object.keys(summary.requests_by_status);
      const colors = statuses.map((s) =>
        s === 'success' ? C_GREEN : s === 'failed' ? C_RED : C_GOLD);
      charts.current.push(new ChartJS(allC, {
        type: 'doughnut',
        data: {
          labels: statuses,
          datasets: [{
            data: statuses.map((s) => summary.requests_by_status[s] || 0),
            backgroundColor: colors,
            borderColor: 'rgba(0,0,0,0)',
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '62%',
          plugins: { legend: { labels: { color: '#E8EAF0' } } },
        },
      }));
    }

    // 8) Затраты по узлам (донат)
    const costCanvas = costRef.current;
    if (costCanvas && summary && Object.keys(summary.cost_by_node || {}).length) {
      const costNodes = Object.keys(summary.cost_by_node);
      charts.current.push(new ChartJS(costCanvas, {
        type: 'doughnut',
        data: {
          labels: costNodes.map((n) => NODE_LABELS[n] || n),
          datasets: [{
            data: costNodes.map((n) => summary.cost_by_node[n] || 0),
            backgroundColor: [C_ORANGE, C_BLUE, C_GREEN, C_GOLD, CHART_COLORS[4] || C_RED],
            borderColor: 'rgba(0,0,0,0)',
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '62%',
          plugins: { legend: { labels: { color: '#E8EAF0' } } },
        },
      }));
    }

    // 9) Успешность ответов (gauge-донат)
    const accC = accuracyRef.current;
    if (accC && summary) {
      const rate = Math.max(0, Math.min(100, summary.success_rate || 0));
      charts.current.push(new ChartJS(accC, {
        type: 'doughnut',
        data: {
          labels: ['успех', 'остальное'],
          datasets: [{
            data: [rate, 100 - rate],
            backgroundColor: [C_GREEN, 'rgba(138,151,166,0.18)'],
            borderColor: 'rgba(0,0,0,0)',
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '72%',
          plugins: { legend: { display: false } },
        },
      }));
    }
  }, [summary, history]);

  const nodeEntries =
    summary && Object.keys(summary.latency_by_node || {}).length
      ? Object.entries(summary.latency_by_node as Record<string, NodeLatency>)
      : [];
  const maxNodeP95 = nodeEntries.length
    ? Math.max(...nodeEntries.map(([, v]) => v.p95_ms || 0), 1)
    : 1;

  return (
    <div className="metrics">
      <motion.div
        className="metrics__header"
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h2 className="metrics__title">
          <Gauge size={26} style={{ verticalAlign: 'middle', marginRight: 8 }} />
          Метрики
        </h2>
        <span className="metrics__subtitle">Наблюдаемость агента: запросы, время ответа, токены, затраты</span>
        <div className="metrics__toolbar">
          <div className="metrics__toolbar-group">
            <span className="metrics__toolbar-label">Период</span>
            <div className="metrics__seg">
              {PERIODS.map((p) => (
                <button
                  key={p.value}
                  className={`metrics__seg-btn${hours === p.value ? ' metrics__seg-btn--active' : ''}`}
                  onClick={() => setHours(p.value)}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <button
            className={`btn metrics__autorefresh${autoRefresh ? ' metrics__autorefresh--on' : ''}`}
            onClick={() => setAutoRefresh((v) => !v)}
            title={autoRefresh ? 'Автообновление каждые 15 с — выключить' : 'Включить автообновление каждые 15 с'}
          >
            {autoRefresh ? <Play size={14} /> : <Pause size={14} />}
            авто
          </button>
          <button className="btn btn--ghost metrics__refresh" onClick={load}>
            <RefreshCw size={16} className={loading ? 'spin' : undefined} />
          </button>
          {updatedAt && <span className="metrics__updated">обновлено {updatedAt}</span>}
        </div>
      </motion.div>

      {loading && !summary && (
        <div className="panel panel--center">
          <Activity size={28} className="spin" />
          <p>Загрузка метрик...</p>
        </div>
      )}

      {error && !summary && (
        <div className="panel panel--center">
          <ServerCrash size={28} />
          <p>Не удалось получить метрики: {error}</p>
          <button className="btn" onClick={load}>Повторить</button>
        </div>
      )}

      {summary && (
        <>
          <div className="metrics__stats">
            <StatCard
              title="Всего запросов"
              value={summary.total_requests.toLocaleString('ru-RU')}
              sub="через /ask, всего"
              icon={TrendingUp}
              accent="red"
              delay={0}
            />
            <StatCard
              title="Успешность"
              value={fmtPct(summary.success_rate)}
              sub="status=success / всего"
              icon={ShieldCheck}
              accent="green"
              delay={0.05}
            />
            <StatCard
              title="Латентность p95"
              value={fmt(summary.latency_p95_ms ?? summary.avg_latency_ms)}
              sub={`в среднем ${fmt(summary.avg_latency_ms)}`}
              icon={Timer}
              accent="cyan"
              delay={0.1}
            />
            <StatCard
              title="В обработке"
              value={String(summary.inflight ?? 0)}
              sub="запросов прямо сейчас"
              icon={Activity}
              accent="blue"
              delay={0.15}
            />
            <StatCard
              title="Токенов LLM"
              value={summary.total_tokens.toLocaleString('ru-RU')}
              sub="prompt + completion"
              icon={BarChart3}
              accent="gold"
              delay={0.2}
            />
            <StatCard
              title="Затраты LLM"
              value={`${summary.total_cost_rub.toFixed(2)} ₽`}
              sub="оценочная стоимость"
              icon={Coins}
              accent="blue"
              delay={0.25}
            />
            <StatCard
              title="Из кэша"
              value={fmtPct(summary.cache_hit_rate)}
              sub={`${fmtNum(summary.cache_hits)} ответов`}
              icon={Database}
              accent="cyan"
              delay={0.3}
            />
            <StatCard
              title="Проблемные"
              value={problemsTotal.toLocaleString('ru-RU')}
              sub="failed + low_confidence"
              icon={ServerCrash}
              accent="red"
              delay={0.35}
            />
          </div>

          <div className="metrics__section-title">
            <Layers size={13} /> Производительность · {hours} ч
          </div>
          <div className="metrics__charts">
            <Panel title="Латентность /ask" now={`p95 ${nowP95}`} delay={0.1}>
              <div className="metrics__chart">
                <canvas ref={latencyRef} />
              </div>
            </Panel>
            <Panel
              title="Запросы по статусам"
              now={`всего ${history ? history.requests.slice(-1)[0] : 0}`}
              delay={0.15}
            >
              <div className="metrics__chart">
                <canvas ref={statusRef} />
              </div>
            </Panel>
            <Panel title="Проблемные ответы" now="failed + low" delay={0.2}>
              <div className="metrics__chart">
                <canvas ref={errorsRef} />
              </div>
            </Panel>
            <Panel
              title="Нагрузка"
              now={`${history ? Math.round((history.requests.slice(-1)[0] || 0) / 60 * 10) / 10 : 0} req/мин`}
              delay={0.25}
            >
              <div className="metrics__chart">
                <canvas ref={rpsRef} />
              </div>
            </Panel>
          </div>

          <div className="metrics__section-title">
            <Layers size={13} /> Узлы агента и LLM
          </div>
          <div className="metrics__charts">
            <Panel title="Латентность по узлам графа" now="p50 / p95, мс" wide delay={0.1}>
              <div className="metrics__chart">
                <canvas ref={nodeLatRef} />
              </div>
            </Panel>
            <Panel title="Токены LLM по узлам" now={fmtNum(summary.total_tokens)} delay={0.15}>
              <div className="metrics__chart">
                <canvas ref={tokensRef} />
              </div>
            </Panel>
            <Panel title="Затраты LLM по узлам" now={`${summary.total_cost_rub.toFixed(2)} ₽`} delay={0.2}>
              <div className="metrics__chart">
                <canvas ref={costRef} />
              </div>
            </Panel>
            {nodeEntries.length > 0 && (
              <Panel title="Узлы агента" now="вызовы · p50 · p95" wide delay={0.25}>
                <div className="metrics__node-table">
                  <table className="metrics__table">
                    <thead>
                      <tr>
                        <th>Узел</th>
                        <th className="metrics__table-num">Вызовов</th>
                        <th className="metrics__table-num">avg</th>
                        <th className="metrics__table-num">p50</th>
                        <th className="metrics__table-num">p95</th>
                        <th>p95, % от max</th>
                      </tr>
                    </thead>
                    <tbody>
                      {nodeEntries.map(([node, v]) => (
                        <tr key={node}>
                          <td>{NODE_LABELS[node] || node}</td>
                          <td className="metrics__table-num">{v.count}</td>
                          <td className="metrics__table-num">{fmt(v.avg_ms)}</td>
                          <td className="metrics__table-num">{fmt(v.p50_ms)}</td>
                          <td className="metrics__table-num metrics__table-num--p95">{fmt(v.p95_ms)}</td>
                          <td>
                            <span className="metrics__mini-track">
                              <span
                                className="metrics__mini-fill"
                                style={{ width: `${Math.max(2, (v.p95_ms / maxNodeP95) * 100)}%` }}
                              />
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
            )}
          </div>

          <div className="metrics__section-title">
            <ShieldCheck size={13} /> Надёжность и стоимость
          </div>
          <div className="metrics__charts">
            <Panel
              title="Успешность (всего)"
              now={fmtPct(summary.success_rate)}
              delay={0.1}
            >
              <div className="metrics__chart metrics__chart--gauge">
                <canvas ref={accuracyRef} />
              </div>
            </Panel>
            <Panel
              title="Статусы запросов · всего"
              now={`${fmtPct(summary.success_rate)} успех`}
              delay={0.15}
            >
              <div className="metrics__chart">
                <canvas ref={statusAllRef} />
              </div>
            </Panel>
            <Panel
              title="Кэш ответов"
              now={`${fmtNum(summary.cache_hits)} хитов`}
              delay={0.2}
            >
              <div className="metrics__cache">
                <div className="metrics__cache-row">
                  <span>Хитов кэша</span>
                  <strong>{fmtNum(summary.cache_hits)}</strong>
                </div>
                <div className="metrics__cache-row">
                  <span>Доля</span>
                  <strong>{fmtPct(summary.cache_hit_rate)}</strong>
                </div>
                <div className="metrics__mini-track metrics__mini-track--lg">
                  <span
                    className="metrics__mini-fill metrics__mini-fill--gold"
                    style={{ width: `${Math.max(2, Math.min(100, summary.cache_hit_rate || 0))}%` }}
                  />
                </div>
                <p className="metrics__cache-hint">
                  Ответы без прогона графа — из query_cache по короткому RAG-пути
                </p>
              </div>
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}