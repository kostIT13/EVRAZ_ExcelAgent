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

/** Февраль 2025: максимум по видам медного лома у каждого из 4 поставщиков. */
const FEB_COPPER_SUPPLIER_MAX = [
  { supplier: 'Шами-сервис', value: 938400.0 },
  { supplier: 'Сплав-21', value: 929016.0 },
  { supplier: 'ЦветМет', value: 926670.0 },
  { supplier: 'Ферроком', value: 832830.0 },
];

/** Среднерыночная цена на «Лом цинка» по месяцам 2025 (колонка J). */
const ZINC_SERIES = [
  { period: '2025-01', value: 175950.0 },
  { period: '2025-02', value: 170085.0 },
  { period: '2025-03', value: 170085.0 },
  { period: '2025-04', value: 181815.0 },
  { period: '2025-05', value: 181815.0 },
  { period: '2025-06', value: 181815.0 },
  { period: '2025-07', value: 181815.0 },
  { period: '2025-08', value: 187680.0 },
  { period: '2025-09', value: 175950.0 },
  { period: '2025-10', value: 164220.0 },
  { period: '2025-11', value: 164220.0 },
  { period: '2025-12', value: 164220.0 },
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
  tagAccent: 'red' | 'gold' | 'cyan' | 'green' | 'blue';
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

type PmiStatus = 'pass' | 'warn' | 'todo';

interface PmiItem {
  code: string;
  title: string;
  annex: string;
  status: PmiStatus;
  steps: string[];
  criterion: string;
  note?: string;
  linkLabel?: string;
  linkTo?: string;
}

const chatQ = (question: string) => `/?q=${encodeURIComponent(question)}`;

const PMI_ITEMS: PmiItem[] = [
  {
    code: 'Ф-1',
    title: 'Загрузка и регистрация файлов',
    annex: 'А-1, А-2',
    status: 'pass',
    steps: [
      'Загрузить data_proportional_prices.xlsx во вкладке «Файлы»',
      'Загрузить повторно — дубль не создаётся (дедуп по хэшу)',
      'Загрузить .docx / повреждённый .xlsx — отклонение с понятным сообщением',
      'Хэш исходного файла не изменяется',
    ],
    criterion: 'Файл зарегистрирован, 12 листов распознаны, статус «processed», 0 аварий',
    linkLabel: 'Открыть «Файлы»',
    linkTo: '/files',
  },
  {
    code: 'Ф-2',
    title: 'Выбор данных / автоопределение листов',
    annex: 'А-3',
    status: 'pass',
    steps: [
      'Задать вопрос по выбранному файлу и листу',
      'Задать тот же вопрос без выбора файла',
    ],
    criterion: 'Релевантные листы определены автоматически и указаны в источниках ответа',
    linkLabel: 'Спросить в чате',
    linkTo: chatQ('Сколько составила среднерыночная цена на Лом твердых сплавов (без припоя) в декабре 2025 года?'),
  },
  {
    code: 'Ф-3',
    title: 'Разбор сложного макета и нормализация',
    annex: 'А-4',
    status: 'pass',
    steps: [
      'Загрузить Faked-книгу (многострочные шапки, матрицы 67/146 колонок)',
      'Загрузить её повторно — разбор переиспользуется',
    ],
    criterion: 'Колонки и типы совпадают; в журнале — «Template reuse» (переиспользование разбора)',
    linkLabel: 'Открыть «Файлы»',
    linkTo: '/files',
  },
  {
    code: 'Ф-4',
    title: 'Модель через конфигурацию, без правки кода',
    annex: 'А-5',
    status: 'warn',
    steps: [
      'Изменить в .env идентификатор модели / temperature / таймаут',
      'docker compose restart service',
      'git status — код не изменён',
    ],
    criterion: 'Ответ получен с новыми параметрами (видно в трейсе), код не менялся',
    note: 'Для демо: вариант со скриншотами «до/после» + git status',
  },
  {
    code: 'Ф-5',
    title: 'Расчёты всех типов по 5 задачам Заказчика',
    annex: 'А-6',
    status: 'pass',
    steps: [
      'Прогнать python benchmark/run_first5.py',
      'Сверить ответы с эталонами docs/request_examples.txt',
    ],
    criterion: '5 из 5 ответов совпали с эталоном — PASS RATE 100 %',
    note: 'Карточки №1–№5 выше — эти же задачи с ответами и SQL',
    linkLabel: 'Карточки выше',
    linkTo: '/demo',
  },
  {
    code: 'Ф-6',
    title: 'Вычисления только через SQL, проверка и автокоррекция',
    annex: 'А-7',
    status: 'pass',
    steps: [
      'Открыть трейсы ответов — в каждом выполненный SQL',
      'pytest tests/test_codegen_helpers.py tests/test_agent_helpers.py — SQL с ошибками отклоняется до выполнения',
    ],
    criterion: 'SQL во всех трассах; некорректный SQL отклонён; self-correction до 3 попыток',
    note: 'Тесты: 30 passed',
    linkLabel: 'Открыть трейсы',
    linkTo: '/trace',
  },
  {
    code: 'Ф-7',
    title: 'Сопоставление сущностей, итоги, единицы',
    annex: 'А-8',
    status: 'pass',
    steps: ['Вопрос по категории «все виды медного лома» за период на листе с итоговыми строками'],
    criterion: '696 625,15 руб./тн — эталон; ИТОГО/ВСЕГО исключены (is_blank=0 в SQL), единица указана',
    linkLabel: 'Спросить в чате',
    linkTo: chatQ('Какова была средняя цена на все виды медного лома по данным Ферроком в феврале 2025 года?'),
  },
  {
    code: 'Ф-8',
    title: 'Уточнение неоднозначного вопроса',
    annex: 'А-9',
    status: 'pass',
    steps: ['Задать вопрос без периода: «Какая цена у поставщика Ферроком?»'],
    criterion: 'Уточняющий вопрос (waiting_for_input) или ответ с явно названной интерпретацией («последний доступный период — декабрь 2025»)',
    linkLabel: 'Спросить в чате',
    linkTo: chatQ('Какая цена у поставщика Ферроком?'),
  },
  {
    code: 'Ф-9',
    title: 'История, SQL, источники, трасса шагов',
    annex: 'А-10',
    status: 'pass',
    steps: [
      'Открыть ответ в чате — SQL-блок и источники (файл · лист · период)',
      'Открыть трейс — шаги classifier → planner → codegen → executor → verifier → answer',
    ],
    criterion: 'Шаги агента с входами/результатами/длительностью; вопрос в истории диалога',
    linkLabel: 'Открыть трейсы',
    linkTo: '/trace',
  },
  {
    code: 'Ф-10',
    title: 'Таблица, линейный и столбчатый графики',
    annex: 'А-11',
    status: 'pass',
    steps: [
      '«Построй линейный график динамики цены … по месяцам»',
      '«Построй столбчатую диаграмму … по поставщикам»',
      'Кнопка «Сделай график» под ответом',
    ],
    criterion: 'Оба типа графиков построены (по запросу и по кнопке), значения равны табличным',
    linkLabel: 'Спросить в чате',
    linkTo: chatQ('Построй линейный график динамики среднерыночной цены на Лом алюминия по месяцам 2025 года'),
  },
  {
    code: 'Ф-11',
    title: 'Краткие аналитические выводы',
    annex: 'А-11',
    status: 'pass',
    steps: ['Прочитать текстовый вывод агента к графикам Ф-10'],
    criterion: 'Вывод о динамике/лидерах (min/max, тренд) не противоречит результату',
    linkLabel: 'Спросить в чате',
    linkTo: chatQ('Покажи динамику среднерыночной цены на Лом алюминия по месяцам за весь 2025 год'),
  },
  {
    code: 'Ф-12',
    title: 'Журнал запросов, воспроизводимость, удаление',
    annex: 'А-12',
    status: 'warn',
    steps: [
      'Открыть журнал запросов (query_logs) и метрики',
      'Удалить файл кнопкой «Удалить», задать вопрос по нему',
    ],
    criterion: 'Поля журнала заполнены (статус, латентность, SQL, трейс); токены — в Prometheus/Grafana; данные удалены',
    note: 'Отдельные колонки tokens/prompt_version в query_logs не заведены',
    linkLabel: 'Открыть метрики',
    linkTo: '/metrics',
  },
  {
    code: 'Ф-13',
    title: 'Ход выполнения долгого запроса',
    annex: 'А-13',
    status: 'pass',
    steps: ['Задать многошаговый вопрос по нескольким листам (сравнение поставщиков за период)'],
    criterion: 'Ход выполнения виден (AgentProgress), интерфейс не блокируется',
    linkLabel: 'Спросить в чате',
    linkTo: chatQ('Какова была дельта между минимальной и максимальной ценой на все виды медного лома по данным Ферроком, Сплав-21, ЦветМет, шами-сервис, в феврале 2025 года?'),
  },
  {
    code: 'К-1',
    title: 'Доля правильных ответов на бенчмарке ≥ 80 %',
    annex: 'А-16',
    status: 'todo',
    steps: ['python benchmark/run_all.py на зафиксированном наборе (новая сессия на каждый вопрос)'],
    criterion: 'PASS RATE ≥ 80 %; отчёт benchmark/results/run_all_<timestamp>.json',
    note: 'Контрольный прогон run_first5: 5/5 (100 %)',
    linkLabel: 'Открыть метрики',
    linkTo: '/metrics',
  },
  {
    code: 'К-2',
    title: 'Доля правильных по каждому типу вопросов ≥ 80 %',
    annex: 'А-16',
    status: 'todo',
    steps: ['Разбить результаты run_all по типам: lookup / max-min / агрегат / дельта / сравнение листов'],
    criterion: 'По каждому типу ≥ 80 %',
    note: 'Разбивка — из JSON-отчёта по полю query_type',
  },
  {
    code: 'К-3',
    title: 'Результат относительно связок Заказчика',
    annex: 'А-16',
    status: 'todo',
    steps: ['Сравнить PASS RATE прогона с результатами текущих связок Заказчика'],
    criterion: 'Не ниже 60 % от результата связок / не менее 60 % абсолютных',
    note: 'Связки Заказчика предоставляются отдельно',
  },
];

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
    tag: 'Агрегация: дельта MIN/MAX по 4 поставщикам',
    tagAccent: 'green',
    question:
      'Какова была дельта между минимальной и максимальной ценой на все виды медного лома по данным Ферроком, Сплав-21, ЦветМет, шами-сервис, в феврале 2025 года?',
    answer:
      'Дельта между минимальной и максимальной ценой на все виды медного лома по данным поставщиков Ферроком, Сплав-21, ЦветМет и шами-сервис в феврале 2025 года составила 438 350,10 руб./тн.',
    sql: `SELECT MAX(fp.value) - MIN(fp.value) AS дельта
FROM mart.price_facts fp
WHERE fp.sheet_period = '2025-02'
  AND fp.price_type = 'поставщик'
  AND fp.item_name ILIKE 'Лом меди%'
  AND fp.value IS NOT NULL
  AND (
    fp.supplier ILIKE '%ферроком%'
    OR fp.supplier ILIKE '%сплав-21%'
    OR fp.supplier ILIKE '%сплав21%'
    OR fp.supplier ILIKE '%цветмет%'
    OR fp.supplier ILIKE '%шами-сервис%'
  )`,
    chartTitle: 'Максимум по видам медного лома у каждого поставщика — февраль 2025 г.',
    chartComment:
      'Максимум — 938 400 руб./тн (Шами-сервис, «Лом меди кусок»); минимум — 500 049,90 руб./тн (Ферроком, «Лом меди трубка с оребрением медь 87,2 %»). Дельта: 938 400 − 500 049,90 = 438 350,10 руб./тн.',
    chartData: FEB_COPPER_SUPPLIER_MAX,
    rows: FEB_COPPER_SUPPLIER_MAX.map((p) => ({
      label: p.supplier,
      value: p.value,
    })),
    total: 'Дельта min/max: 438 350,10 руб./тн',
  },
  {
    id: 5,
    tag: 'Сравнение листов: MIN за все месяцы',
    tagAccent: 'blue',
    question: 'Какова была минимальная цена на цинковый лом за все месяцы?',
    answer:
      'Минимальная среднерыночная цена на цинковый лом за все месяцы составила 164 220,00 руб./тн.',
    sql: `SELECT MIN(fp.value) AS минимальная_цена
FROM mart.price_facts fp
WHERE fp.sheet_period LIKE '2025-%'
  AND fp.price_type = 'среднерыночная'
  AND fp.item_name ILIKE 'Лом цинка%'`,
    chartTitle: 'Среднерыночная цена «Лом цинка» по месяцам 2025 г.',
    chartComment:
      'Минимум зафиксирован в октябре–декабре 2025: 164 220 руб./тн; максимум — август: 187 680 руб./тн. Агрегат MIN собран по всем 12 месячным листам сразу.',
    chartData: ZINC_SERIES,
    rows: ZINC_SERIES.map((p) => ({
      label: MONTH_LABELS[p.period] ?? p.period,
      value: p.value,
    })),
    total: 'Минимум за все месяцы: 164 220,00 руб./тн',
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
          Пять демонстраций — контрольные вопросы бенчмарка: значение на листе, максимум за период,
          средняя цена по группе, дельта min/max по поставщикам и минимум за все месяцы.
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

      <motion.div
        className="pmi__head"
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        <h2 className="demo__title">Протокол приёмочных испытаний (ПМИ)</h2>
        <p className="demo__subtitle">
          Все 16 пунктов протокола (Ф-1…Ф-13, К-1…К-3) по приложению Б ПМИ:
          шаги проверки, критерий приёмки и статус по итогам прогона-репетиции.
          Пункты со ссылками открываются в соответствующем разделе системы.
        </p>
        <div className="pmi__summary">
          <span className="pmi__summary-item pmi__summary-item--pass">Пройдено: {PMI_ITEMS.filter((p) => p.status === 'pass').length}</span>
          <span className="pmi__summary-item pmi__summary-item--warn">С оговоркой: {PMI_ITEMS.filter((p) => p.status === 'warn').length}</span>
          <span className="pmi__summary-item pmi__summary-item--todo">Предстоит: {PMI_ITEMS.filter((p) => p.status === 'todo').length}</span>
        </div>
      </motion.div>

      <div className="pmi__grid">
        {PMI_ITEMS.map((item, idx) => (
          <motion.article
            key={item.code}
            className={`pmi-card pmi-card--${item.status}`}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 + idx * 0.05 }}
          >
            <div className="pmi-card__head">
              <span className={`pmi-card__badge pmi-card__badge--${item.status}`}>
                {item.status === 'pass' ? '✓' : item.status === 'warn' ? '⚠' : '□'} {item.code}
              </span>
              <span className="pmi-card__annex">{item.annex}</span>
            </div>

            <h3 className="pmi-card__title">{item.title}</h3>

            <ol className="pmi-card__steps">
              {item.steps.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>

            <div className="pmi-card__criterion">
              <span className="pmi-card__criterion-label">Критерий:</span>
              <span>{item.criterion}</span>
            </div>

            {item.note && (
              <div className="pmi-card__note">{item.note}</div>
            )}

            {item.linkTo && item.linkLabel && (
              <button
                type="button"
                className="pmi-card__link"
                onClick={() => navigate(item.linkTo as string)}
              >
                {item.linkLabel} →
              </button>
            )}
          </motion.article>
        ))}
      </div>

      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}