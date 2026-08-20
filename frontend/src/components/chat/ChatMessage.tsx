import { useState } from 'react';
import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import {
  BarChart3,
  Bot,
  CornerDownLeft,
  Loader2,
  User,
  XCircle,
  Timer,
  Fingerprint,
  Search,
  BookOpen,
  Wand2,
} from 'lucide-react';
import type { AskResponse, ChartPoint, SourceInfo } from '@/types/api';
import { confidenceLabel, formatMs, modeLabel, shortId } from '@/lib/utils';
import { SourceList } from './SourcesModal';
import SqlBlock from './SqlBlock';
import ResultChart from './ResultChart';
import ResultTable from './ResultTable';

export interface ChatMessageData {
  id: number;
  type: 'user' | 'assistant' | 'error';
  content: string;
  meta?: AskResponse;
  sources?: SourceInfo[];
}

interface ChatMessageProps {
  message: ChatMessageData;
  onCopy: (text: string) => void;
  onOpenSources: (sources: SourceInfo[]) => void;
  onTrace: (requestId: string) => void;
  onClarify?: (refinement: string) => void;
  clarifyBase?: string;
  onMakeChart?: (threadId: string) => Promise<ChartPoint[]>;
}

export default function ChatMessage({
  message,
  onCopy,
  onOpenSources,
  onTrace,
  onClarify,
  clarifyBase,
  onMakeChart,
}: ChatMessageProps) {
  const { type, content, meta } = message;
  const isUser = type === 'user';
  const isError = type === 'error';
  const isConcise = meta?.response_mode === 'concise';
  const [showClarify, setShowClarify] = useState(false);
  const [clarifyText, setClarifyText] = useState('');
  // Кэш chart_data на уровне конкретного сообщения — повторный клик не бьёт в бэкенд.
  const [chartData, setChartData] = useState<ChartPoint[] | null>(meta?.chart_data ?? null);
  const [chartLoading, setChartLoading] = useState(false);

  const handleMakeChart = async () => {
    if (!meta?.thread_id || !onMakeChart) return;
    if (chartData && chartData.length > 0) return;
    setChartLoading(true);
    try {
      const data = await onMakeChart(meta.thread_id);
      if (data && data.length > 0) setChartData(data);
    } catch {
      /* toast handled in parent */
    } finally {
      setChartLoading(false);
    }
  };

  const sqlPreview = meta?.sql_result_preview?.length ? meta.sql_result_preview : null;

  return (
    <motion.div
      className={`chat-message chat-message--${type}`}
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 350, damping: 28 }}
    >
      <div className="chat-message__header">
        <span className="chat-message__avatar">
          {isUser ? <User size={16} /> : isError ? <XCircle size={16} /> : <Bot size={16} />}
        </span>
        <span className="chat-message__author">
          {isUser ? 'Вы' : isError ? 'Ошибка' : 'Ассистент'}
        </span>
        {isConcise && <Wand2 size={13} className="chat-message__concise-ico" />}
      </div>

      <div className="chat-message__content">
        {type === 'assistant' && isConcise ? (
          <div className="chat-message__concise">{content}</div>
        ) : type === 'assistant' ? (
          <ReactMarkdown>{content}</ReactMarkdown>
        ) : (
          content
        )}
      </div>

      {meta?.sql_query && <SqlBlock sql={meta.sql_query} onCopy={onCopy} />}

      {sqlPreview && <ResultTable data={sqlPreview} onCopy={onCopy} />}

      {(type === 'assistant' || type === 'error') && (meta || content) && (
        <div className="chat-message__meta">
          {meta?.mode_used && (
            <span className={`chat-message__badge chat-message__badge--${modeLabel(meta.mode_used).cls}`}>
              {modeLabel(meta.mode_used).text}
            </span>
          )}
          {isConcise && (
            <span className="chat-message__badge chat-message__badge--concise">🔢 Только число</span>
          )}
          {meta?.confidence !== undefined && (
            <span className={`chat-message__badge chat-message__badge--${confidenceLabel(meta.confidence).cls}`}>
              Уверенность: {confidenceLabel(meta.confidence).text} ({(meta.confidence * 100).toFixed(0)}%)
            </span>
          )}
          {meta?.latency_ms != null && (
            <span className="chat-message__badge">
              <Timer size={12} /> {formatMs(meta.latency_ms)}
            </span>
          )}
          {meta?.self_corrected && (
            <span className="chat-message__badge chat-message__badge--warning">🔄 Self-Correction</span>
          )}
          {meta?.request_id && (
            <>
              <button className="chat-message__badge chat-message__badge--copy" onClick={() => onCopy(meta.request_id!)} title="Скопировать request_id">
                <Fingerprint size={12} /> {shortId(meta.request_id)}
              </button>
              <button className="chat-message__sources-btn" onClick={() => onTrace(meta.request_id!)}>
                <Search size={12} /> Trace
              </button>
            </>
          )}
          {message.sources && message.sources.length > 0 && (
            <button className="chat-message__sources-btn" onClick={() => onOpenSources(message.sources!)}>
              <BookOpen size={12} /> Источники ({message.sources.length})
            </button>
          )}
          {!isUser && !isError && onClarify && (
            <button
              className="chat-message__badge chat-message__badge--clarify"
              onClick={() => setShowClarify((v) => !v)}
              title="Уточнить информацию по этому запросу"
            >
              <CornerDownLeft size={12} /> Уточнить
            </button>
          )}
          {!isUser && !isError && onMakeChart && meta?.thread_id && (
            <button
              className="chat-message__badge chat-message__badge--chart"
              onClick={handleMakeChart}
              disabled={chartLoading || (!!chartData && chartData.length > 0)}
              title="Построить график по всем месяцам"
            >
              {chartLoading ? (
                <Loader2 size={12} className="chat-message__spin" />
              ) : (
                <BarChart3 size={12} />
              )}{' '}
              Сделай график
            </button>
          )}
        </div>
      )}

      {chartData && chartData.length > 0 && <ResultChart data={chartData} />}

      {showClarify && onClarify && (
        <form
          className="chat-clarify"
          onSubmit={(e) => {
            e.preventDefault();
            const t = clarifyText.trim();
            if (!t) return;
            onClarify(t);
            setClarifyText('');
            setShowClarify(false);
          }}
        >
          {clarifyBase && <div className="chat-clarify__base">Запрос: {clarifyBase}</div>}
          <textarea
            className="chat-clarify__textarea"
            rows={2}
            autoFocus
            value={clarifyText}
            onChange={(e) => setClarifyText(e.target.value)}
            placeholder="Уточните, что именно нужно уточнить..."
          />
          <div className="chat-clarify__actions">
            <button className="chat-clarify__send" type="submit" disabled={!clarifyText.trim()}>
              Отправить уточнение
            </button>
            <button
              className="chat-clarify__cancel"
              type="button"
              onClick={() => {
                setClarifyText('');
                setShowClarify(false);
              }}
            >
              Отмена
            </button>
          </div>
        </form>
      )}
    </motion.div>
  );
}

export { SourceList };