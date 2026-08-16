import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, Copy, Check, Database } from 'lucide-react';

const SQL_KEYWORDS = new Set([
  'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'LIKE', 'ILIKE',
  'GROUP', 'BY', 'ORDER', 'HAVING', 'LIMIT', 'OFFSET', 'AS', 'DISTINCT',
  'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER', 'ON', 'BETWEEN', 'IS', 'NULL',
  'AVG', 'SUM', 'MIN', 'MAX', 'COUNT', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
  'EXISTS', 'ANY', 'ALL', 'ARRAY', 'ASC', 'DESC', 'COALESCE', 'ROUND', 'CAST',
]);

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>');
}

/**
 * Лёгкая подсветка SQL без внешних зависимостей.
 * Разбивает SQL на токены: строки, числа, ключевые слова, комментарии.
 */
function highlightSql(sql: string): string {
  const escaped = escapeHtml(sql);
  const parts = escaped.split(
    /('(?:[^'\\]|\\.)*'|--[^\n]*|\b\d+(?:\.\d+)?\b|\b[A-ZА-ЯЁ]+\b)/
  );

  return parts
    .map((part) => {
      if (/^'/.test(part) && /'$/.test(part)) {
        return `<span class="sql-tok sql-tok--str">${part}</span>`;
      }
      if (/^--/.test(part)) {
        return `<span class="sql-tok sql-tok--comment">${part}</span>`;
      }
      if (/^\d/.test(part)) {
        return `<span class="sql-tok sql-tok--num">${part}</span>`;
      }
      if (/^[A-ZА-ЯЁ]+$/.test(part) && SQL_KEYWORDS.has(part.toUpperCase())) {
        return `<span class="sql-tok sql-tok--kw">${part}</span>`;
      }
      return part;
    })
    .join('');
}

interface SqlBlockProps {
  sql: string;
  onCopy: (text: string) => void;
}

export default function SqlBlock({ sql, onCopy }: SqlBlockProps) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const highlighted = useMemo(() => highlightSql(sql), [sql]);

  const handleCopy = () => {
    onCopy(sql);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className={`sql-block${open ? ' sql-block--open' : ''}`}>
      <div className="sql-block__bar">
        <span className="sql-block__title" onClick={() => setOpen((o) => !o)}>
          <Database size={14} />
          <span>SQL запрос</span>
          <ChevronDown size={16} className="sql-block__chevron" />
        </span>
        <span className="sql-block__actions">
          <button className="sql-block__copy" onClick={handleCopy} title="Скопировать SQL">
            {copied ? <Check size={14} /> : <Copy size={14} />}
            <span>{copied ? 'Скопировано' : 'Копировать'}</span>
          </button>
        </span>
      </div>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            className="sql-block__body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
          >
            <pre
              className="sql-block__pre"
              dangerouslySetInnerHTML={{ __html: highlighted }}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}