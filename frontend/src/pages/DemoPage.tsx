import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Check, Copy, LineChart, MessageSquare, Table2 } from 'lucide-react';
import { useState } from 'react';
import ResultChart from '@/components/chat/ResultChart';
import SqlBlock from '@/components/chat/SqlBlock';
import { useToast } from '@/hooks/useToast';
import { ToastContainer } from '@/components/ui/Toast';

/** Среднерыночная цена на «Лом твердых сплавов (без припоя)» по месяцам 2025 (колонка J). */
const HARD_ALLOY_SERIES = [
  { period: '2025-01', value: 2073277.5 },
  { period: '2025-02', value: 1999965.0 },
  { period: '2025-03', value: 1999965.0 },
  { period: '2025-04', value: 2023425.0 },
  { period: '2025-05', value: 1994100.0 },
  { period: '2025-06', value: 2090872.5 },
  { period: '2025-07', value: 2105535.0 },
  { period: '2025-08', value: 2134860.0 },
  { period: '2025-09', value: 2149522.5 },
  { period: '2025-10', value: 2340135.0 },
  { period: '2025-11', value: 2457435.0 },
  { period: '2025-12', value: 2697900.0 },
];

/** «Предлож. победителя» на «Лом латуни ЛАЖМц» по месяцам 2025 (колонка L). */
const BRASS_LAZH_SERIES = [
  { period: '2025-01', value: 498525.0 },
  { period: '2025-02', value: 498525.0 },
  { period: '2025-03', value: 498525.0 },
  { period: '2025-04', value: 498525.0 },
  { period: '2025-05', value: 498525.0 },
  { period: '2025-06', value: 498525.0 },
  { period: '2025-07', value: 498525.0 },
  { period: '2025-08', value: 498525.0 },
  { period: '2025-09', value: 564213.0 },
  { period: '2025-10', value: 564213.0 },
  { period: '2025-11', value: 564213.0 },
  { period: '2025-12', value: 602922.0 },
];

/** Цены «Ферроком» на все виды медного лома в феврале 2025 (колонка E). */
const FERROKOM_FEB_COPPER_ITEMS = [
  { item: 'Лом меди кусок', value: 832830.0 },
  { item: 'Лом меди микс', value: 821100.0 },
  { item: 'Лом меди в кабеле', value: 715530.0 },
  { item: 'Лом меди стружка', value: 727260.0 },
  { item: 'Лом меди трубка с оребрением', value: 582981.0 },
  { item: 'Лом меди трубка с оребрением медь 87,2%', value: 500049.9 },
];

/** Среднерыночная цена на «Лом алюминия» по месяцам 2025 (колонка J). */
const ALUMINIUM_SERIES = [
  { period: '2025-01', value: 156595.5 },
  { period: '2025-02', value: 164513.25 },
  { period: '2025-03', value: 161580.75 },
  { period: '2025-04', value: 150730.5 },
  { period: '2025-05', value: 134308.5 },
  { period: '2025-06', value: 126097.5 },
  { period: '2025-07', value: 129616.5 },
  { period: '2025-08', value: 129616.5 },
  { period: '2025-09', value: 135188.25 },
  { period: '2025-10', value: 145745.25 },
  { period: '2025-11', value: 153369.75 },
  { period: '2025-12', value: 155715.75 },
];

const MONTH_LABELS: Record<string, string> = {
  '2025-01': 'Январь',
  '2025-02': 'Февраль',
  '2025-03': 'Март',
  '2025-04': 'Апрель',
  '2025-05': 'Май',
  '2025-06': 'Июнь',
  '2025-07': 'Июль',
  '2025-08': 'Август',
  '2025-09': 'Сентябрь',
  '2025-10': 'Октябрь',
  '2025-11': 'Ноябрь',
  '2025-12': 'Декабрь',
};

interface DemoRow {
  label: string;
  value: number;
}

interface DemoClarification {
  question: string;
  answer: string;
  sql: string;
}

interface DemoItem {
  id: number;
  tag: string;
  tagAccent: 'red' | 'gold' | 'cyan' | 'green';
  question: string;
  answer: string;
  sql: string;
  clarification?: DemoClarification;
  chartTitle: string;
  chartComment: string;
  chartData: Record<string, unknown>[];
  rows: DemoRow[];
  total?: string;
}

const DEMO_ITEMS: DemoItem[] = [
  {
    id: 1,
    tag: 'Поиск значения на листе',
    tagAccent: 'red',
    question: 'Сколько составила среднерыночная цена на Лом твердых сплавов (без припоя) в декабре 2025 года?',
    answer:
      'Среднерыночная цена на лом твердых сплавов (без припоя) в декабре 2025 года составила 2 697 900 руб./тн.',
    sql: `SELECT fp.value AS среднерыночная_цена
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-12'
  AND fp.price_type = 'среднерыночная'
  AND fp.item_name = 'Лом твердых сплавов (без припоя)'
LIMIT 1`,
    chartTitle: 'Среднерыночная цена «Лом твердых сплавов (без припоя)» по месяцам 2025 г.',
    chartComment: 'Динамика цены за январь–декабрь 2025; максимум — в декабре: 2 697 900 руб./тн.',
    chartData: HARD_ALLOY_SERIES,
    rows: HARD_ALLOY_SERIES.map((p) => ({
      label: MONTH_LABELS[p.period] ?? p.period,
      value: p.value,
    })),
  },
  {
    id: 2,
    tag: 'Агрегация: MAX за период',
    tagAccent: 'gold',
    question:
      'Какова была максимальная цена по результатам предложения победителя на аукционе за Лом латуни ЛАЖМц в январе 2025 - декабре 2025 года?',
    answer:
      'Максимальная цена по результатам предложения победителя на аукционе за лом латуни ЛАЖМц в период с января по декабрь 2025 года составила 602 922 руб./тн.',
    sql: `SELECT MAX(fp.value) AS максимальная_цена
FROM mart.price_facts fp
WHERE fp.item_name = 'Лом латуни ЛАЖМц'
  AND fp.price_type = 'аукцион_победитель'
  AND fp.sheet_period BETWEEN '2025-01' AND '2025-12'`,
    chartTitle: 'Предложение победителя на аукционе за «Лом латуни ЛАЖМц» по месяцам 2025 г.',
    chartComment:
      'Цена 498 525 руб./тн держалась с января по август, с сентября выросла; максимум — декабрь: 602 922 руб./тн.',
    chartData: BRASS_LAZH_SERIES,
    rows: BRASS_LAZH_SERIES.map((p) => ({
      label: MONTH_LABELS[p.period] ?? p.period,
      value: p.value,
    })),
  },
  {
    id: 3,
    tag: 'Расчёт среднего по группе',
    tagAccent: 'cyan',
    question: 'Какова была средняя цена на все виды медного лома по данным Ферроком в феврале 2025 года?',
    answer:
      'Средняя цена на все виды медного лома по данным компании Ферроком в феврале 2025 года составила 696 625,15 руб./тн.',
    sql: `SELECT AVG(fp.value) AS средняя_цена
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-02'
  AND fp.supplier ILIKE '%ферроком%'
  AND fp.item_name ILIKE 'Лом меди%'
  AND fp.price_type = 'поставщик'
  AND fp.value IS NOT NULL`,
    chartTitle: 'Цены Ферроком на виды медного лома в феврале 2025 г.',
    chartComment:
      'Среднее по 6 заполненным позициям: (832 830 + 821 100 + 715 530 + 727 260 + 582 981 + 500 049,9) / 6 = 696 625,15 руб./тн.',
    chartData: FERROKOM_FEB_COPPER_ITEMS,
    rows: FERROKOM_FEB_COPPER_ITEMS.map((p) => ({
      label: p.item,
      value: p.value,
    })),
    total: 'Средняя цена: 696 625,15 руб./тн',
  },
  {
    id: 4,
    tag: 'Диалог: уточнение периода',
    tagAccent: 'green',
    question: 'Сколько составила среднерыночная цена на Лом алюминия в ноябре 2025 года?',
    answer:
      'Среднерыночная цена на лом алюминия в ноябре 2025 года составила 153 369,75 руб./тн.',
    clarification: {
      question: 'А в декабре?',
      answer:
        'Среднерыночная цена на лом алюминия в декабре 2025 года составила 155 715,75 руб./тн.',
      sql: `SELECT fp.value AS среднерыночная_цена
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-12'
  AND fp.price_type = 'среднерыночная'
  AND fp.item_name = 'Лом алюминия'
LIMIT 1`,
    },
    sql: `SELECT fp.value AS среднерыночная_цена
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-11'
  AND fp.price_type = 'среднерыночная'
  AND fp.item_name = 'Лом алюминия'
LIMIT 1`,
    chartTitle: 'Среднерыночная цена «Лом алюминия» по месяцам 2025 г.',
    chartComment:
      'Первый запрос — ноябрь: 153 369,75 руб./тн. Уточнение «А в декабре?» агент обрабатывает с учётом контекста диалога: 155 715,75 руб./тн (декабрь).',
    chartData: ALUMINIUM_SERIES,
    rows: ALUMINIUM_SERIES.map((p) => ({
      label: MONTH_LABELS[p.period] ?? p.period,
      value: p.value,
    })),
  },
];

const fmtPrice = (v: number) =>
  `${v.toLocaleString('ru-RU', { maximumFractionDigits: 2, minimumFractionDigits: 0 })} руб./тн`;

export default function DemoPage() {
  const navigate = useNavigate();
  const { toasts, showToast, dismiss } = useToast();
  const [copiedId, setCopiedId] = useState<number | null>(null);

  const copyQuestion = (id: number, text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(id);
      showToast('Запрос скопирован в буфер обмена', 'success');
      window.setTimeout(() => setCopiedId(null), 1600);
    });
  };

  const copySql = (sqlText: string) => {
    navigator.clipboard.writeText(sqlText).then(() => {
      showToast('SQL запрос скопирован', 'success');
    });
  };

  const openInChat = (question: string) => {
    navigate(`/?q=${encodeURIComponent(question)}`);
  };

  return (
    <div className="demo">
      <motion.div
        className="demo__head"
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <h2 className="demo__title">Демо: запросы с графиками и SQL</h2>
        <p className="demo__subtitle">
          Четыре демонстрации: значение на листе, максимум за период, средняя цена по группе и диалоговое уточнение.
          Каждый пример сопровождается ответом агента, сгенерированным SQL-запросом и графиком на основе данных.
        </p>
      </motion.div>

      <div className="demo__grid">
        {DEMO_ITEMS.map((item, idx) => (
          <motion.article
            key={item.id}
            className="demo-card"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: idx * 0.12 }}
          >
            <div className="demo-card__head">
              <span className={`demo-card__badge demo-card__badge--${item.tagAccent}`}>
                #{item.id} · {item.tag}
              </span>
              <div className="demo-card__actions">
                <button
                  type="button"
                  className="demo-card__copy"
                  onClick={() => copyQuestion(item.id, item.question)}
                  title="Скопировать запрос"
                >
                  {copiedId === item.id ? <Check size={15} /> : <Copy size={15} />}
                </button>
                <button
                  type="button"
                  className="demo-card__chat"
                  onClick={() => openInChat(item.question)}
                  title="Перейти в чат и задать вопрос"
                >
                  <MessageSquare size={15} />
                  <span>В чат</span>
                </button>
              </div>
            </div>

            <h3 className="demo-card__question">{item.question}</h3>

            <div className="demo-card__answer">
              <span className="demo-card__answer-label">Ответ агента:</span>
              <span className="demo-card__answer-value">{item.answer}</span>
            </div>

            {item.clarification && (
              <div className="demo-card__clarify">
                <div className="demo-card__clarify-q">
                  <MessageSquare size={14} />
                  <span>{item.clarification.question}</span>
                </div>
                <div className="demo-card__clarify-a">
                  <span className="demo-card__answer-label">Уточнение:</span>
                  <span className="demo-card__answer-value">{item.clarification.answer}</span>
                </div>
              </div>
            )}

            <div className="demo-card__body">
              <div className="demo-card__chart">
                <div className="demo-card__row-title">
                  <LineChart size={16} />
                  <span>{item.chartTitle}</span>
                </div>
                <div className="demo-card__chart-canvas">
                  <ResultChart data={item.chartData} />
                </div>
                <p className="demo-card__chart-comment">{item.chartComment}</p>
              </div>

              <div className="demo-card__table">
                <div className="demo-card__row-title">
                  <Table2 size={16} />
                  <span>Значения</span>
                </div>
                <div className="demo-card__table-scroll">
                  <table className="demo-table">
                    <thead>
                      <tr>
                        <th>{item.id === 3 ? 'Вид лома' : 'Месяц'}</th>
                        <th>Цена, руб./тн</th>
                      </tr>
                    </thead>
                    <tbody>
                      {item.rows.map((r) => (
                        <tr key={r.label}>
                          <td>{r.label}</td>
                          <td className="demo-table__num">{fmtPrice(r.value)}</td>
                        </tr>
                      ))}
                    </tbody>
                    {item.total && (
                      <tfoot>
                        <tr>
                          <td colSpan={2}>{item.total}</td>
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              </div>
            </div>

            <div className="demo-card__sql">
              <SqlBlock sql={item.sql} onCopy={copySql} />
              {item.clarification && (
                <div className="demo-card__sql-secondary">
                  <span className="demo-card__sql-check">SQL запрос (уточнение)</span>
                  <SqlBlock sql={item.clarification.sql} onCopy={copySql} />
                </div>
              )}
            </div>
          </motion.article>
        ))}
      </div>

      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}