import { motion } from 'framer-motion';
import { Search, FileCode2, Zap, BrainCircuit, Check } from 'lucide-react';

const steps = [
  { icon: Search, label: 'Анализ вопроса', desc: 'Определяю тип запроса...' },
  { icon: FileCode2, label: 'Генерация SQL', desc: 'Формирую SQL-запрос...' },
  { icon: Zap, label: 'Выполнение', desc: 'Выполняю запрос к БД...' },
  { icon: BrainCircuit, label: 'Формирование ответа', desc: 'Анализирую результат...' },
];

interface AgentProgressProps {
  activeStep: number;
}

export default function AgentProgress({ activeStep }: AgentProgressProps) {
  return (
    <motion.div
      className="agent-progress"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
    >
      {steps.map((step, i) => {
        const Icon = step.icon;
        const isDone = i < activeStep;
        const isActive = i === activeStep;
        return (
          <motion.div
            key={step.label}
            className={`agent-progress__step${isActive ? ' agent-progress__step--active' : ''}${isDone ? ' agent-progress__step--done' : ''}`}
            animate={isActive ? { scale: 1.02 } : { scale: 1 }}
            transition={{ duration: 0.3 }}
          >
            <div className="agent-progress__indicator">
              <span className="agent-progress__icon">
                {isDone ? <Check size={16} /> : <Icon size={16} />}
              </span>
              <div className="agent-progress__line" />
            </div>
            <div className="agent-progress__info">
              <div className="agent-progress__label">{step.label}</div>
              <div className="agent-progress__desc">{step.desc}</div>
            </div>
          </motion.div>
        );
      })}
    </motion.div>
  );
}