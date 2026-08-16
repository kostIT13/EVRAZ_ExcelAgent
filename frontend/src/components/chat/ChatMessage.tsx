import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import { Bot, User, XCircle, Timer, Fingerprint, Search, BookOpen, Wand2 } from 'lucide-react';
import type { AskResponse, SourceInfo } from '@/types/api';
import { confidenceLabel, formatMs, modeLabel, shortId } from '@/lib/utils';
import { SourceList } from './SourcesModal';
import SqlBlock from './SqlBlock';
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
}

export default function ChatMessage({ message, onCopy, onOpenSources, onTrace }: ChatMessageProps) {
  const { type, content, meta } = message;
  const isUser = type === 'user';
  const isError = type === 'error';
  const isConcise = meta?.response_mode === 'concise';

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
        </div>
      )}
    </motion.div>
  );
}

export { SourceList };