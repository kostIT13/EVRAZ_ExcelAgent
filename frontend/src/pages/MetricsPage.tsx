import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity, BarChart3, Clock, Coins, Gauge, RefreshCw, ServerCrash, ShieldCheck, TrendingUp,
} from 'lucide-react';
import { Chart, registerables } from 'chart.js';
import { Chart as ChartJS } from 'chart.js';
import api from '@/api';
import type { MetricsHistory, MetricsSummary } from '@/types/api';
import { CHART_COLORS } from '@/lib/utils';

Chart.register(...registerables);

// Палитра в стиле презентации EVRAZ
const C_ORANGE = '#FF5A36';
const C_BLUE = '#2FA6C9';
const C_GREEN = '#3FBF8A';
const C_RED = '#E5484D';
const C_GOLD = '#E5B53D';
const C_GRAY = '#8A97A6';
const C_GRID = 'rgba(138,151,166,0.14)';

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
  children: React.ReactNode;
  delay?: number;
}

function Panel({ title, now, children, delay = 0 }: PanelProps) {
  return (
    <motion.div
      className="panel metrics__panel"
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

export default function MetricsPage() {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [history, setHistory] = useState<MetricsHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const latencyRef = useRef<HTMLCanvasElement>(null);
  const statusRef = useRef<HTMLCanvasElement>(null);
  const errorsRef = useRef<HTMLCanvasElement>(null);
  const tokensRef = useRef<HTMLCanvasElement>(null);
  const costRef = useRef<HTMLCanvasElement>(null);
  const statusAllRef = useRef<HTMLCanvasElement>(null);
  const charts = useRef<ChartJS[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, h] = await Promise.all([
        api.getMetricsSummary(),
        api.getMetricsHistory({ hours: 24 }),
      ]);
      setSummary(s);
      setHistory(h);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => {
      clearInterval(t);
      charts.current.forEach((c) => c.destroy());
      charts.current = [];
    };
  }, [load]);

  // Текущие значения для заголовков панелей
  const nowTrend = (arr: number[] | undefined) =>
    arr && arr.length ? Math.round((arr[arr.length - 1] ?? 0) * 10) / 10 : 0;
  const nowP95 = history?.latency_p95_ms ? `${nowTrend(history.latency_p95_ms)} мс` : '—';

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

    // 4) Токены по узлам
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

    // 5) Статусы запросов (донат, всего)
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

    // 6) Затраты по узлам (донат)
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
  }, [summary, history]);

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
        <span className="metrics__subtitle">Запросы, время ответа, токены и затраты агента</span>
        <button className="btn btn--ghost metrics__refresh" onClick={load}>
          <RefreshCw size={16} /> Обновить
        </button>
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
              icon={Clock}
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
          </div>

          <div className="metrics__charts">
            <Panel title="Латентность /ask · 24 часа" now={`p95 ${nowP95}`} delay={0.1}>
              <div className="metrics__chart">
                <canvas ref={latencyRef} />
              </div>
            </Panel>
            <Panel
              title="Запросы по статусам · 24 часа"
              now={`всего ${history ? history.requests.slice(-1)[0] : 0}`}
              delay={0.15}
            >
              <div className="metrics__chart">
                <canvas ref={statusRef} />
              </div>
            </Panel>
            <Panel title="Проблемные ответы · 24 часа" now="failed + low" delay={0.2}>
              <div className="metrics__chart">
                <canvas ref={errorsRef} />
              </div>
            </Panel>
            <Panel title="Токены LLM по узлам агента" now={fmtNum(summary.total_tokens)} delay={0.25}>
              <div className="metrics__chart">
                <canvas ref={tokensRef} />
              </div>
            </Panel>
            <Panel
              title="Статусы запросов · всего"
              now={`${fmtPct(summary.success_rate)} успех`}
              delay={0.3}
            >
              <div className="metrics__chart">
                <canvas ref={statusAllRef} />
              </div>
            </Panel>
            <Panel title="Затраты LLM по узлам" now={`${summary.total_cost_rub.toFixed(2)} ₽`} delay={0.35}>
              <div className="metrics__chart">
                <canvas ref={costRef} />
              </div>
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}