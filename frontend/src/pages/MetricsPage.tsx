import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity, BarChart3, Clock, Coins, Gauge, RefreshCw, ServerCrash, TrendingUp,
} from 'lucide-react';
import { Chart, registerables } from 'chart.js';
import { Chart as ChartJS } from 'chart.js';
import api from '@/api';
import type { MetricsSummary } from '@/types/api';
import { CHART_COLORS } from '@/lib/utils';

Chart.register(...registerables);

interface StatCardProps {
  title: string;
  value: string;
  sub: string;
  icon: typeof Activity;
  accent: 'red' | 'gold' | 'cyan' | 'green';
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

export default function MetricsPage() {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const tokensRef = useRef<HTMLCanvasElement>(null);
  const costRef = useRef<HTMLCanvasElement>(null);
  const statusRef = useRef<HTMLCanvasElement>(null);
  const charts = useRef<ChartJS[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getMetricsSummary();
      setSummary(data);
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

  // Перерисовываем графики при обновлении данных.
  useEffect(() => {
    if (!summary) return;
    charts.current.forEach((c) => c.destroy());
    charts.current = [];

    const tokenCanvas = tokensRef.current;
    if (tokenCanvas) {
      const nodes = Object.keys(summary.tokens_by_node || {});
      const prompt = nodes.map((n) => summary.tokens_by_node[n]?.prompt || 0);
      const completion = nodes.map((n) => summary.tokens_by_node[n]?.completion || 0);
      const labels = nodes.map((n) => NODE_LABELS[n] || n);
      charts.current.push(new ChartJS(tokenCanvas, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: 'Prompt (вход)', data: prompt, backgroundColor: CHART_COLORS[0], borderRadius: 6 },
            { label: 'Completion (выход)', data: completion, backgroundColor: CHART_COLORS[1], borderRadius: 6 },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#E8EAF0' } } },
          scales: {
            x: { ticks: { color: '#8A8D8F' }, grid: { color: 'rgba(200,168,78,0.08)' } },
            y: { ticks: { color: '#8A8D8F' }, grid: { color: 'rgba(200,168,78,0.08)' } },
          },
        },
      }));
    }

    const costCanvas = costRef.current;
    if (costCanvas) {
      const costNodes = Object.keys(summary.cost_by_node || {});
      charts.current.push(new ChartJS(costCanvas, {
        type: 'doughnut',
        data: {
          labels: costNodes.map((n) => NODE_LABELS[n] || n),
          datasets: [{
            data: costNodes.map((n) => summary.cost_by_node[n] || 0),
            backgroundColor: CHART_COLORS,
            borderColor: 'rgba(0,0,0,0)',
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#E8EAF0' } } },
        },
      }));
    }

    const statusCanvas = statusRef.current;
    if (statusCanvas) {
      const statuses = Object.keys(summary.requests_by_status || {});
      const colors = statuses.map((s) => {
        if (s === 'success') return '#34d399';
        if (s === 'failed') return '#f87171';
        return '#fbbf24';
      });
      charts.current.push(new ChartJS(statusCanvas, {
        type: 'pie',
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
          plugins: { legend: { labels: { color: '#E8EAF0' } } },
        },
      }));
    }
  }, [summary]);

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
        <span className="metrics__subtitle">Запросы, токены LLM и затраты на агента</span>
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
              title="Запросов"
              value={String(summary.total_requests)}
              sub={`средняя ${summary.avg_latency_ms} мс`}
              icon={TrendingUp}
              accent="red"
              delay={0}
            />
            <StatCard
              title="Токенов (всего)"
              value={summary.total_tokens.toLocaleString('ru-RU')}
              sub="prompt + completion"
              icon={BarChart3}
              accent="gold"
              delay={0.05}
            />
            <StatCard
              title="Затраты LLM"
              value={`${summary.total_cost_rub.toFixed(2)} ₽`}
              sub="оценочная стоимость"
              icon={Coins}
              accent="cyan"
              delay={0.1}
            />
            <StatCard
              title="Средняя латентность"
              value={`${summary.avg_latency_ms} мс`}
              sub="на запрос /ask"
              icon={Clock}
              accent="green"
              delay={0.15}
            />
          </div>

          <div className="metrics__row">
            <motion.div
              className="panel metrics__panel"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
            >
              <h3 className="metrics__panel-title">Токены по узлам агента</h3>
              <div className="metrics__chart">
                <canvas ref={tokensRef} />
              </div>
            </motion.div>

            <motion.div
              className="panel metrics__panel"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
            >
              <h3 className="metrics__panel-title">Затраты по узлам</h3>
              <div className="metrics__chart">
                <canvas ref={costRef} />
              </div>
            </motion.div>

            <motion.div
              className="panel metrics__panel"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25 }}
            >
              <h3 className="metrics__panel-title">Статусы запросов</h3>
              <div className="metrics__chart">
                <canvas ref={statusRef} />
              </div>
            </motion.div>
          </div>
        </>
      )}
    </div>
  );
}