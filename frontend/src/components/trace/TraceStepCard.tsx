import { motion } from 'framer-motion';
import { useState } from 'react';
import {
  ChevronDown,
  Database,
  FileCode2,
  Brain,
  Zap,
  CheckCircle2,
  Search,
  Sparkles,
  MessageSquare,
  ShieldCheck,
  Timer,
  Activity,
} from 'lucide-react';
import type { TraceStepInfo } from '@/types/api';
import { formatMs } from '@/lib/utils';

interface TraceStepCardProps {
  step: TraceStepInfo;
  index: number;
}

const STEP_ICONS: Record<string, { icon: typeof Brain; accent: string }> = {
  question: { icon: MessageSquare, accent: 'blue' },
  classifier: { icon: Brain, accent: 'purple' },
  planner: { icon: Sparkles, accent: 'gold' },
  codegen: { icon: FileCode2, accent: 'cyan' },
  executor: { icon: Zap, accent: 'red' },
  verifier: { icon: ShieldCheck, accent: 'green' },
  verification: { icon: CheckCircle2, accent: 'green' },
  retrieval: { icon: Search, accent: 'gold' },
  answer: { icon: Sparkles, accent: 'green' },
};

function pretty(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function renderField(label: string, value: unknown) {
  if (value === null || value === undefined || value === '') return null;
  const str = pretty(value);
  const isObject = typeof value === 'object';
  return (
    <div className="trace-field" key={label}>
      <span className="trace-field__label">{label}</span>
      {isObject ? (
        <pre className="trace-field__json">{str}</pre>
      ) : (
        <span className="trace-field__value">{str}</span>
      )}
    </div>
  );
}

export default function TraceStepCard({ step, index }: TraceStepCardProps) {
  const data = (step.data as Record<string, unknown>) || {};
  const stepName = step.step as string;
  const meta = STEP_ICONS[stepName] || { icon: Activity, accent: 'blue' };
  const Icon = meta.icon;
  const label = (data.label as string) || stepName || `Шаг ${index + 1}`;
  const durationMs = (data.duration_ms as number) || 0;
  const [open, setOpen] = useState(index < 4);

  // Определяем ключи для отображения (без внутренних служебных полей)
  const knownMeta = ['icon', 'label', 'duration_ms', 'question'];
  const contentKeys = Object.keys(data).filter((k) => !knownMeta.includes(k));

  const hasJson = contentKeys.some((k) => typeof data[k] === 'object' && data[k] !== null);
  const mainOutput = hasJson ? contentKeys.filter((k) => typeof data[k] === 'object' && data[k] !== null) : [];
  const scalarFields = contentKeys.filter((k) => !mainOutput.includes(k));

  return (
    <motion.div
      className={`trace-step-card trace-step-card--${meta.accent}`}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06 }}
    >
      <button className="trace-step-card__header" onClick={() => setOpen((o) => !o)}>
        <span className="trace-step-card__icon">
          <Icon size={16} />
        </span>
        <span className="trace-step-card__index">#{index + 1}</span>
        <span className="trace-step-card__label">{label}</span>
        {durationMs > 0 && (
          <span className="trace-step-card__time">
            <Timer size={12} /> {formatMs(durationMs)}
          </span>
        )}
        <ChevronDown
          size={16}
          className={`trace-step-card__chevron${open ? ' trace-step-card__chevron--open' : ''}`}
        />
      </button>

      {open && (
        <motion.div
          className="trace-step-card__body"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.25 }}
        >
          {stepName === 'question' && data.question ? (
            <div className="trace-question">
              <MessageSquare size={18} />
              <span>{data.question as string}</span>
            </div>
          ) : null}

          {scalarFields.length > 0 && (
            <div className="trace-fields">
              {scalarFields.map((k) => renderField(k, data[k]))}
            </div>
          )}

          {mainOutput.length > 0 && (
            <div className="trace-json-block">
              <div className="trace-json-block__title">
                <Database size={13} /> Детали
              </div>
              {mainOutput.map((k) => (
                <pre className="trace-json-block__content" key={k}>
                  {pretty(data[k])}
                </pre>
              ))}
            </div>
          )}

          {scalarFields.length === 0 && mainOutput.length === 0 && stepName !== 'question' && (
            <div className="trace-fields">
              {renderField('step', stepName)}
              {renderField('duration_ms', durationMs)}
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}