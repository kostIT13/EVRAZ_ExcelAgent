import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Send, Sparkles } from 'lucide-react';
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

export default function ChatPage() {
  const navigate = useNavigate();
  const { toasts, showToast, dismiss } = useToast();

  const [files, setFiles] = useState<FileResponse[]>([]);
  const [selectedFile, setSelectedFile] = useState<FileResponse | null>(null);
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [question, setQuestion] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [mode, setMode] = useState<'auto' | 'rag' | 'agent'>('auto');
  const [topK, setTopK] = useState(10);
  const [agentStep, setAgentStep] = useState(-1);
  const [sourcesModal, setSourcesModal] = useState<SourceInfo[] | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const idRef = useRef(0);

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

    try {
      const result = await api.askQuestion({ question: q, top_k: topK, mode });
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

          {isAsking && mode === 'agent' && agentStep >= 0 && <AgentProgress activeStep={agentStep} />}
          {isAsking && mode !== 'agent' && <TypingIndicator />}

          <div ref={messagesEndRef} />
        </div>

        <div className="chat-controls">
          <div className="chat-settings">
            <label className="chat-settings__item">
              <span className="chat-settings__label">Режим:</span>
              <select
                className="chat-settings__select"
                value={mode}
                onChange={(e) => setMode(e.target.value as typeof mode)}
              >
                <option value="auto">🤖 Auto</option>
                <option value="rag">📚 RAG</option>
                <option value="agent">🧠 Agent</option>
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
          </div>

          <form
            className="chat-input"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <input
              className="chat-input__field"
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Задайте вопрос о данных..."
              autoComplete="off"
            />
            <button className="btn btn--primary chat-input__btn" type="submit" disabled={!question.trim() || isAsking}>
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