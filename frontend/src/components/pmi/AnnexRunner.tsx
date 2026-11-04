import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  ListChecks,
  Play,
  RotateCcw,
  Send,
} from 'lucide-react';
import ResultChart from '@/components/chat/ResultChart';
import SqlBlock from '@/components/chat/SqlBlock';
import AnnexUploader from '@/components/pmi/AnnexUploader';
import BenchmarkFiveRunner from '@/components/pmi/BenchmarkFiveRunner';
import ModelSwitcher from '@/components/pmi/ModelSwitcher';
import { ToastContainer } from '@/components/ui/Toast';
import { useToast } from '@/hooks/useToast';
import { api } from '@/api';
import { IDLE_PROBE, runProbe, type ProbeState } from '@/lib/pmiProbes';
import { runCheck, type CheckDef, type CheckResult } from '@/lib/pmiChecks';
import {
  ANNEX_A_ITEMS,
  VERDICT_META,
  chatQ,
  type AnnexItem,
  type PmiVerdict,
} from '@/data/pmiAnnexA';
import { PMI_ADDRESSES, PMI_PREFLIGHT, PMI_RUNBOOK, runbookCheatSheet } from '@/data/pmiRunBook';

const STORAGE_KEY = 'evraz.pmi.annexA.v1';
const PREFLIGHT_KEY = 'evraz.pmi.preflight.v1';
const CHECKS_KEY = 'evraz.pmi.checks.v1';
const ACTIVE_KEY = 'evraz.pmi.activeItem.v1';
/** Проверки, которые не запускаются в экспресс-прогоне всех пунктов. */
const NOT_AUTO = new Set(['clearCache', 'llmConfigDiff']);
/** Сколько строк доказательства храним в браузере (полные — до перезагрузки). */
const STORED_LINES = 6;
const GROUPS = ['Функциональные', 'Качество', 'Надёжность', 'Безопасность', 'Совместимость'] as const;

interface ItemState {
  verdict: PmiVerdict;
  note: string;
}

type Stored = Record<string, ItemState>;
type ChecksByItem = Record<string, Record<string, CheckResult>>;

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* приватный режим браузера — данные живут только до перезагрузки */
  }
}

function loadStored(): Stored {
  return readJson<Stored>(STORAGE_KEY, {});
}

function loadChecks(): ChecksByItem {
  return readJson<ChecksByItem>(CHECKS_KEY, {});
}

function saveChecks(value: ChecksByItem) {
  const trimmed: ChecksByItem = {};
  Object.entries(value).forEach(([item, byCheck]) => {
    trimmed[item] = {};
    Object.entries(byCheck).forEach(([id, res]) => {
      trimmed[item][id] = { ...res, lines: res.lines.slice(0, STORED_LINES) };
    });
  });
  writeJson(CHECKS_KEY, trimmed);
}

const checksOf = (id: string): CheckDef[] => PMI_RUNBOOK[id]?.checks ?? [];

function protocolMarkdown(states: Stored, checks: ChecksByItem, preflight: Record<string, boolean>): string {
  const date = new Date().toLocaleString('ru-RU');
  const lines = [
    'ПРОТОКОЛ ПРИЁМОЧНЫХ ИСПЫТАНИЙ № ___',
    'Excel-агент ЕВРАЗ — приложение А (контрольные примеры А-1…А-17)',
    `Заполнен: ${date}`,
    '',
    '| № | Пример | Покрывает | Критерий приёмки | Фактический результат | Автопроверки | Пройдено |',
    '|---|--------|-----------|------------------|---------------------|--------------|----------|',
  ];

  ANNEX_A_ITEMS.forEach((item, idx) => {
    const state = states[item.id] ?? { verdict: item.verdict, note: item.note ?? '' };
    const checksCol = checksSummaryCell(item.id, checks);
    const criteria = item.requirements.map((r) => `${r.code}: ${r.criterion}`).join('; ');
    const fact = (state.note || item.note || VERDICT_META[state.verdict].label).replace(/\|/g, '/');
    const passed =
      state.verdict === 'pass'
        ? 'да'
        : state.verdict === 'warn'
          ? 'с оговоркой'
          : state.verdict === 'fail'
            ? 'нет'
            : '—';
    lines.push(
      `| ${idx + 1} | ${item.id} · ${item.title} | ${item.requirements.map((r) => r.code).join(', ')} | ${criteria} | ${fact} | ${checksCol} | ${passed} |`,
    );
  });

  const counts = ANNEX_A_ITEMS.reduce<Record<string, number>>((acc, item) => {
    const v = states[item.id]?.verdict ?? item.verdict;
    acc[v] = (acc[v] ?? 0) + 1;
    return acc;
  }, {});

  const preDone = PMI_PREFLIGHT.filter((p) => preflight[p.id]).length;

  lines.push(
    '',
    `Итог: пройдено ${counts.pass ?? 0} · с оговоркой ${counts.warn ?? 0} · не пройдено ${counts.fail ?? 0} · предстоит ${counts.todo ?? 0} (всего ${ANNEX_A_ITEMS.length}).`,
    `Предусловия прогона отмечены: ${preDone} из ${PMI_PREFLIGHT.length}.`,
    'Автопроверки — вызовы стенда из карточек пункта; итоговый статус ставит комиссия.',
    'Выводы: ____________________  Председатель комиссии: ______________  Члены комиссии: ______________',
  );

  return lines.join('\n');
}

function checksSummaryCell(itemId: string, checks: ChecksByItem): string {
  const defs = checksOf(itemId);
  if (!defs.length) return '—';
  const res = checks[itemId] ?? {};
  const done = defs.filter((c) => res[c.id]);
  if (!done.length) return `запускалось 0 из ${defs.length}`;
  const passed = done.filter((c) => res[c.id].status === 'pass').length;
  const at = done.map((c) => res[c.id].at).sort().slice(-1)[0];
  return `${passed} из ${defs.length} пройдено · ${at}`;
}

export default function AnnexRunner() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { toasts, showToast, dismiss } = useToast();
  const [activeId, setActiveId] = useState<string>(() => {
    const fromUrl = searchParams.get('item');
    if (fromUrl && ANNEX_A_ITEMS.some((i) => i.id === fromUrl)) return fromUrl;
    const saved = readJson<string>(ACTIVE_KEY, '');
    return ANNEX_A_ITEMS.some((i) => i.id === saved) ? saved : ANNEX_A_ITEMS[0].id;
  });
  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const [stored, setStored] = useState<Stored>(() => loadStored());
  const [preflight, setPreflight] = useState<Record<string, boolean>>(() =>
    readJson<Record<string, boolean>>(PREFLIGHT_KEY, {}),
  );
  const [probes, setProbes] = useState<Record<string, ProbeState>>({});
  const [envProbe, setEnvProbe] = useState<ProbeState>(IDLE_PROBE);
  const [checks, setChecks] = useState<ChecksByItem>(() => loadChecks());
  const [running, setRunning] = useState<Record<string, string>>({});
  const [pickedFile, setPickedFile] = useState<File | null>(null);
  const [allowDestructive, setAllowDestructive] = useState(false);
  const [cacheBusy, setCacheBusy] = useState(false);
  const [sweep, setSweep] = useState<{ done: number; total: number } | null>(null);
  const [sweepResult, setSweepResult] = useState<{ passed: number; total: number; problems: string[] } | null>(
    null,
  );
  const [copiedText, setCopiedText] = useState<string | null>(null);
  const tabsRef = useRef<HTMLDivElement | null>(null);
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const busyRef = useRef(false);

  const visible = useMemo(
    () => (groupFilter ? ANNEX_A_ITEMS.filter((i) => i.group === groupFilter) : ANNEX_A_ITEMS),
    [groupFilter],
  );

  const active: AnnexItem = ANNEX_A_ITEMS.find((i) => i.id === activeId) ?? ANNEX_A_ITEMS[0];
  const activeBook = PMI_RUNBOOK[active.id];
  const activeChecks = checksOf(active.id);
  const activeResults = checks[active.id] ?? {};
  const busy = Object.keys(running).length > 0;

  // Полоса вкладок скроллится по горизонтали — активную удерживаем в зоне видимости.
  useEffect(() => {
    const wrap = tabsRef.current;
    const tab = tabRefs.current[activeId];
    if (!wrap || !tab) return;
    const target = tab.offsetLeft - (wrap.clientWidth - tab.offsetWidth) / 2;
    const max = wrap.scrollWidth - wrap.clientWidth;
    wrap.scrollTo({ left: Math.min(Math.max(target, 0), max), behavior: 'smooth' });
  }, [activeId, groupFilter]);

  // Пункт живёт в адресе: возврат из чата (вопрос уходит на /?q=…) открывает
  // тот же контрольный пример, а не первый список.
  useEffect(() => {
    writeJson(ACTIVE_KEY, activeId);
    if (searchParams.get('item') === activeId) return;
    const next = new URLSearchParams(searchParams);
    next.set('item', activeId);
    setSearchParams(next, { replace: true });
    // searchParams не в зависимостях: иначе эффект перезапускался бы на каждую
    // собственную правку адреса.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, setSearchParams]);

  const stateOf = useCallback(
    (item: AnnexItem): ItemState => stored[item.id] ?? { verdict: item.verdict, note: item.note ?? '' },
    [stored],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === 'TEXTAREA' || tag === 'INPUT' || tag === 'SELECT') return;
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      // Стрелки ходят по отфильтрованному списку: с фильтром «Надёжность»
      // нельзя уехать в А-1 из группы «Функциональные».
      const list = visible.length ? visible : ANNEX_A_ITEMS;
      const idx = list.findIndex((i) => i.id === activeId);
      const next =
        e.key === 'ArrowRight'
          ? list[Math.min(idx + 1, list.length - 1)]
          : list[Math.max(idx - 1, 0)];
      if (next) setActiveId(next.id);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [activeId, visible]);

  const applyGroupFilter = (group: string | null) => {
    setGroupFilter(group);
    if (!group || active.group === group) return;
    const first = ANNEX_A_ITEMS.find((i) => i.group === group);
    if (first) setActiveId(first.id);
  };

  const setVerdict = (id: string, verdict: PmiVerdict) => {
    const base = stateOf(ANNEX_A_ITEMS.find((i) => i.id === id) as AnnexItem);
    const next = { ...stored, [id]: { ...base, verdict } };
    setStored(next);
    writeJson(STORAGE_KEY, next);
  };

  const setNote = (id: string, note: string) => {
    const base = stateOf(ANNEX_A_ITEMS.find((i) => i.id === id) as AnnexItem);
    const next = { ...stored, [id]: { ...base, note } };
    setStored(next);
    writeJson(STORAGE_KEY, next);
  };

  const togglePreflight = (id: string) => {
    const next = { ...preflight, [id]: !preflight[id] };
    setPreflight(next);
    writeJson(PREFLIGHT_KEY, next);
  };

  const resetVerdicts = () => {
    setStored({});
    writeJson(STORAGE_KEY, {});
    showToast('Статусы и замечания сброшены к данным прогона-репетиции', 'info');
  };

  const resetPreflight = () => {
    setPreflight({});
    writeJson(PREFLIGHT_KEY, {});
    showToast('Чек-лист предусловий очищен', 'info');
  };

  const resetItemChecks = (itemId: string) => {
    const next = { ...checks };
    delete next[itemId];
    setChecks(next);
    showToast('Результаты автопроверок пункта очищены', 'info');
  };

  const copyText = (label: string, text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedText(label);
      showToast('Скопировано в буфер обмена', 'success');
      window.setTimeout(() => setCopiedText(null), 1600);
    });
  };

  const copyProtocol = () => {
    navigator.clipboard.writeText(protocolMarkdown(stored, checks, preflight)).then(() =>
      showToast('Протокол (приложение Б) скопирован в буфер обмена', 'success'),
    );
  };

  const download = (name: string, text: string, mime: string) => {
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast(`Файл ${name} сохранён`, 'success');
  };

  const downloadProtocol = () =>
    download(
      `pmi_protocol_annex_a_${new Date().toISOString().slice(0, 10)}.md`,
      protocolMarkdown(stored, checks, preflight),
      'text/markdown;charset=utf-8',
    );

  const downloadCheat = () =>
    download(`pmi_runbook_${new Date().toISOString().slice(0, 10)}.md`, runbookCheatSheet(), 'text/markdown;charset=utf-8');

  const runItemProbe = async (item: AnnexItem) => {
    if (!item.probe) return;
    setProbes((prev) => ({ ...prev, [item.id]: { status: 'loading', lines: [] } }));
    try {
      const lines = await runProbe(item.probe.kind);
      setProbes((prev) => ({ ...prev, [item.id]: { status: 'ok', lines } }));
    } catch (err) {
      setProbes((prev) => ({
        ...prev,
        [item.id]: { status: 'error', lines: [], error: (err as Error).message },
      }));
    }
  };

  const runEnvProbe = async () => {
    setEnvProbe({ status: 'loading', lines: [] });
    try {
      setEnvProbe({ status: 'ok', lines: await runProbe('health') });
    } catch (err) {
      setEnvProbe({ status: 'error', lines: [], error: (err as Error).message });
    }
  };

  const clearCache = async () => {
    setCacheBusy(true);
    try {
      const res = await api.clearCache();
      showToast(`${res.message} · очищено ответов: ${res.cleared}`, 'success');
    } catch (err) {
      showToast(`Не удалось очистить кэш: ${(err as Error).message}`, 'error');
    } finally {
      setCacheBusy(false);
    }
  };

  useEffect(() => {
    saveChecks(checks);
  }, [checks]);

  const markResult = (itemId: string, checkId: string, result: CheckResult) => {
    setChecks((prev) => ({ ...prev, [itemId]: { ...(prev[itemId] ?? {}), [checkId]: result } }));
  };

  const runOneCheck = useCallback(
    async (item: AnnexItem, check: CheckDef) => {
      const key = `${item.id}:${check.id}`;
      setRunning((prev) => ({ ...prev, [key]: 'Запрос к стенду…' }));
      try {
        const result = await runCheck(check, {
          file: pickedFile,
          allowDestructive,
          onProgress: (message) =>
            setRunning((prev) => (key in prev ? { ...prev, [key]: message } : prev)),
        });
        markResult(item.id, check.id, result);
        return result;
      } finally {
        setRunning((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
      }
    },
    [allowDestructive, pickedFile],
  );

  interface Pair {
    item: AnnexItem;
    check: CheckDef;
  }

  /**
   * Последовательный прогон списка проверок: одна проверка за раз, чтобы
   * запросы к модели не шли параллельно и журнал оставался читаемым.
   */
  const runPairs = async (
    pairs: Pair[],
    label: string,
    onStep?: (done: number, total: number) => void,
  ): Promise<{ passed: number; total: number; problems: string[] } | null> => {
    if (!pairs.length) return null;
    if (busyRef.current) {
      showToast('Уже выполняется другая проверка — дождитесь её окончания', 'warn');
      return null;
    }
    busyRef.current = true;
    const keys: string[] = [];
    let passed = 0;
    const problems: string[] = [];
    try {
      for (let i = 0; i < pairs.length; i += 1) {
        const { item, check } = pairs[i];
        const key = `${item.id}:${check.id}`;
        keys.push(key);
        if (check.destructive && !allowDestructive) {
          markResult(item.id, check.id, {
            status: 'fail',
            summary: 'Проверка не запускалась: нужно разрешить удаление данных',
            lines: ['флаг «разрешить удаление данных» под списком проверок'],
            at: new Date().toLocaleTimeString('ru-RU'),
          });
          problems.push(item.id);
          onStep?.(i + 1, pairs.length);
          continue;
        }
        const result = await runOneCheck(item, check);
        if (result.status === 'pass') passed += 1;
        else if (!problems.includes(item.id)) problems.push(item.id);
        onStep?.(i + 1, pairs.length);
      }
    } finally {
      busyRef.current = false;
      setRunning((prev) => {
        const next = { ...prev };
        keys.forEach((k) => delete next[k]);
        return next;
      });
    }
    showToast(
      `${label}: пройдено ${passed} из ${pairs.length}${
        problems.length ? ` · требуют внимания ${problems.join(', ')}` : ''
      }`,
      problems.length ? 'warn' : 'success',
    );
    return { passed, total: pairs.length, problems };
  };

  const runCheckList = async (item: AnnexItem, list: CheckDef[], label: string) => {
    await runPairs(list.map((check) => ({ item, check })), label);
  };

  /**
   * Экспресс-проверка всех пунктов сразу: обращения к модели, очистка кэша,
   * сравнение снимка конфигурации и удаление файлов в неё не входят — они
   * меняют состояние стенда и запускаются только вручную, осознанно.
   */
  const autoPairs = useMemo(
    () =>
      ANNEX_A_ITEMS.flatMap((item) =>
        checksOf(item.id)
          .filter((c) => !c.slow && !c.destructive && !c.needsFile && !NOT_AUTO.has(c.kind))
          .map((check) => ({ item, check })),
      ),
    [],
  );

  const runAllFast = async () => {
    setSweep({ done: 0, total: autoPairs.length });
    const res = await runPairs(autoPairs, 'Экспресс-проверка всех пунктов', (done, total) =>
      setSweep({ done, total }),
    );
    setSweep(null);
    setSweepResult(res);
  };

  const counts = useMemo(() => {
    const acc: Record<PmiVerdict, number> = { pass: 0, warn: 0, fail: 0, todo: 0 };
    ANNEX_A_ITEMS.forEach((item) => {
      acc[stateOf(item).verdict] += 1;
    });
    return acc;
  }, [stateOf]);

  const checksPassed = activeChecks.filter((c) => activeResults[c.id]?.status === 'pass').length;
  const checksDone = activeChecks.filter((c) => activeResults[c.id]).length;
  const fastChecks = activeChecks.filter((c) => !c.slow && !c.destructive);
  const fullChecks = activeChecks.filter((c) => !c.destructive);
  const needsFile = activeChecks.some((c) => c.needsFile);
  const hasDestructive = activeChecks.some((c) => c.destructive);
  const progress = Math.round(((counts.pass + counts.warn * 0.5) / ANNEX_A_ITEMS.length) * 100);
  const probe = probes[active.id] ?? IDLE_PROBE;
  const activeState = stateOf(active);
  const activeIndex = ANNEX_A_ITEMS.findIndex((i) => i.id === active.id);
  const preflightDone = PMI_PREFLIGHT.filter((p) => preflight[p.id]).length;

  return (
    <section className="annex">
      <div className="annex__head">
        <div>
          <h2 className="demo__title">Прогон ПМИ: {ANNEX_A_ITEMS.length} контрольных примеров</h2>
        </div>
        <div className="annex__headActions">
          <button
            type="button"
            className="annex__btn annex__btn--probe"
            onClick={runAllFast}
            disabled={busy || autoPairs.length === 0}
            title="Настоящие вызовы стенда по всем пунктам сразу. Обращений к модели, очистки кэша, сравнения конфигурации и удаления файлов здесь нет — они запускаются только вручную."
          >
            <Play size={15} />
            <span>
              {sweep
                ? `Экспресс-проверка ${sweep.done} из ${sweep.total}…`
                : `Экспресс-проверка всех пунктов (${autoPairs.length})`}
            </span>
          </button>
          <button type="button" className="annex__btn" onClick={copyProtocol}>
            <Copy size={15} />
            <span>Протокол в буфер</span>
          </button>
          <button type="button" className="annex__btn" onClick={downloadProtocol}>
            <Download size={15} />
            <span>Протокол .md</span>
          </button>
          <button type="button" className="annex__btn" onClick={downloadCheat}>
            <Download size={15} />
            <span>Шпаргалка спикера .md</span>
          </button>
          <button
            type="button"
            className="annex__btn annex__btn--ghost"
            onClick={resetVerdicts}
            title="Только статусы и замечания комиссии; чек-лист и автопроверки — отдельными кнопками"
          >
            <RotateCcw size={15} />
            <span>Сбросить статусы</span>
          </button>
        </div>
      </div>

      <div className="annex__meter">
        <div className="annex__meterBar">
          <div className="annex__meterFill" style={{ width: `${progress}%` }} />
        </div>
        <div className="annex__meterLegend">
          <span className="annex__chip annex__chip--pass">Пройдено {counts.pass}</span>
          <span className="annex__chip annex__chip--warn">С оговоркой {counts.warn}</span>
          <span className="annex__chip annex__chip--fail">Не пройдено {counts.fail}</span>
          <span className="annex__chip annex__chip--todo">Предстоит {counts.todo}</span>
          <span className="annex__chip annex__chip--muted">Готовность {progress} %</span>
          <span className="annex__chip annex__chip--muted">
            Предусловия {preflightDone} из {PMI_PREFLIGHT.length}
          </span>
          {PMI_ADDRESSES.map((a) => (
            <span className="annex__chip annex__chip--muted" key={a.value}>
              {a.label}: {a.value}
            </span>
          ))}
        </div>
      </div>

      {sweepResult && (
        <div className={`annex__sweep${sweepResult.problems.length ? ' annex__sweep--warn' : ''}`}>
          Экспресс-проверка стенда: пройдено {sweepResult.passed} из {sweepResult.total}.{' '}
          {sweepResult.problems.length
            ? `Требуют внимания: ${sweepResult.problems.join(', ')} — откройте пункт и посмотрите строки доказательства.`
            : 'Замечаний нет.'}{' '}
          Пункты с обращениями к модели, очисткой кэша и удалением данных запускаются отдельно из своих карточек.
        </div>
      )}

      <details className="ds__preflight">
        <summary className="ds__preflightSummary">
          <ListChecks size={15} />
          <span>Чек-лист перед прогоном · отмечено {preflightDone} из {PMI_PREFLIGHT.length}</span>
          <ChevronDown size={16} className="ds__preflightChevron" />
        </summary>
        <div className="ds__preflightBody">
          <div className="ds__checks">
            {PMI_PREFLIGHT.map((p) => {
              const on = Boolean(preflight[p.id]);
              return (
                <button
                  type="button"
                  key={p.id}
                  className={`ds__check${on ? ' ds__check--on' : ''}`}
                  onClick={() => togglePreflight(p.id)}
                >
                  <span className="ds__checkBox">{on && <Check size={13} />}</span>
                  <span>
                    <span className="ds__checkText">{p.text}</span>
                    {p.detail && <span className="ds__checkDetail">{p.detail}</span>}
                  </span>
                  {p.item && <span className="ds__checkScene">{p.item}</span>}
                </button>
              );
            })}
          </div>
          <div className="ds__preflightActions">
            <button
              type="button"
              className="annex__btn annex__btn--probe"
              onClick={runEnvProbe}
              disabled={envProbe.status === 'loading'}
            >
              <Play size={14} />
              <span>{envProbe.status === 'loading' ? 'Проверяем…' : 'Проверить окружение'}</span>
            </button>
            <button
              type="button"
              className="annex__btn annex__btn--probe"
              onClick={clearCache}
              disabled={cacheBusy}
              title="POST /cache/clear — нужен перед прогонами А-6 и А-16"
            >
              <RotateCcw size={14} />
              <span>{cacheBusy ? 'Очищаем…' : 'Очистить кэш ответов'}</span>
            </button>
            <button type="button" className="annex__btn annex__btn--ghost" onClick={resetPreflight}>
              <span>Сбросить чек-лист</span>
            </button>
          </div>
          {envProbe.status === 'ok' && (
            <ul className="annex__probeLines">
              {envProbe.lines.map((l, i) => (
                <li key={`${l}-${i}`}>{l}</li>
              ))}
            </ul>
          )}
          {envProbe.status === 'error' && (
            <div className="annex__probeError">
              Стенд недоступен: {envProbe.error}. Проверьте <code>docker compose ps</code> и адрес API.
            </div>
          )}
        </div>
      </details>

      <div className="annex__filters">
        <button
          type="button"
          className={`annex__filter${groupFilter === null ? ' annex__filter--on' : ''}`}
          onClick={() => applyGroupFilter(null)}
        >
          Все {ANNEX_A_ITEMS.length}
        </button>
        {GROUPS.map((g) => (
          <button
            key={g}
            type="button"
            className={`annex__filter${groupFilter === g ? ' annex__filter--on' : ''}`}
            onClick={() => applyGroupFilter(groupFilter === g ? null : g)}
          >
            {g} · {ANNEX_A_ITEMS.filter((i) => i.group === g).length}
          </button>
        ))}
      </div>

      <div className="annex__tabs" role="tablist" aria-label="Контрольные примеры ПМИ" ref={tabsRef}>
        {visible.map((item) => {
          const v = stateOf(item).verdict;
          const defs = checksOf(item.id);
          const done = defs.filter((c) => checks[item.id]?.[c.id]?.status === 'pass').length;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`annex-tab-${item.id}`}
              aria-controls="annex-panel"
              aria-selected={item.id === active.id}
              ref={(el) => {
                tabRefs.current[item.id] = el;
              }}
              className={`annex__tab annex__tab--${v}${item.id === active.id ? ' annex__tab--active' : ''}`}
              onClick={() => setActiveId(item.id)}
              title={`${item.title} · ${item.requirements.map((r) => r.code).join(', ')}${
                defs.length ? ` · автопроверок: ${defs.length} (пройдено ${done})` : ''
              }`}
            >
              <span className="annex__tabVerdict">{VERDICT_META[v].short}</span>
              <span className="annex__tabId">{item.id}</span>
              <span className="annex__tabChecks">{item.requirements.map((r) => r.code).join(' ')}</span>
              {defs.length > 0 && (
                <span className={`annex__tabChecks${done === defs.length ? ' annex__tabChecks--ok' : ''}`}>
                  {done}/{defs.length} проверок
                </span>
              )}
            </button>
          );
        })}
      </div>

      <motion.article
        key={active.id}
        id="annex-panel"
        role="tabpanel"
        aria-labelledby={`annex-tab-${active.id}`}
        className={`annex__panel annex__panel--${activeState.verdict}`}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <header className="annex__panelHead">
          <div>
            <div className="annex__panelKicker">
              Контрольный пример {active.id} · {active.group} · п. {activeIndex + 1} из {ANNEX_A_ITEMS.length}
            </div>
            <h3 className="annex__panelTitle">{active.title}</h3>
            {activeBook?.goal && <div className="ds__goal">{activeBook.goal}</div>}
          </div>
          <div className="annex__verdicts">
            {(Object.keys(VERDICT_META) as PmiVerdict[]).map((v) => (
              <button
                key={v}
                type="button"
                className={`annex__verdict annex__verdict--${v}${activeState.verdict === v ? ' annex__verdict--on' : ''}`}
                onClick={() => setVerdict(active.id, v)}
              >
                {VERDICT_META[v].short} {VERDICT_META[v].label}
              </button>
            ))}
          </div>
        </header>

        <div className="annex__cols">
          <div className="annex__col">
            <h4 className="annex__h">Проверяемые требования (таблица 2 ПМИ)</h4>
            <div className="annex__reqs">
              {active.requirements.map((r) => (
                <div className="annex__req" key={r.code}>
                  <span className={`annex__reqCode annex__reqCode--${activeState.verdict}`}>{r.code}</span>
                  <div>
                    <div className="annex__reqTitle">{r.title}</div>
                    <div className="annex__reqMeta">Пункты ТЗ: {r.tz}</div>
                    <div className="annex__reqMeta">
                      <b>Критерий приёмки:</b> {r.criterion}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <h4 className="annex__h">Шаги проверки (таблица А.1)</h4>
            <ol className="annex__steps">
              {active.steps.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>

            <div className="annex__expected">
              <span className="annex__expectedLabel">Ожидаемый результат</span>
              {active.expected}
            </div>

            {activeBook?.questions?.length ? (
              <>
                <h4 className="annex__h">Вопросы — нажать, чтобы задать в чате</h4>
                <div className="ds__questions">
                  {activeBook.questions.map((q) => (
                    <div className="ds__question" key={q.text}>
                      <button type="button" className="ds__ask" onClick={() => navigate(chatQ(q.text))}>
                        <Send size={13} />
                        <span>{q.text}</span>
                      </button>
                      {q.expect && <div className="ds__qExpect">→ {q.expect}</div>}
                      <button
                        type="button"
                        className="annex__cmdCopy"
                        onClick={() => copyText(q.text, q.text)}
                        title="Скопировать вопрос"
                      >
                        {copiedText === q.text ? <Check size={14} /> : <Copy size={14} />}
                      </button>
                    </div>
                  ))}
                </div>
              </>
            ) : null}

            {active.commands && active.commands.length > 0 && (
              <>
                <h4 className="annex__h">Команды прогона</h4>
                <div className="annex__cmds">
                  {active.commands.map((c) => (
                    <div className="annex__cmd" key={c.cmd}>
                      <div className="annex__cmdTitle">{c.title}</div>
                      <div className="annex__cmdRow">
                        <code>{c.cmd}</code>
                        <button
                          type="button"
                          className="annex__cmdCopy"
                          onClick={() => copyText(c.cmd, c.cmd)}
                          title="Скопировать команду"
                        >
                          {copiedText === c.cmd ? <Check size={14} /> : <Copy size={14} />}
                        </button>
                      </div>
                      {c.expect && <div className="annex__cmdExpect">Ожидание: {c.expect}</div>}
                    </div>
                  ))}
                </div>
              </>
            )}

            {active.artifacts && active.artifacts.length > 0 && (
              <div className="annex__artifacts">
                <span className="annex__artifactsLabel">Артефакты для протокола:</span>
                {active.artifacts.map((a) => (
                  <code key={a}>{a}</code>
                ))}
              </div>
            )}
          </div>

          <div className="annex__col">
            {active.modelSwitch && <ModelSwitcher />}
            {active.benchmarkFive && <BenchmarkFiveRunner />}
            {active.upload && (
              <AnnexUploader
                key={active.id}
                expectFilename={active.upload.expectFilename}
                hint={active.upload.hint}
                onSettled={() => void runCheckList(active, fastChecks, 'Быстрые проверки')}
              />
            )}
            {(activeChecks.length > 0 || active.probe) && (
              <div className="annex__checks">
                <div className="annex__checksHead">
                  <div>
                    <div className="annex__checksTitle">Проверка пункта на живом стенде</div>
                    <div className="annex__checksHint">
                      Настоящие вызовы API: запросы к сервису, загрузка файлов, вопросы агенту. Строки ниже —
                      доказательство, а не оценка. Итоговый статус пункта по-прежнему ставит комиссия.
                    </div>
                  </div>
                  <div className="annex__checksActions">
                    {active.probe && (
                      <button
                        type="button"
                        className="annex__btn annex__btn--probe"
                        onClick={() => runItemProbe(active)}
                        disabled={probe.status === 'loading' || busy}
                        title={active.probe.hint}
                      >
                        <Play size={14} />
                        <span>{probe.status === 'loading' ? 'Снимаем…' : 'Снять показатели'}</span>
                      </button>
                    )}
                    {fastChecks.length > 0 && (
                      <button
                        type="button"
                        className="annex__btn annex__btn--probe"
                        onClick={() => runCheckList(active, fastChecks, 'Быстрые проверки')}
                        disabled={busy}
                        title="Проверки без обращений к модели"
                      >
                        <Play size={14} />
                        <span>Быстрые ({fastChecks.length})</span>
                      </button>
                    )}
                    {fullChecks.length > fastChecks.length && (
                      <button
                        type="button"
                        className="annex__btn annex__btn--probe"
                        onClick={() => runCheckList(active, fullChecks, 'Полный прогон пункта')}
                        disabled={busy}
                        title="Включает запросы к модели — минуты, а не секунды"
                      >
                        <Play size={14} />
                        <span>Полный прогон ({fullChecks.length})</span>
                      </button>
                    )}
                    {checksDone > 0 && (
                      <button
                        type="button"
                        className="annex__btn annex__btn--ghost"
                        onClick={() => resetItemChecks(active.id)}
                        disabled={busy}
                      >
                        <RotateCcw size={14} />
                        <span>Очистить результаты</span>
                      </button>
                    )}
                  </div>
                </div>

                {probe.status === 'ok' && (
                  <ul className="annex__probeLines">
                    {probe.lines.map((l, i) => (
                      <li key={`${l}-${i}`}>{l}</li>
                    ))}
                  </ul>
                )}
                {probe.status === 'error' && (
                  <div className="annex__probeError">
                    Стенд недоступен: {probe.error}. Проверьте <code>docker compose ps</code> и адрес API.
                  </div>
                )}

                {needsFile && (
                  <div className="annex__checkFile">
                    <label className="annex__btn annex__btn--probe annex__btn--file" htmlFor={`file-${active.id}`}>
                      <input
                        id={`file-${active.id}`}
                        type="file"
                        accept=".xlsx,.xls"
                        onChange={(e) => setPickedFile(e.target.files?.[0] ?? null)}
                      />
                      <span>Выбрать .xlsx для проверок</span>
                    </label>
                    <span className="annex__checkFileName">
                      {pickedFile ? `${pickedFile.name} · ${(pickedFile.size / 1024 / 1024).toFixed(2)} MiB` : 'файл не выбран — проверки загрузки запустятся с подсказкой'}
                    </span>
                  </div>
                )}

                {hasDestructive && (
                  <label className="annex__checkFlag">
                    <input
                      type="checkbox"
                      checked={allowDestructive}
                      onChange={(e) => setAllowDestructive(e.target.checked)}
                    />
                    <span>
                      Разрешить удаление данных (А-12 удаляет эталонный файл с тестового стенда; после него
                      нужно загрузить файл заново)
                    </span>
                  </label>
                )}

                {activeChecks.length > 0 && (
                  <ul className="annex__checkList">
                    {activeChecks.map((c) => {
                      const key = `${active.id}:${c.id}`;
                      const progressText = running[key];
                      const isRunning = progressText !== undefined;
                      const res = activeResults[c.id];
                      return (
                        <li key={c.id} className={`annex__check${res ? ` annex__check--${res.status}` : ''}`}>
                          <div className="annex__checkRow">
                            <span className={`annex__checkMark${res ? ` annex__checkMark--${res.status}` : ''}`}>
                              {isRunning ? '…' : res ? { pass: '✓', fail: '✕', error: '!' }[res.status] : '□'}
                            </span>
                            <div className="annex__checkBody">
                              <div className="annex__checkTitle">{c.title}</div>
                              <div className="annex__checkCriterion">
                                <b>Критерий:</b> {c.criterion}
                              </div>
                              <div className="annex__checkMeta">
                                {c.slow && <span className="annex__checkTag annex__checkTag--slow">долго: запрос к модели</span>}
                                {c.destructive && <span className="annex__checkTag annex__checkTag--danger">удаляет данные</span>}
                                {c.needsFile && <span className="annex__checkTag">нужен выбранный файл</span>}
                                {res && !isRunning && <span className="annex__checkTag">в {res.at}</span>}
                              </div>
                              {isRunning && <div className="annex__checkProgress">{progressText || 'Выполняется…'}</div>}
                              {res && !isRunning && (
                                <>
                                  <div className="annex__checkSummary">{res.summary}</div>
                                  {res.requestId && (
                                    <button
                                      type="button"
                                      className="annex__link annex__link--trace"
                                      onClick={() => navigate(`/trace?request_id=${encodeURIComponent(res.requestId!)}`)}
                                      title="Открыть трассу этого запроса: узлы, входы/результаты, SQL"
                                    >
                                      Трасса запроса {res.requestId.slice(0, 8)}… →
                                    </button>
                                  )}
                                  {res.lines.length > 0 && (
                                    <ul className="annex__checkLines">
                                      {res.lines.map((l, i) => (
                                        <li key={`${c.id}-${i}`}>{l}</li>
                                      ))}
                                    </ul>
                                  )}
                                  {res.chart && res.chart.data.length > 0 && (
                                    <div className="annex__chart">
                                      <div className="annex__h">
                                        График, построенный проверкой ({res.chart.data.length} точек)
                                      </div>
                                      <ResultChart data={res.chart.data} chartType={res.chart.kind} />
                                    </div>
                                  )}
                                </>
                              )}
                            </div>
                            <button
                              type="button"
                              className="annex__btn annex__btn--probe"
                              onClick={() => runOneCheck(active, c)}
                              disabled={busy}
                            >
                              <Play size={14} />
                              <span>{isRunning ? 'Выполняется…' : 'Запустить'}</span>
                            </button>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}

                {activeChecks.length > 0 && (
                  <div className="annex__checksFoot">
                    По пункту пройдено {checksPassed} автопроверок из {activeChecks.length}
                  </div>
                )}
              </div>
            )}

            {active.facts && active.facts.length > 0 && (
              <>
                <h4 className="annex__h">Данные проверки</h4>
                <dl className="annex__facts">
                  {active.facts.map((f) => (
                    <div className={`annex__fact${f.tone ? ` annex__fact--${f.tone}` : ''}`} key={f.label}>
                      <dt>{f.label}</dt>
                      <dd>{f.value}</dd>
                    </div>
                  ))}
                </dl>
              </>
            )}

            {active.tables?.map((t) => (
              <div className="annex__tableWrap" key={t.title}>
                <h4 className="annex__h">{t.title}</h4>
                <div className="annex__tableScroll">
                  <table className={`annex__table${t.tone === 'risk' ? ' annex__table--risk' : ''}`}>
                    <thead>
                      <tr>
                        {t.columns.map((c) => (
                          <th key={c}>{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {t.rows.map((row) => (
                        <tr key={row.join('|')}>
                          {row.map((cell, ci) => (
                            <td key={`${row.join('-')}-${ci}`} className={ci === 0 ? 'annex__tableKey' : ''}>
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {t.note && <div className="annex__tableNote">{t.note}</div>}
              </div>
            ))}

            {active.sql?.map((s) => (
              <div className="annex__sql" key={s.title}>
                <div className="annex__h">{s.title}</div>
                <SqlBlock sql={s.text} onCopy={(t) => copyText(s.title, t)} />
              </div>
            ))}

            {active.charts?.map((c) => (
              <div className="annex__chart" key={c.title}>
                <div className="annex__h">{c.title}</div>
                <ResultChart data={c.data} chartType={c.kind} />
                {c.note && <div className="annex__chartNote">{c.note}</div>}
              </div>
            ))}
          </div>
        </div>

        {activeBook?.speech && (
          <div className="ds__speech">
            <div className="ds__speechHead">
              <span className="annex__h">Речь для комиссии — читается вслух</span>
              <button
                type="button"
                className="annex__btn annex__btn--probe"
                onClick={() => copyText(active.id, activeBook.speech ?? '')}
              >
                {copiedText === active.id ? <Check size={14} /> : <Copy size={14} />}
                <span>{copiedText === active.id ? 'Скопировано' : 'Копировать речь'}</span>
              </button>
            </div>
            <p className="ds__speechText">{activeBook.speech}</p>
          </div>
        )}

        {activeBook?.tips?.length ? (
          <>
            <h4 className="annex__h">Замечания по показу этого пункта</h4>
            <ul className="ds__tips">
              {activeBook.tips.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </>
        ) : null}

        {activeBook?.defense?.length ? (
          <div className="ds__defense">
            <h4 className="annex__h">Вероятные вопросы комиссии — что отвечать</h4>
            {activeBook.defense.map((d) => (
              <details className="ds__qa" key={d.q}>
                <summary className="ds__qaQ">
                  <ChevronDown size={15} className="ds__qaChevron" />
                  <span>{d.q}</span>
                </summary>
                <div className="ds__qaA">{d.a}</div>
              </details>
            ))}
          </div>
        ) : null}

        <div className="annex__foot">
          <div className="annex__footCol">
            <label className="annex__h" htmlFor={`note-${active.id}`}>
              Фактический результат / замечание комиссии
            </label>
            <textarea
              id={`note-${active.id}`}
              className="annex__note"
              rows={3}
              value={activeState.note}
              placeholder="Например: выполнено 02.11.2026, стенд ЕВРАЗ-2, модель …; замечаний нет"
              onChange={(e) => setNote(active.id, e.target.value)}
            />
          </div>
          <div className="annex__footCol annex__footCol--links">
            {(active.links ?? []).map((l) => (
              <button
                key={l.label}
                type="button"
                className="annex__link"
                onClick={() => (l.href ? window.open(l.href, '_blank', 'noopener') : navigate(l.to as string))}
              >
                {l.label} →
              </button>
            ))}
            <div className="annex__nav">
              <button
                type="button"
                className="annex__navBtn"
                onClick={() => setActiveId(ANNEX_A_ITEMS[Math.max(activeIndex - 1, 0)].id)}
                disabled={activeIndex === 0}
              >
                <ChevronLeft size={15} />
                {ANNEX_A_ITEMS[Math.max(activeIndex - 1, 0)].id}
              </button>
              <span className="annex__navHint">← / → — переключение пунктов</span>
              <button
                type="button"
                className="annex__navBtn"
                onClick={() =>
                  setActiveId(ANNEX_A_ITEMS[Math.min(activeIndex + 1, ANNEX_A_ITEMS.length - 1)].id)
                }
                disabled={activeIndex === ANNEX_A_ITEMS.length - 1}
              >
                {ANNEX_A_ITEMS[Math.min(activeIndex + 1, ANNEX_A_ITEMS.length - 1)].id}
                <ChevronRight size={15} />
              </button>
            </div>
          </div>
        </div>
      </motion.article>

      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </section>
  );
}
