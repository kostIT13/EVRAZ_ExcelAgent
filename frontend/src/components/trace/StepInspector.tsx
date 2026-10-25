import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  Check,
  Copy,
  Database,
  FileJson2,
  MessageSquare,
  Timer,
  X,
} from 'lucide-react';
import type { TraceStepInfo } from '@/types/api';
import { formatMs } from '@/lib/utils';

interface StepInspectorProps {
  step: TraceStepInfo | null;
  index: number;
  totalMs: number;
  onClose: () => void;
}

const META_KEYS = ['icon', 'label', 'duration_ms'];

function pretty(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function isLong(value: unknown): boolean {
  return typeof value === 'string' && value.length > 140;
}

export default function StepInspector({ step, index, totalMs, onClose }: StepInspectorProps) {
  const [copied, setCopied] = useState(false);
  const [showFull, setShowFull] = useState(false);

  if (!step) return null;

  const data = (step.data as Record<string, unknown>) || {};
  const error = typeof data.error === 'string' ? data.error.trim() : '';
  const durationMs = (data.duration_ms as number) || 0;
  const share =
    totalMs > 0 && durationMs > 0 ? Math.max(0.1, Math.round((durationMs / totalMs) * 100)) : 0;
  const label = (data.label as string) || step.step || `Шаг ${index + 1}`;
  const question = typeof data.question === 'string' ? data.question : '';

  const contentKeys = Object.keys(data).filter((k) => !META_KEYS.includes(k) && k !== 'error');
  const jsonKeys = contentKeys.filter((k) => typeof data[k] === 'object' && data[k] !== null);
  const scalarKeys = contentKeys.filter((k) => !jsonKeys.includes(k));
  const longKeys = scalarKeys.filter((k) => isLong(data[k]));
  const shortKeys = scalarKeys.filter((k) => !longKeys.includes(k));

  const fullJson = JSON.stringify(data, null, 2);

  const copyJson = async () => {
    try {
      await navigator.clipboard.writeText(fullJson);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard недоступен */
    }
  };

  return (
    <motion.div
      className={`trace-inspector${error ? ' trace-inspector--error' : ''}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      key={step.step + index}
    >
      <div className="trace-inspector__head">
        <span className="trace-inspector__title">
          <Database size={14} />
          <span>
            Шаг #{index + 1} · {label}
          </span>
        </span>
        <span className="trace-inspector__tools">
          {durationMs > 0 && (
            <span className="trace-inspector__time">
              <Timer size={12} /> {formatMs(durationMs)} <em>({share}%)</em>
            </span>
          )}
          <button
            className="trace-inspector__iconbtn"
            onClick={copyJson}
            title="Скопировать JSON шага"
          >
            {copied ? <Check size={14} className="trace-inspector__ok" /> : <Copy size={14} />}
          </button>
          <button className="trace-inspector__iconbtn" onClick={onClose} title="Закрыть">
            <X size={14} />
          </button>
        </span>
      </div>

      {error && (
        <div className="trace-inspector__error">
          <AlertTriangle size={14} />
          <span>{error}</span>
        </div>
      )}

      {question && (
        <div className="trace-inspector__question">
          <MessageSquare size={14} />
          <span>{question}</span>
        </div>
      )}

      {shortKeys.length > 0 && (
        <div className="trace-inspector__fields">
          {shortKeys.map((k) => (
            <div className="trace-inspector__field" key={k}>
              <span className="trace-inspector__field-label">{k}</span>
              <span className="trace-inspector__field-value">{pretty(data[k])}</span>
            </div>
          ))}
        </div>
      )}

      {longKeys.map((k) => (
        <div className="trace-inspector__long" key={k}>
          <div className="trace-inspector__long-title">
            <FileJson2 size={12} /> {k}
          </div>
          <pre className="trace-inspector__pre">{pretty(data[k])}</pre>
        </div>
      ))}

      {jsonKeys.map((k) => (
        <div className="trace-inspector__long" key={k}>
          <div className="trace-inspector__long-title">
            <FileJson2 size={12} /> {k}
          </div>
          <pre className="trace-inspector__pre">{pretty(data[k])}</pre>
        </div>
      ))}

      {contentKeys.length === 0 && !error && !question && (
        <p className="trace-inspector__empty">Дополнительных данных по шагу нет</p>
      )}

      <div className="trace-inspector__footer">
        <button className="trace-inspector__toggle" onClick={() => setShowFull((v) => !v)}>
          {showFull ? 'Скрыть полный JSON' : 'Показать полный JSON'}
        </button>
        {showFull && <pre className="trace-inspector__fulljson">{fullJson}</pre>}
      </div>
    </motion.div>
  );
}