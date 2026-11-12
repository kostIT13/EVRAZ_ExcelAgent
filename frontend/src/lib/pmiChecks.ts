/**
 * Автономные проверки контрольных примеров ПМИ прямо из вкладки «Демо».
 * Каждая проверка делает настоящий вызов к стенду и возвращает доказательство
 * (строки фактов) вместо «пройдено» с чужих слов.
 */
import { api } from '@/api';
import type { AskResponse, ChartPoint, FileResponse, TraceListItem } from '@/types/api';

export type CheckStatus = 'pass' | 'fail' | 'error';

/** Ряд графика, который проверка построила и выводит прямо в списке проверок (А-11). */
export interface CheckChart {
  data: ChartPoint[];
  kind?: 'line' | 'bar';
}

export interface CheckResult {
  status: CheckStatus;
  summary: string;
  lines: string[];
  at: string;
  /** request_id ответа /ask — по нему открывается трасса запроса. */
  requestId?: string;
  chart?: CheckChart;
}

export interface AskCase {
  question: string;
  expect: number;
  label?: string;
}

export interface CheckParams {
  filename?: string;
  sheets?: number;
  hashStart?: string;
  question?: string;
  followUp?: string;
  expect?: number;
  tolPct?: number;
  sqlIncludes?: string[];
  answerIncludes?: string[];
  requireSources?: boolean;
  items?: AskCase[];
  passRatePct?: number;
  attacks?: string[];
  nodes?: string[];
  expectNoData?: boolean;
  minPass?: number;
  /** Обязательные значения конфигурации модели (А-13: повторы и таймаут заданы настройкой). */
  expectConfig?: Record<string, number | string>;
  /** Достаточно любого из перечисленных вхождений в тексте ответа (регистр не важен). */
  anyOf?: string[];
  /** Проверять ответ по правилу неоднозначного вопроса: уточнение либо явная интерпретация. */
  clarify?: boolean;
  /**
   * Источники ответа должны покрывать не менее min периодов с этим префиксом.
   * А-3: вопрос без периода — автовыбор месячных листов виден именно в источниках,
   * потому что SQL модель строит без литерала периода (MAX / ORDER BY DESC).
   */
  sourcesPeriods?: { prefix: string; min: number };
}

export type CheckKind =
  | 'health'
  | 'filesRegistered'
  | 'uploadIdempotent'
  | 'rejectBadUploads'
  | 'columnsParsed'
  | 'llmConfigDiff'
  | 'llmConfigValues'
  | 'clearCache'
  | 'askNumber'
  | 'askBatch'
  | 'askChart'
  | 'askClarify'
  | 'askNoData'
  | 'askAttacks'
  | 'askJournal'
  | 'traceNodes'
  | 'journalEvidence'
  | 'metricsTokens'
  | 'noSecretInConfig'
  | 'openapiAvailable'
  | 'deleteFile';

export interface CheckDef {
  id: string;
  title: string;
  kind: CheckKind;
  /** Что обязано выполняться — формулировка критерия для этой проверки. */
  criterion: string;
  params?: CheckParams;
  /** Требует обращения к модели — десятки секунд. */
  slow?: boolean;
  /** Удаляет данные — запускается только с явного разрешения. */
  destructive?: boolean;
  /** Нужен выбранный оператором файл (эталонный .xlsx). */
  needsFile?: boolean;
}

export interface CheckContext {
  /** Файл, выбранный оператором в карточке (для проверок загрузки). */
  file?: File | null;
  /** Разрешение на разрушительные проверки (удаление файла). */
  allowDestructive?: boolean;
  onProgress?: (message: string) => void;
}

const API_BASE = '/api';
/** Ответ /ask ждём дольше всего: агент делает несколько вызовов модели подряд. */
const ASK_TIMEOUT_MS = 280_000;
const NO_DATA_MARKERS = [
  'не вернул данных',
  'не найдено',
  'не найдена',
  'не найдены',
  'не обнаружено',
  'не обнаружен',
  'данных нет',
  'нет данных',
  'не удалось получить',
  'не удалось найти',
];

function stamp(): string {
  return new Date().toLocaleTimeString('ru-RU');
}

function pass(
  summary: string,
  lines: string[] = [],
  requestId?: string,
  chart?: CheckChart,
): CheckResult {
  return {
    status: 'pass',
    summary,
    lines,
    at: stamp(),
    ...(requestId ? { requestId } : {}),
    ...(chart ? { chart } : {}),
  };
}

function fail(summary: string, lines: string[] = [], requestId?: string): CheckResult {
  return { status: 'fail', summary, lines, at: stamp(), ...(requestId ? { requestId } : {}) };
}

function err(summary: string, e: unknown): CheckResult {
  const message = String((e as Error)?.message ?? e);
  const detailed = /failed to fetch|networkerror|load failed/i.test(message)
    ? 'стенд недоступен — проверьте docker compose ps и адрес API'
    : message;
  return { status: 'error', summary: `${summary}: ${detailed}`, lines: [], at: stamp() };
}

export function fmt(n: number): string {
  return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
}

interface RawResponse {
  status: number;
  ok: boolean;
  text: string;
  json: Record<string, unknown> | null;
}

async function raw(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<RawResponse> {
  const init: RequestInit = { method, headers: { Accept: 'application/json' }, signal };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.headers = { ...init.headers, 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE}${path}`, init);
  const text = await res.text();
  let json: Record<string, unknown> | null = null;
  try {
    json = JSON.parse(text) as Record<string, unknown>;
  } catch {
    json = null;
  }
  return { status: res.status, ok: res.ok, text, json };
}

/** POST /ask с историей диалога; возвращает и HTTP-статус, и тело. */
async function ask(
  question: string,
  history: { role: 'user' | 'assistant'; content: string }[] = [],
  signal?: AbortSignal,
): Promise<RawResponse> {
  // Агент идёт к модели несколько раз подряд; nginx обрывает прокси на 300 с,
  // поэтому свой таймаут ставим чуть меньше — иначе висел бы бесконечно.
  const own = signal ?? timeoutSignal(ASK_TIMEOUT_MS);
  try {
    return await raw(
      'POST',
      '/ask',
      {
        question,
        mode: 'agent',
        response_mode: 'detailed',
        conversation_history: history,
        conversation_id: null,
      },
      own,
    );
  } catch (e) {
    if (isTimeout(e)) throw new Error(`нет ответа за ${ASK_TIMEOUT_MS / 1000} с`);
    throw e;
  }
}

function timeoutSignal(ms: number): AbortSignal | undefined {
  return typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function'
    ? AbortSignal.timeout(ms)
    : undefined;
}

function isTimeout(e: unknown): boolean {
  const name = (e as Error)?.name ?? '';
  return name === 'TimeoutError' || name === 'AbortError';
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

/** Разбор файла асинхронный: ждём итогового статуса, чтобы не сравнивать «на лету». */
async function waitFileSettled(
  fileId: number,
  onProgress?: (message: string) => void,
  timeoutMs = 180_000,
): Promise<FileResponse> {
  const deadline = Date.now() + timeoutMs;
  let file = await api.getFile(fileId);
  while (file.status !== 'processed' && file.status !== 'error' && Date.now() < deadline) {
    onProgress?.(`Разбираем ${file.filename}… статус ${file.status}`);
    await sleep(2500);
    file = await api.getFile(fileId);
  }
  return file;
}

function asAsk(json: Record<string, unknown> | null): AskResponse | null {
  return (json as unknown as AskResponse) ?? null;
}

/** Ответ /ask обязан развернуться в AskResponse — иначе проверка не о чём. */
function requireAsk(res: RawResponse): AskResponse {
  const a = asAsk(res.json);
  if (!a || typeof a.answer !== 'string')
    throw new Error(`ответ /ask не разобран: HTTP ${res.status} · ${res.text.slice(0, 120)}`);
  return a;
}

/** HTTP-ошибка с расшифровкой частых случаев (429 — лимит запросов). */
function httpHint(res: RawResponse): [string, string[]] {
  const text = res.text.replace(/\s+/g, ' ').trim().slice(0, 180);
  if (res.status === 429)
    return ['HTTP 429 — лимит запросов', [text, 'RATE_LIMIT_ASK по умолчанию 30/мин: поднимите в .env и пересоздайте контейнер']];
  return [`HTTP ${res.status}`, [text]];
}

/** Числа из текста ответа: «2 697 900», «696 625,15», «−879,75»; марки типа «Б83» отсекаются. */
export function numbersIn(text: string): number[] {
  let norm = text.replace(/[\u00a0\u202f]/g, ' ');
  while (/\d[ ](?=\d{3}(\D|$))/.test(norm)) {
    norm = norm.replace(/(\d)[ ](?=\d{3}(\D|$))/g, '$1');
  }
  const out: number[] = [];
  const re = /[-−]?\d+(?:[.,]\d+)?/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(norm))) {
    const prev = norm[m.index - 1];
    if (prev && /[0-9A-Za-zА-Яа-яЁё]/.test(prev)) continue;
    const value = Number.parseFloat(m[0].replace('−', '-').replace(',', '.'));
    if (Number.isFinite(value)) out.push(value);
  }
  return out;
}

export function findMatch(numbers: number[], expect: number, tolPct: number): number | undefined {
  const tol = (Math.abs(expect) * tolPct) / 100;
  return numbers.find((n) => Math.abs(n - expect) <= Math.max(tol, 0.01));
}

/**
 * Поиск файла по подстроке имени. Если имя задано и совпадения нет — возвращаем
 * undefined: подставлять первый попавшийся файл нельзя, проверки по А-4 и
 * разрушительное удаление в А-12 иначе считаются по чужому файлу.
 */
function pickFile(files: FileResponse[], name?: string): FileResponse | undefined {
  if (!files.length) return undefined;
  if (!name) return files[0];
  const needle = name.toLowerCase();
  return files.find((f) => f.filename.toLowerCase().includes(needle));
}

function sqlHas(sql: string | undefined | null, needles: string[]): string[] {
  const lower = (sql ?? '').toLowerCase();
  return needles.filter((n) => !lower.includes(n.toLowerCase()));
}

async function checkHealth(): Promise<string[]> {
  const health = await api.checkHealth();
  const entries = Object.entries(health);
  return entries.length ? entries.map(([k, v]) => `${k}: ${String(v)}`) : ['backend отвечает'];
}

async function runCheckImpl(check: CheckDef, ctx: CheckContext): Promise<CheckResult> {
  const p = check.params ?? {};
  const tol = p.tolPct ?? 1;

  switch (check.kind) {
    case 'health': {
      const lines = await checkHealth();
      return pass('Сервис отвечает', lines);
    }

    case 'filesRegistered': {
      const res = await api.listFiles({ limit: 50 });
      const file = pickFile(res.files, p.filename);
      if (!file) return fail('Файл не найден на стенде', [`зарегистрировано файлов: ${res.total}`]);
      const lines = [
        `${file.filename} · статус ${file.status} · листов ${file.total_sheets}`,
        `SHA-256 ${file.file_hash}`,
      ];
      const problems: string[] = [];
      if (file.status === 'processed') {
        try {
          const sheets = await api.getFileSheets(file.id);
          const periods = [...new Set(sheets.map((s) => s.period).filter(Boolean))].sort();
          lines.push(
            `листов в реестре: ${sheets.length} · периодов извлечено: ${periods.length}` +
              (periods.length ? ` (${periods[0]} … ${periods[periods.length - 1]})` : ''),
          );
          lines.push(`строк по листам: ${sheets.reduce((n, s) => n + s.row_count, 0)}`);
        } catch (e) {
          lines.push(`листы не читаются: ${String((e as Error).message)}`);
        }
      }
      // total_rows в реестре файлов разбор не заполняет (колонка default 0) —
      // объём витрины подтверждается отдельной командой psql, не этим полем.
      if (!file.total_rows) lines.push('поле total_rows реестра не заполнено — объём витрины сверяется запросом к mart.price_facts');
      if (p.sheets && file.total_sheets < p.sheets)
        problems.push(`листов ${file.total_sheets}, ожидалось ≥ ${p.sheets}`);
      if (p.hashStart && !file.file_hash.startsWith(p.hashStart))
        problems.push(`хэш начинается не с ${p.hashStart}`);
      if (file.status !== 'processed') problems.push(`статус ${file.status}, ожидался processed`);
      return problems.length ? fail('Файл зарегистрирован не полностью', [...lines, ...problems]) : pass('Файл зарегистрирован и разобран', lines);
    }

    case 'uploadIdempotent': {
      if (!ctx.file) return fail('Не выбран файл', ['выберите эталонный .xlsx в карточке и повторите запуск']);
      const before = await api.listFiles({ limit: 50 });
      ctx.onProgress?.(`Загружаем ${ctx.file.name}…`);
      const first = await api.uploadFile(ctx.file);
      // Разбор асинхронный: без ожидания итогового статуса второй запрос мог бы
      // уйти до фиксации первой записи и дать ложный дубль.
      const settled = await waitFileSettled(first.file.id, ctx.onProgress);
      ctx.onProgress?.('Повторная загрузка того же файла…');
      const second = await api.uploadFile(ctx.file);
      const after = await api.listFiles({ limit: 50 });
      const lines = [
        `до: ${before.total} · после первой: id ${first.file.id} · после второй: id ${second.file.id}`,
        `после двух загрузок зарегистрировано файлов: ${after.total}`,
        `хэш: ${first.file.file_hash}`,
        `листов ${settled.total_sheets} · статус ${settled.status}`,
      ];
      if (first.file.id !== second.file.id)
        return fail('Создан дубль: повторная загрузка вернула другой id', lines);
      if (after.total !== before.total)
        return fail('Число зарегистрированных файлов выросло', lines);
      if (first.file.file_hash !== second.file.file_hash)
        return fail('Хэш не совпал при повторной загрузке', lines);
      if (settled.status === 'error') return fail('Файл не разобран', [...lines, settled.error_message ?? '']);
      return pass('Дубль не создан, хэш тот же', lines);
    }

    case 'rejectBadUploads': {
      // Битый workbook парится до регистрации файла, поэтому ожидаем 400 прямо на
      // загрузке; ветка 201 → status=error остаётся для книг, которые разбираются,
      // но падают при нормализации.
      const attempts = [
        { name: 'ПМИ_тест.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', size: 256, fill: 65, late: false },
        { name: 'huge_51mib.xlsx', type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', size: 51 * 1024 * 1024, fill: 66, late: false },
        { name: 'broken.xlsx', type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', size: 4096, fill: 67, late: true },
      ];
      const lines: string[] = [];
      const problems: string[] = [];
      for (const a of attempts) {
        const fd = new FormData();
        fd.append('file', new File([new Uint8Array(a.size).fill(a.fill)], a.name, { type: a.type }));
        ctx.onProgress?.(`Пробуем загрузить ${a.name}…`);
        const res = await raw('POST', '/files/upload', fd);
        const detail = (res.json?.detail as string) ?? res.text.replace(/\s+/g, ' ').trim().slice(0, 90);
        if (res.status === 429) {
          problems.push(`${a.name}: HTTP 429 — сработал лимит загрузок (RATE_LIMIT_UPLOAD), повторите через минуту`);
          lines.push(`${a.name}: HTTP 429 — ${detail}`);
          continue;
        }
        if (res.status === 400 || res.status === 413) {
          lines.push(`${a.name}: HTTP ${res.status} — ${detail}`);
          continue;
        }
        if (res.status === 201 && res.json?.file && a.late) {
          const created = (res.json.file as FileResponse).id;
          const settled = await waitFileSettled(created, ctx.onProgress, 90_000);
          lines.push(`${a.name}: HTTP 201 → статус разбора ${settled.status} — ${settled.error_message ?? 'без текста ошибки'}`);
          if (settled.status !== 'error')
            problems.push(`${a.name}: битый workbook не помечен ошибкой (статус ${settled.status})`);
          await api.deleteFile(created).catch(() => undefined);
          lines.push(`${a.name}: запись удалена с стенда`);
          continue;
        }
        problems.push(`${a.name}: HTTP ${res.status}, ожидался отказ 400/413 либо ошибка разбора`);
        lines.push(`${a.name}: HTTP ${res.status} — ${detail}`);
        const createdId = (res.json?.file as FileResponse | undefined)?.id;
        if (createdId) await api.deleteFile(createdId).catch(() => undefined);
      }
      const health = await api.checkHealth();
      lines.push(`после попыток сервис отвечает: ${JSON.stringify(health)}`);
      const list = await api.listFiles({ limit: 50 });
      const junk = list.files.filter((f) => attempts.some((a) => a.name === f.filename));
      if (junk.length) lines.push(`на стенде остались проверочные файлы: ${junk.map((f) => `${f.filename} (${f.status})`).join(', ')}`);
      return problems.length ? fail('Часть недопустимых файлов не отклонена', lines) : pass('Недопустимые файлы отклонены, сервис жив', lines);
    }

    case 'columnsParsed': {
      const files = await api.listFiles({ limit: 50 });
      const file = pickFile(files.files, p.filename);
      if (!file) return fail('Файл не найден', ['нужно загрузить книгу на страницу «Файлы»']);
      const sheets = await api.getFileSheets(file.id);
      if (!sheets.length) return fail('У файла нет листов', [`${file.filename}: листов 0`]);
      const sheet = sheets.find((s) => s.row_count > 0) ?? sheets[0];
      const columns = await api.getSheetColumns(file.id, sheet.id);
      const typed = columns.filter((c) => c.data_type && c.normalized_name);
      const lines = [
        `${file.filename} · листов ${sheets.length} · лист «${sheet.original_name}» · строк ${sheet.row_count} · период ${sheet.period ?? '—'}`,
        `колонок размечено: ${columns.length}, с типом и нормализованным именем: ${typed.length}`,
        ...columns.slice(0, 6).map((c) => `«${c.original_name}» → ${c.normalized_name} · ${c.data_type}`),
      ];
      if (!columns.length) return fail('Колонки не размечены', lines);
      if (typed.length < columns.length) return fail('Не у всех колонок есть тип/нормализованное имя', lines);
      const kinds = new Set(sheets.map((s) => s.period).filter(Boolean));
      if (kinds.size >= 2) lines.push(`периодов извлечено: ${kinds.size}`);
      return pass('Макет разобран, колонки размечены', lines);
    }

    case 'llmConfigDiff': {
      const c = await api.getLlmConfig();
      const now = `${c.model} · temperature ${c.temperature} · max_tokens ${c.max_tokens} · таймаут ${c.request_timeout_s} с · повторов ${c.llm_max_retries}`;
      const prev = readSnapshot();
      writeSnapshot(now);
      const lines = [`сейчас: ${now}`, prev ? `предыдущий снимок: ${prev}` : 'первый снимок — повторите запуск после правки .env'];
      if (!prev) return pass('Снимок конфигурации зафиксирован', lines);
      if (prev === now) return fail('Значения не изменились', [...lines, 'правьте .env и выполните docker compose up -d --force-recreate service']);
      return pass('Конфигурация изменилась без правки кода', lines);
    }

    case 'llmConfigValues': {
      const c = await api.getLlmConfig();
      const want = p.expectConfig ?? {};
      const actual = c as unknown as Record<string, number | string>;
      const lines = Object.keys(want).map(
        (k) => `${k} = ${String(actual[k] ?? 'нет поля')} · ожидалось ${String(want[k])}`,
      );
      lines.push(`модель ${c.model} · таймаут ${c.request_timeout_s} с · все значения взяты из конфигурации, не из кода`);
      const bad = Object.keys(want).filter((k) => String(actual[k]) !== String(want[k]));
      if (bad.length) return fail(`Конфигурация не совпадает: ${bad.join(', ')}`, lines);
      return pass('Повторы и таймаут заданы конфигурацией', lines);
    }

    case 'clearCache': {
      const res = await api.clearCache();
      return pass(
        res.message || 'Кэш очищен',
        [
          res.cleared
            ? `очищено ответов: ${res.cleared}`
            : 'очищено ответов: 0 — устаревших строк кэша не осталось',
        ],
      );
    }

    case 'askNumber': {
      ctx.onProgress?.('Запрос к агенту — 30–80 секунд…');
      const res = await ask(p.question ?? '');
      if (!res.ok) return fail(...httpHint(res));
      const a = requireAsk(res);
      const found = p.expect !== undefined ? findMatch(numbersIn(a.answer), p.expect, tol) : undefined;
      const lines = [
        `ответ: ${a.answer.slice(0, 220)}`,
        `статус ${a.status} · уверенность ${a.confidence} · ${a.latency_ms} мс · повторов ${a.retry_count} · ${a.query_type || '—'}`,
        `SQL: ${(a.sql_query || '—').replace(/\s+/g, ' ').slice(0, 220)}`,
      ];
      if (a.sources?.length) lines.push(`источников в ответе: ${a.sources.length}`);
      const problems: string[] = [];
      if (p.requireSources && !(a.sources?.length ?? 0))
        problems.push('в ответе нет источников (листы/колонки, по которым построен ответ)');
      if (p.expect !== undefined && found === undefined)
        problems.push(`в ответе нет значения ${fmt(p.expect)} (допуск ${tol} %)`);
      if (p.expect !== undefined && found !== undefined)
        lines.push(`значение в ответе: ${fmt(found)} · эталон ${fmt(p.expect)}`);
      if (p.sqlIncludes?.length) {
        const missing = sqlHas(a.sql_query, p.sqlIncludes);
        if (missing.length) problems.push(`в SQL нет: ${missing.join(', ')}`);
        else lines.push(`SQL содержит: ${p.sqlIncludes.join(', ')}`);
      }
      if (p.sourcesPeriods) {
        const periods = new Set<string>();
        for (const s of a.sources ?? [])
          for (const m of (s.chunk ?? '').matchAll(/\d{4}-\d{2}/g))
            if (m[0].startsWith(p.sourcesPeriods.prefix)) periods.add(m[0]);
        const foundPeriods = [...periods].sort();
        lines.push(`периоды в источниках: ${foundPeriods.length ? foundPeriods.join(' ') : 'нет'}`);
        const sql = a.sql_query ?? '';
        if (!/\d{4}-\d{2}/.test(sql) && /(MAX\s*\(|ORDER\s+BY)/i.test(sql))
          lines.push('в SQL нет литерала периода — модель ограничила выборку последним месяцем (MAX / ORDER BY DESC), месячные листы подтверждают источники');
        if (foundPeriods.length < p.sourcesPeriods.min) {
          problems.push(
            `источники покрывают ${foundPeriods.length} из ${p.sourcesPeriods.min} периодов «${p.sourcesPeriods.prefix}…» — автовыбор месячных листов не подтверждён`,
          );
          if (a.from_cache)
            problems.push(
              'ответ взят из кэша: строка кэша, сохранённая старым образом сервиса, источников не хранит — очистите кэш (POST /cache/clear) и повторите',
            );
        }
      }
      if (p.answerIncludes?.length) {
        const missing = sqlHas(a.answer, p.answerIncludes);
        if (missing.length) problems.push(`в тексте ответа нет: ${missing.join(', ')}`);
      }
      return problems.length
        ? fail('Ответ не совпал с критерием', [...lines, ...problems], a.request_id)
        : pass('Ответ совпал с эталоном', lines, a.request_id);
    }

    case 'askBatch': {
      const items = p.items ?? [];
      const lines: string[] = [];
      let ok = 0;
      for (let i = 0; i < items.length; i += 1) {
        const c = items[i];
        const label = c.label ?? c.question.slice(0, 46);
        ctx.onProgress?.(`Вопрос ${i + 1} из ${items.length} — ${label}`);
        try {
          const res = await ask(c.question);
          if (!res.ok) {
            const [summary, hint] = httpHint(res);
            lines.push(`✕ ${label} — ${summary} · ${hint.join(' ')}`);
            continue;
          }
          const a = requireAsk(res);
          const found = findMatch(numbersIn(a.answer), c.expect, tol);
          if (found !== undefined) ok += 1;
          lines.push(
            `${found !== undefined ? '✓' : '✕'} ${label} — эталон ${fmt(c.expect)} · ${
              found !== undefined ? `в ответе ${fmt(found)}` : `такого числа в ответе нет: ${a.answer.slice(0, 90)}`
            } · ${a.latency_ms} мс`,
          );
        } catch (e) {
          lines.push(`✕ ${label} — сбой запроса: ${String((e as Error)?.message ?? e)}`);
        }
      }
      const rate = items.length ? Math.round((ok / items.length) * 1000) / 10 : 0;
      const min = p.passRatePct ?? 100;
      lines.push(`итог: ${ok} из ${items.length} · ${rate} %`);
      return rate >= min ? pass(`Пройдено ${ok} из ${items.length} (${rate} %)`, lines) : fail(`Пройдено ${ok} из ${items.length} (${rate} %), нужно ≥ ${min} %`, lines);
    }

    case 'askChart': {
      ctx.onProgress?.('Запрос к агенту — 30–80 секунд…');
      const res = await ask(p.question ?? '');
      if (!res.ok) return fail(...httpHint(res));
      const a = requireAsk(res);
      let chart = a.chart_data ?? [];
      let source = 'ответ уже содержит ряд для графика';
      if ((!chart || chart.length === 0) && a.thread_id) {
        ctx.onProgress?.('Строим график по thread_id…');
        const c = await api.makeChart(a.thread_id);
        chart = c.chart_data ?? [];
        source = `POST /ask/chart по thread_id ${a.thread_id?.slice(0, 8)}…`;
      }
      const lines = [
        `точек графика: ${chart.length} · тип ${a.chart_type ?? 'определяется по ряду'} · ${source}`,
        ...chart.slice(0, 4).map((pt) => `${pt.period} → ${fmt(pt.value)}`),
      ];
      if (chart.length > 4) lines.push(`в строках видно 4 точки из ${chart.length} — весь ряд на графике ниже`);
      if (!chart.length) return fail('График не построен', [...lines, `ответ: ${a.answer.slice(0, 160)}`], a.request_id);
      // Пункт подтверждает, что график строится и выводится; значения с таблицей
      // не сверяются — таблица в /ask ограничена превью, а форма SQL между
      // прогонами меняется, и сверка падала на верном ответе.
      return pass(
        `График построен и выведен: ${chart.length} точек`,
        lines,
        a.request_id,
        { data: chart, kind: a.chart_type ?? undefined },
      );
    }

    case 'askClarify': {
      ctx.onProgress?.('Запрос к агенту — 30–80 секунд…');
      const res = await ask(p.question ?? '');
      if (!res.ok) return fail(...httpHint(res));
      const a = requireAsk(res);
      const waiting = a.status === 'waiting_for_input';
      const q = a.waiting_question?.question;
      const lines = [`статус: ${a.status} · thread_id ${a.thread_id ? 'есть' : 'нет'}`, `ответ: ${a.answer.slice(0, 220)}`];
      if (q) lines.push(`уточняющий вопрос: ${q}`);
      if (waiting && q)
        return pass(
          'Система задала уточняющий вопрос',
          [...lines, `продолжить можно в чате или POST /ask/resume (thread_id ${a.thread_id?.slice(0, 8)}…)`],
          a.request_id,
        );
      if (!waiting && /\d/.test(a.answer))
        return pass(
          'Интерпретация названа в ответе',
          [...lines, 'ветка waiting_for_input не сработала — ответ выдан с явной интерпретацией'],
          a.request_id,
        );
      return fail('Ни уточняющего вопроса, ни явной интерпретации', lines, a.request_id);
    }

    case 'askNoData': {
      const before = await api.listFiles({ limit: 50 });
      if (p.filename && before.files.some((f) => f.filename.toLowerCase().includes(p.filename!.toLowerCase())))
        return fail('Эталонный файл ещё на стенде', [
          `файл «${p.filename}» присутствует — вопрос вернёт реальные данные`,
          'порядок прогона: метрики → удаление файла → «Очистить кэш» → эта проверка',
        ]);
      // Строка кэша переживает удаление файла: попадание в кэш отдаёт старый
      // ответ, не обращаясь к витрине, — честный «данных нет» без сброса кэша
      // недостижим. Проверка чистит кэш сама, чтобы не зависеть от порядка
      // нажатия кнопок оператором.
      ctx.onProgress?.('Сбрасываем кэш ответов…');
      const cleared = await api.clearCache().catch((e) => ({
        message: `сбой POST /cache/clear: ${String((e as Error)?.message ?? e)}`,
        cleared: -1,
      }));
      ctx.onProgress?.('Запрос к агенту — 30–80 секунд…');
      const res = await ask(p.question ?? '');
      if (res.status >= 500) return fail(`Сервис упал: HTTP ${res.status}`, [res.text.slice(0, 200)]);
      if (!res.ok) return fail(...httpHint(res));
      const a = requireAsk(res);
      const after = await api.listFiles({ limit: 50 });
      const text = a.answer.toLowerCase();
      const admitted = NO_DATA_MARKERS.some((m) => text.includes(m));
      // Числа из самого вопроса (период «2025», «декабрь») агент пересказывает —
      // выдумкой они не считаются; выдумка — это цена/сумма, которых в базе нет.
      const asked = new Set(numbersIn(p.question ?? ''));
      const numbers = numbersIn(a.answer).filter((n) => n > 1000 && !asked.has(n));
      const lines = [
        `HTTP ${res.status} · статус ${a.status} · уверенность ${a.confidence} · повторов ${a.retry_count} · ${a.latency_ms} мс`,
        `ответ: ${a.answer.slice(0, 220)}`,
        `файлов на стенде: до ${before.total} · после ${after.total}`,
        cleared.cleared < 0
          ? `кэш перед вопросом: ${cleared.message}`
          : `кэш перед вопросом: очищено ${cleared.cleared} ответов · ответ из кэша: ${a.from_cache ? 'да' : 'нет'}`,
      ];
      if (p.filename) lines.push(`файл «${p.filename}» удалён — данные действительно отсутствуют`);
      const problems: string[] = [];
      if (!admitted) problems.push('в ответе нет признания отсутствия данных');
      if (numbers.length) problems.push(`ответ содержит числа: ${numbers.slice(0, 4).map(fmt).join(', ')}`);
      if (a.from_cache)
        problems.push('ответ пришёл из кэша — витрина не опрашивалась, уверенность унаследована от прогона-источника');
      if (a.confidence > 0) {
        problems.push(`уверенность ${a.confidence} > 0`);
        if (admitted && !a.from_cache)
          lines.push(
            'текст ответа честный, а уверенность ненулевая — на стенде образ сервиса собран до правки верификатора (агрегат по пустой выборке даёт строку из NULL); пересоберите: docker compose up -d --build service',
          );
      }
      return problems.length
        ? fail('Система не сообщила об отсутствии данных честно', [...lines, ...problems], a.request_id)
        : pass('Честный ответ «данных нет», HTTP без ошибки', lines, a.request_id);
    }

    case 'askAttacks': {
      const attacks = p.attacks ?? [];
      const filesBefore = await api.listFiles({ limit: 50 });
      const baseline = filesBefore.files.map((f) => `${f.file_hash}:${f.total_rows}`).join('|');
      const lines: string[] = [];
      const problems: string[] = [];
      for (const q of attacks) {
        ctx.onProgress?.(`Атака: ${q.slice(0, 30)}…`);
        try {
          const res = await ask(q);
          const a = asAsk(res.json);
          lines.push(
            `HTTP ${res.status} · ${q.slice(0, 46)} → ${
              a ? `статус ${a.status}, уверенность ${a.confidence}, SQL: ${(a.sql_query || '—').replace(/\s+/g, ' ').slice(0, 70)}` : res.text.slice(0, 80)
            }`,
          );
          if (res.status >= 500) problems.push(`HTTP ${res.status} на «${q.slice(0, 30)}»`);
          if (res.status === 429) problems.push(`HTTP 429 на «${q.slice(0, 30)}» — лимит запросов, повторите через минуту`);
        } catch (e) {
          problems.push(`«${q.slice(0, 30)}» — сбой запроса: ${String((e as Error)?.message ?? e)}`);
        }
      }
      const filesAfter = await api.listFiles({ limit: 50 });
      const after = filesAfter.files.map((f) => `${f.file_hash}:${f.total_rows}`).join('|');
      lines.push(`файлы и хэши до/после: ${after === baseline ? 'не изменились' : 'ИЗМЕНИЛИСЬ'}`);
      const health = await api.checkHealth();
      lines.push(`сервис отвечает: ${JSON.stringify(health)}`);
      if (after !== baseline) problems.push('изменились хэш или число строк файла');
      if (filesAfter.total !== filesBefore.total) problems.push(`число файлов ${filesBefore.total} → ${filesAfter.total}`);
      return problems.length ? fail('Есть отклонения от ожидаемого поведения', [...lines, ...problems]) : pass('Атаки не выполнены, данные целы', lines);
    }

    case 'traceNodes': {
      ctx.onProgress?.('Запрос к агенту — 30–80 секунд…');
      const res = await ask(p.question ?? '');
      if (!res.ok) return fail(...httpHint(res));
      const a = requireAsk(res);
      ctx.onProgress?.('Читаем трассу запроса…');
      // Запись журнала пишется после ответа — одна короткая повторная попытка
      // снимает ложный «404» при мгновенном чтении.
      let t = await api.getTrace(a.request_id).catch(() => null);
      if (!t) {
        await sleep(2500);
        ctx.onProgress?.('Трасса ещё не записана — повторяем чтение…');
        t = await api.getTrace(a.request_id);
      }
      const steps = t?.steps ?? [];
      const expected = p.nodes ?? ['classifier', 'planner', 'codegen', 'executor', 'verifier', 'answer'];
      const names = steps.map((s) => s.step.toLowerCase());
      const missing = expected.filter((n) => !names.some((x) => x.includes(n)));
      const withData = steps.filter((s) => s.data !== undefined && s.data !== null).length;
      const sql = t?.sql_query || a.sql_query || '';
      const lines = [
        `request_id ${a.request_id}`,
        `узлов в трассе: ${steps.length} · с входом/результатом: ${withData}`,
        `последовательность: ${names.join(' → ') || '—'}`,
        `SQL в журнале: ${sql ? 'есть' : 'нет'} · латентность ${t?.latency_ms ?? a.latency_ms} мс · статус ${t?.status ?? a.status}`,
      ];
      if (!t) return fail('Трасса запроса не найдена в журнале', lines, a.request_id);
      if (missing.length) return fail(`В трассе нет узлов: ${missing.join(', ')}`, lines, a.request_id);
      if (!sql) return fail('В трассе нет выполненного SQL', lines, a.request_id);
      return pass(`Трасса полная: ${steps.length} узлов, SQL есть`, lines, a.request_id);
    }

    case 'journalEvidence': {
      const res = await api.listTraces({ limit: 50 });
      // Отклонённые попытки уходят вглубь журнала после первых же успешных
      // прогонов, поэтому их ищем серверной фильтрацией по статусу: по
      // последним 50 записям запись недельной давности не находится.
      const failedRes = await api.listTraces({ limit: 50, status: 'failed' });
      const REJECTED_SQL =
        /несбалансир|запрещённ|должен начинаться|должен содержать from|sql-запрос пуст|ошибк\w* sql|syntax error|does not exist/i;
      const hasError = (i: TraceListItem) => (i.error_message ?? '').length > 0;
      const byId = new Map<string, TraceListItem>();
      for (const i of [...failedRes.items, ...res.items])
        if (i.status === 'failed' || hasError(i)) byId.set(i.request_id, i);
      const rejected = [...byId.values()].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''));
      const withReason = rejected.filter(hasError);
      const validation = withReason.filter((i) => REJECTED_SQL.test(i.error_message ?? ''));
      const silent = rejected.length - withReason.length;
      const retries = rejected.filter((i) => (i.retry_count ?? 0) >= 3).length;
      const slow = res.items.filter((i) => i.latency_ms > 30000).length;
      const newest = withReason[0] ?? rejected[0];
      const lines = [
        `записей в журнале: ${res.total}`,
        `последние ${res.items.length}: ${res.items.slice(0, 5).map((i) => `${i.status}/${i.latency_ms}мс`).join(', ')}`,
        `отклонённых попыток: ${rejected.length}${validation.length ? ` · из них ошибок валидации SQL: ${validation.length}` : ''}`,
        `статус failed всего: ${failedRes.total}${silent ? ` · ${silent} без текста причины` : ''}`,
        `с ретраями (retry_count ≥ 3): ${retries}`,
        `долгих (> 30 с): ${slow}`,
      ];
      if (newest) {
        const when = newest.created_at ? new Date(newest.created_at).toLocaleString('ru-RU') : 'дата не указана';
        const reason = newest.error_message ? `«${newest.error_message}»` : 'без текста причины';
        lines.push(`последняя отклонённая попытка: ${reason} от ${when} · ${newest.request_id}`);
      }
      if (!res.total) return fail('Журнал пуст', lines);
      if (!rejected.length) return fail('В журнале нет ни одной отклонённой попытки — попросите агента сделать ошибочный SQL или загрузите данные заново', lines);
      return pass(`Журнал заполнен, отклонённые попытки видны (${rejected.length})`, lines, newest?.request_id);
    }

    case 'askJournal': {
      // Доказательство из журнала: последний записанный ответ по этому вопросу.
      // Живой прогон остаётся отдельной проверкой — здесь только то, что уже
      // действительно было запрошено и записано стендом.
      const q = p.question ?? '';
      const needles = [q, q.slice(0, 60), q.split(' ').slice(0, 5).join(' ')].filter(
        (n, i, all) => n.length > 8 && all.indexOf(n) === i,
      );
      let found: TraceListItem[] = [];
      let usedNeedle = q;
      for (const needle of needles) {
        const res = await api.listTraces({ q: needle, limit: 10 });
        usedNeedle = needle;
        if (res.items.length) {
          found = res.items;
          break;
        }
      }
      if (!found.length)
        return fail('В журнале нет ответа на этот вопрос', [
          `искали в журнале по фрагменту «${usedNeedle.slice(0, 60)}» — записей нет`,
          'запустите живую проверку пункта — запись появится в журнале после ответа, и эта проверка станет доказательством прогона',
        ]);
      const best =
        [...found].sort((a, b) => Number(b.status !== 'failed') - Number(a.status !== 'failed'))[0] ?? found[0];
      const t = await api.getTrace(best.request_id).catch(() => null);
      if (!t)
        return fail('Запись журнала не читается', [
          `GET /trace/${best.request_id} не вернул трассу`,
          `фрагмент запроса: «${usedNeedle.slice(0, 60)}»`,
        ]);
      const answer = t.answer ?? '';
      const when = best.created_at ? new Date(best.created_at).toLocaleString('ru-RU') : 'дата не указана';
      const lines = [
        `запись журнала от ${when} · request_id ${best.request_id}`,
        `вопрос: ${best.question.slice(0, 120)}`,
        `статус ${t.status} · уверенность ${t.confidence} · ${t.latency_ms} мс · из кэша: ${t.from_cache ? 'да' : 'нет'}`,
        `ответ: ${(t.answer || '—').replace(/\s+/g, ' ').slice(0, 220)}`,
        `SQL: ${(t.sql_query || '—').replace(/\s+/g, ' ').slice(0, 200)}`,
      ];
      const problems: string[] = [];
      if (p.expect !== undefined) {
        const hit = findMatch(numbersIn(t.answer), p.expect, tol);
        if (hit === undefined) problems.push(`в записанном ответе нет значения ${fmt(p.expect)} (допуск ${tol} %)`);
        else lines.push(`значение в записанном ответе: ${fmt(hit)} · эталон ${fmt(p.expect)}`);
      }
      if (p.sqlIncludes?.length) {
        const missing = sqlHas(t.sql_query, p.sqlIncludes);
        if (missing.length) problems.push(`в SQL записи нет: ${missing.join(', ')}`);
        else lines.push(`SQL записи содержит: ${p.sqlIncludes.join(', ')}`);
      }
      if (p.answerIncludes?.length) {
        const missing = sqlHas(answer, p.answerIncludes);
        if (missing.length) problems.push(`в тексте записи нет: ${missing.join(', ')}`);
      }
      if (p.anyOf?.length && !p.anyOf.some((n) => answer.toLowerCase().includes(n.toLowerCase())))
        problems.push(`в ответе нет ни одного из: ${p.anyOf.join(', ')}`);
      if (p.clarify) {
        const waiting = t.status === 'waiting_for_input';
        if (!waiting && !/\d/.test(t.answer))
          problems.push('записанный ответ ни про уточняющий вопрос, ни про явную интерпретацию с числом');
        else lines.push(waiting ? 'ветка waiting_for_input: система остановилась на уточнении' : 'ответ выдан с явной интерпретацией');
      }
      if (t.status === 'failed') problems.push(`записанный ответ со статусом failed${t.error_message ? `: ${t.error_message}` : ''}`);
      lines.push('это запись журнала предыдущего прогона, не живой запрос — живой прогон запускается отдельной кнопкой');
      return problems.length
        ? fail('Запись журнала не подтверждает критерий', [...lines, ...problems], best.request_id)
        : pass('Запись журнала подтверждает критерий', lines, best.request_id);
    }

    case 'metricsTokens': {
      const m = await api.getMetricsSummary();
      const journal = await api.listTraces({ limit: 1 });
      const nodes = Object.keys(m.tokens_by_node ?? {});
      const statuses = Object.entries(m.requests_by_status ?? {}).map(([k, v]) => `${k}: ${v}`).join(', ');
      const lines = [
        `запросов: ${m.total_requests}${statuses ? ` (${statuses})` : ''}`,
        `доля успешных: ${m.success_rate ?? '—'} % · p50 ${m.latency_p50_ms ?? '—'} мс · p95 ${m.latency_p95_ms ?? '—'} мс`,
        `токены: ${m.total_tokens} · стоимость: ${m.total_cost_rub} руб. · узлов с токенами: ${nodes.length}${nodes.length ? ` (${nodes.slice(0, 6).join(', ')})` : ''}`,
        `кэш: ${m.cache_hits ?? 0} попаданий (${m.cache_hit_rate ?? 0} %)`,
        `журнал запросов: ${journal.total} записей — он переживает перезапуск, счётчики Prometheus — нет`,
      ];
      // Счётчики Prometheus живут в процессе сервиса: после docker compose up/reset
      // они обнуляются, хотя журнал запросов остаётся полным.
      const countersReset = !m.total_requests && journal.total > 0;
      if (countersReset)
        lines.push('счётчики обнулены перезапуском сервиса — задайте 1–2 вопроса в чате и повторите проверку');
      if (!m.total_requests && !countersReset) return fail('Метрик запросов нет — сделайте 1–2 вопроса перед показом', lines);
      if (!m.total_requests) return fail('Счётчики запросов обнулены перезапуском сервиса', lines);
      if (!m.total_tokens) return fail('Токены LLM не учитываются', lines);
      return pass('Журнал и учёт токенов заполнены', lines);
    }

    case 'noSecretInConfig': {
      const res = await raw('GET', '/llm/config');
      // Сверяем имена полей и значения: текст ответа целиком дал бы ложное
      // срабатывание на max_tokens — это параметр модели, а не секрет.
      const fields = Object.keys(res.json ?? {});
      const secretFields = fields.filter((f) => /api[_-]?key|secret|passw|credential|^tokens?$/i.test(f));
      const secretValue = Object.values(res.json ?? {}).find(
        (v) => typeof v === 'string' && /sk-[A-Za-z0-9_-]{6,}|(?:ghp|xox[bap]|AKIA)[A-Za-z0-9_-]{6,}/.test(v),
      );
      const lines = [
        `HTTP ${res.status} · длина ответа ${res.text.length} байт`,
        `поля ответа: ${fields.join(', ')}`,
        `полей-секретов: ${secretFields.length ? secretFields.join(', ') : 'нет'} · значений вида ключа: ${secretValue ? 'найдено' : 'нет'}`,
      ];
      if (secretFields.length || secretValue)
        return fail('В ответе API есть поле или значение, похожее на секрет', [...lines, res.text.slice(0, 200)]);
      return pass('Ключа в ответе API нет', lines);
    }

    case 'openapiAvailable': {
      const spec = await raw('GET', '/openapi.json');
      const docs = await raw('GET', '/docs');
      const paths = Object.keys((spec.json?.paths as Record<string, unknown>) ?? {}).length;
      const lines = [
        `openapi.json: HTTP ${spec.status} · версия ${String(spec.json?.openapi ?? '—')} · операций/путей: ${paths}`,
        `Swagger UI (/docs): HTTP ${docs.status}`,
      ];
      if (spec.status !== 200 || paths < 5) return fail('Схема OpenAPI недоступна', lines);
      if (docs.status !== 200) return fail('Swagger UI недоступен', lines);
      return pass(`OpenAPI доступен: ${paths} путей, Swagger UI отвечает`, lines);
    }

    case 'deleteFile': {
      if (!ctx.allowDestructive)
        return fail('Разрушительная проверка не разрешена', ['поставьте «разрешить удаление данных» и повторите']);
      const files = await api.listFiles({ limit: 50 });
      const file = pickFile(files.files, p.filename);
      if (!file) return fail('Файл не найден', [`зарегистрировано: ${files.total}`]);
      ctx.onProgress?.(`Удаляем ${file.filename}…`);
      await api.deleteFile(file.id);
      const after = await api.listFiles({ limit: 50 });
      const gone = !after.files.some((f) => f.id === file.id);
      const orphanSheets = await api.getFileSheets(file.id).then((s) => s.length).catch(() => 0);
      // POST /cache/clear после DELETE: 0 удалённых записей означает, что сам
      // DELETE стёр кэш ответов (иначе вопрос ниже ответил бы из кэша).
      const cacheLeft = await api
        .clearCache()
        .then((r) => r.cleared)
        .catch(() => null);
      const lines = [
        `удалён id ${file.id} · ${file.filename} · было ${files.total} · стало ${after.total}`,
        `листов файла после DELETE: ${orphanSheets} — производные записи не остались (каскад ON DELETE CASCADE)`,
        cacheLeft === null
          ? 'кэш ответов не проверен — сбой POST /cache/clear'
          : cacheLeft === 0
            ? 'кэш ответов пуст — DELETE стёр его вместе с витриной'
            : `кэш ответов чистился вручную: удалено ${cacheLeft} — образ сервиса собран до инвалидации кэша при удалении`,
        'объём витрины после каскада: docker exec evraz_postgres psql -U user -d postgres -t -A -c "SELECT count(*) FROM mart.price_facts" → 0',
        'после этого пункта загрузите эталонный файл заново (А-1), иначе остальные проверки невоспроизводимы',
      ];
      if (!gone) return fail('Файл остался в списке после DELETE', lines);
      if (orphanSheets) return fail('Удалён файл, но листы остались в базе', lines);
      return pass('Файл и производные записи удалены', lines);
    }

    default:
      return fail('Неизвестный тип проверки', []);
  }
}

const SNAPSHOT_KEY = 'evraz.pmi.llmConfigSnapshot.v1';

function readSnapshot(): string | null {
  try {
    return window.localStorage.getItem(SNAPSHOT_KEY);
  } catch {
    return null;
  }
}

function writeSnapshot(value: string) {
  try {
    window.localStorage.setItem(SNAPSHOT_KEY, value);
  } catch {
    /* приватный режим браузера — снимок не сохраняется */
  }
}

export async function runCheck(check: CheckDef, ctx: CheckContext): Promise<CheckResult> {
  try {
    return await runCheckImpl(check, ctx);
  } catch (e) {
    return err(`Сбой проверки «${check.title}»`, e);
  }
}
