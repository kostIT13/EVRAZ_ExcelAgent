import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, Table2, Copy } from 'lucide-react';

interface ResultTableProps {
  data: unknown[];
  onCopy: (text: string) => void;
}

export default function ResultTable({ data, onCopy }: ResultTableProps) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const rows = useMemo(() => (data as Array<Record<string, unknown>>), [data]);

  const columns = useMemo(() => {
    const cols: string[] = [];
    for (const r of rows) {
      for (const k of Object.keys(r)) {
        if (!cols.includes(k)) cols.push(k);
      }
    }
    return cols;
  }, [rows]);

  if (!rows || rows.length === 0 || columns.length === 0) return null;

  const formatCell = (v: unknown): string => {
    if (v === null || v === undefined) return '∅';
    if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toLocaleString('ru-RU');
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  };

  const copyTable = () => {
    const header = columns.join('\t');
    const body = rows.map((r) => columns.map((c) => formatCell(r[c])).join('\t')).join('\n');
    onCopy(`${header}\n${body}`);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className={`result-table${open ? ' result-table--open' : ''}`}>
      <div className="result-table__bar">
        <span className="result-table__title" onClick={() => setOpen((o) => !o)}>
          <Table2 size={14} />
          <span>Данные ({rows.length} стр.)</span>
          <ChevronDown size={16} className="result-table__chevron" />
        </span>
        <button className="result-table__copy" onClick={copyTable} title="Скопировать таблицу">
          <Copy size={13} />
          <span>{copied ? 'Скопировано' : 'CSV'}</span>
        </button>
      </div>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            className="result-table__body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
          >
            <div className="result-table__scroll">
              <table className="result-table__grid">
                <thead>
                  <tr>
                    {columns.map((c) => (
                      <th key={c}>{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      {columns.map((c) => (
                        <td key={c} className={typeof r[c] === 'number' ? 'is-num' : ''}>
                          {formatCell(r[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}