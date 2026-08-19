import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { RotateCcw, Send, Sparkles, Trash2 } from 'lucide-react';
import { motion } from 'framer-motion';
import api from '@/api';
import type { FileResponse, SourceInfo } from '@/types/api';
import { useToast } from '@/hooks/useToast';
import { ToastContainer } from '@/components/ui/Toast';
import FileList from '@/components/files/FileList';
import FileUpload from '@/components/files/FileUpload';
import ChatMessage, { type ChatMessageData } from '@/components/chat/ChatMessage';
import SourcesModal from '@/components/chat/SourcesModal';
import AgentProgress from '@/components/chat/AgentProgress';
import TypingIndicator from '@/components/chat/TypingIndicator';

const SUGGESTIONS = [
  'Средняя цена лома меди по Ферроком в феврале 2025',
  'Сравни цены на латунь у всех поставщиков в декабре 2025',
  'Дельта между мин и макс ценой на медь по поставщикам',
];

// Генерация нового thread_id (conversation_id) для диалога.
function newThreadId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `chat-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export default function ChatPage() {
  const navigate = useNavigate();
  const { toasts, showToast, dismiss } = useToast();

  const [files, setFiles] = useState<FileResponse[]>([]);
  const [selectedFile, setSelectedFile] = useState<FileResponse | null>(null);
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [question, setQuestion] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [topK, setTopK] = useState(10);
  const [responseMode, setResponseMode] = useState<'detailed' | 'concise'>('detailed');
  const [agentStep, setAgentStep] = useState(-1);
  const [sourcesModal, setSourcesModal] = useState<SourceInfo[] | null>(null);
  // conversationId = thread_id диалога (для checkpointer/interrupt на бэкенде).
  const [conversationId, setConversationId] = useState<string | null>(() => newThreadId());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const idRef = useRef(0);

  const autoResize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  };

  const loadFiles = useCallback(async () => {
    try {
      const data = await api.listFiles({ limit: 100 });
      setFiles(data.files || []);
    } catch (err) {
      showToast(`Ошибка загрузки файлов: ${(err as Error).message}`, 'error');
    }
  }, [showToast]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isAsking, agentStep]);

  const addMessage = (msg: Omit<ChatMessageData, 'id'>) => {
    setMessages((prev) => [...prev, { ...msg, id: ++idRef.current }]);
  };

  const handleSend = async () => {
    const q = question.trim();
    if (!q || isAsking) return;

    setIsAsking(true);
    setAgentStep(0);
    addMessage({ type: 'user', content: q });
    setQuestion('');
    window.requestAnimationFrame(() => {
      autoResize();
      textareaRef.current?.focus();
    });

    try {
      const result = await api.askQuestion({
        question: q,
        top_k: topK,
        mode: 'agent',
        response_mode: responseMode,
        conversation_id: conversationId,
      });
      setAgentStep(-1);
      addMessage({
        type: 'assistant',
        content: result.answer,
        meta: result,
        sources: result.sources,
      });
    } catch (err) {
      setAgentStep(-1);
      addMessage({ type: 'error', content: `❌ Ошибка: ${(err as Error).message}` });
    } finally {
      setIsAsking(false);
    }
  };

  const handleUpload = async (file: File) => {
    try {
      await api.uploadFile(file);
      showToast('Файл загружен успешно', 'success');
      loadFiles();
    } catch (err) {
      showToast(`Ошибка загрузки: ${(err as Error).message}`, 'error');
    }
  };

  const handleDelete = async (fileId: number) => {
    if (!window.confirm('Удалить файл?')) return;
    try {
      await api.deleteFile(fileId);
      showToast('Файл удалён', 'success');
      if (selectedFile?.id === fileId) setSelectedFile(null);
      loadFiles();
    } catch (err) {
      showToast(`Ошибка удаления: ${(err as Error).message}`, 'error');
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    showToast('Скопировано в буфер обмена', 'success');
  };

  const handleTrace = (requestId: string) => {
    navigate(`/trace?request_id=${requestId}`);
  };

  const handleClearCache = async () => {
    if (!window.confirm('Очистить кэшированные запросы?')) return;
    try {
      const res = await api.clearCache();
      showToast(`Кэш очищен (${res.cleared} записей)`, 'success');
    } catch (err) {
      showToast(`Ошибка очистки кэша: ${(err as Error).message}`, 'error');
    }
  };

  // Начать новый диалог: сбросить сообщения и thread_id.
  const handleNewChat = () => {
    setMessages([]);
    setQuestion('');
    setAgentStep(-1);
    setSourcesModal(null);
    setConversationId(newThreadId());
    showToast('Начат новый чат', 'success');
    textareaRef.current?.focus();
  };

  return (
    <div className="layout">
      <aside className="panel panel--files">
        <FileUpload onUpload={handleUpload} compact />
        <FileList
          files={files}
          selectedId={selectedFile?.id}
          onSelect={(f) => setSelectedFile(f)}
          onDelete={handleDelete}
          onRefresh={loadFiles}
        />
      </aside>

      <section className="panel panel--chat">
        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="chat-welcome">
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
              >
                <div className="chat-welcome__title">
                  <Sparkles size={24} style={{ verticalAlign: 'middle', marginRight: 8 }} />
                  Здравствуйте!
                </div>
                <div className="chat-welcome__text">
                  Я — AI-агент для анализа Excel-данных ЕВРАЗ.
                  <br />
                  Загрузите файл с ценами на металлы и задайте вопрос.
                </div>
                <div className="chat-welcome__suggestions">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      className="chat-welcome__chip"
                      onClick={() => {
                        setQuestion(s);
                        textareaRef.current?.focus();
                      }}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </motion.div>
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessage
              key={msg.id}
              message={msg}
              onCopy={handleCopy}
              onOpenSources={setSourcesModal}
              onTrace={handleTrace}
            />
          ))}

          {isAsking && agentStep >= 0 && <AgentProgress activeStep={agentStep} />}
          {isAsking && agentStep < 0 && <TypingIndicator />}

          <div ref={messagesEndRef} />
        </div>

        <div className="chat-controls">
          <div className="chat-settings">
            <label className="chat-settings__item">
              <span className="chat-settings__label">Формат:</span>
              <select
                className="chat-settings__select"
                value={responseMode}
                onChange={(e) => setResponseMode(e.target.value as typeof responseMode)}
              >
                <option value="detailed">📝 Полный ответ</option>
                <option value="concise">🔢 Только число</option>
              </select>
            </label>
            <label className="chat-settings__item">
              <span className="chat-settings__label">Top-K:</span>
              <input
                className="chat-settings__input"
                type="number"
                value={topK}
                min={1}
                max={50}
                onChange={(e) => setTopK(parseInt(e.target.value) || 10)}
              />
            </label>
            <button
              type="button"
              className="chat-settings__new"
              onClick={handleNewChat}
              title="Начать новый диалог (сбросить thread_id)"
            >
              <RotateCcw size={16} />
              <span>Новый чат</span>
            </button>
            <button
              type="button"
              className="chat-settings__clear"
              onClick={handleClearCache}
              title="Очистить кэшированные запросы"
            >
              <Trash2 size={16} />
              <span>Очистить кэш</span>
            </button>
          </div>

          <form
            className="chat-input"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <div className="chat-input__wrap">
              <textarea
                ref={textareaRef}
                className="chat-input__field"
                rows={1}
                value={question}
                onChange={(e) => {
                  setQuestion(e.target.value);
                  autoResize();
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="Задайте вопрос о данных... (Enter — отправить, Shift+Enter — новая строка)"
                autoComplete="off"
              />
              <div className="chat-input__hint">
                <kbd>Enter</kbd> отправить
              </div>
            </div>
            <button
              className="btn btn--primary chat-input__btn"
              type="submit"
              disabled={!question.trim() || isAsking}
            >
              <Send size={18} />
            </button>
          </form>
        </div>
      </section>

      <SourcesModal
        open={sourcesModal !== null}
        sources={sourcesModal || []}
        onClose={() => setSourcesModal(null)}
      />
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}