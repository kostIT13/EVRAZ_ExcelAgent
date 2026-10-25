import { motion } from 'framer-motion';
import type { TraceStepInfo } from '@/types/api';
import { formatMs } from '@/lib/utils';

export const STEP_COLORS: Record<string, string> = {
  question: '#60a5fa',
  classifier: '#a78bfa',
  disambiguation: '#e5b53d',
  planner: '#e5b53d',
  codegen: '#2fa6c9',
  executor: '#e5484d',
  verifier: '#3fbf8a',
  verification: '#3fbf8a',
  retrieval: '#e5b53d',
  answer: '#3fbf8a',
};
const FALLBACK_COLOR = '#8a97a6';

interface TraceWaterfallProps {
  steps: TraceStepInfo[];
  /** Общая латентность запроса, мс */
  totalMs: number;
  /** Индекс активного шага (null — ничего не выбрано) */
  activeIndex: number | null;
  onSelect: (index: number) => void;
}

interface Row {
  index: number;
  start: number;
  dur: number;
  step: TraceStepInfo;
}

export default function TraceWaterfall({ steps, totalMs, activeIndex, onSelect }: TraceWaterfallProps) {
  const dur = (s: TraceStepInfo) =>
    Number(((s.data as Record<string, unknown> | undefined)?.duration_ms as number) || 0);

  const durations = steps.map(dur);
  const sum = durations.reduce((a, b) => a + b, 0);
  const scale = Math.max(totalMs || 0, sum, 1);

  let cursor = 0;
  const rows: Row[] = steps.map((step, index) => {
    const start = cursor;
    cursor += durations[index];
    return { index, start, dur: durations[index], step };
  });

  const remainder = totalMs > 0 ? totalMs - sum : 0;
  const hasRemainder = remainder > 1;

  const pct = (v: number) => (v / scale) * 100;

  return (
    <div className="twc">
      <div className="twc__rows">
        {rows.map((row) => {
          const data = (row.step.data as Record<string, unknown> | undefined) || {};
          const label = (data.label as string) || row.step.step || `Шаг ${row.index + 1}`;
          const color = STEP_COLORS[row.step.step] || FALLBACK_COLOR;
          const isActive = activeIndex === row.index;
          return (
            <motion.button
              key={row.index}
              className={`twc__row${isActive ? ' twc__row--active' : ''}`}
              onClick={() => onSelect(row.index)}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: row.index * 0.03 }}
              title={`${label} · старт ${formatMs(row.start)} · ${row.dur > 0 ? formatMs(row.dur) : 'не замерено'}`}
            >
              <span className="twc__row-label">
                <span className="twc__row-name">{label}</span>
                <span className="twc__row-meta">{row.dur > 0 ? formatMs(row.dur) : '—'}</span>
              </span>
              <span className="twc__track">
                <span
                  className="twc__bar"
                  style={{
                    left: `${pct(row.start)}%`,
                    width: `${Math.max(pct(row.dur), row.dur > 0 ? 0.6 : 0)}%`,
                    background: color,
                  }}
                />
                {row.dur > 0 && (
                  <span className="twc__bar-time" style={{ left: `calc(${pct(row.start)}% + 6px)` }}>
                    {formatMs(row.start)}
                  </span>
                )}
              </span>
            </motion.button>
          );
        })}

        {hasRemainder && (
          <div className="twc__row twc__row--remainder" title="Время вне замеренных узлов графа">
            <span className="twc__row-label">
              <span className="twc__row-name">прочее (вне узлов)</span>
              <span className="twc__row-meta">{formatMs(remainder)}</span>
            </span>
            <span className="twc__track">
              <span
                className="twc__bar"
                style={{
                  left: `${pct(sum)}%`,
                  width: `${Math.max(pct(remainder), 0.6)}%`,
                  background: 'rgba(255,255,255,0.10)',
                }}
              />
            </span>
          </div>
        )}
      </div>

      <div className="twc__axis">
        {[0, 0.25, 0.5, 0.75, 1].map((p) => (
          <span key={p} className="twc__axis-tick" style={{ left: `${p * 100}%` }}>
            {formatMs(scale * p)}
          </span>
        ))}
      </div>
    </div>
  );
}