import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  Play,
  RotateCcw,
} from 'lucide-react';
import ResultChart from '@/components/chat/ResultChart';
import SqlBlock from '@/components/chat/SqlBlock';
import { ToastContainer } from '@/components/ui/Toast';
import { useToast } from '@/hooks/useToast';
import { api } from '@/api';
import {
  ANNEX_A_ITEMS,
  VERDICT_META,
  type AnnexItem,
  type PmiVerdict,
  type ProbeKind,
} from '@/data/pmiAnnexA';

const STORAGE_KEY = 'evraz.pmi.annexA.v1';
const GROUPS = ['Функциональные', 'Качество', 'Надёжность', 'Безопасность', 'Совместимость'] as const;

interface ItemState {
  verdict: PmiVerdict;
  note: string;
}

type Stored = Record<string, ItemState>;

interface ProbeState {
  status: 'idle' | 'loading' | 'ok' | 'error';
  lines: string[];
  error?: string;
}

const IDLE_PROBE: ProbeState = { status: 'idle', lines: [] };

function loadStored(): Stored {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Stored) : {};
  } catch {
    return {};
  }
}

function saveStored(value: Stored) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    /* приватный режим браузера — статусы живут только до перезагрузки */
  }
}

async function runProbe(kind: ProbeKind): Promise<string[]> {
  if (kind === 'health') {
    const health = await api.checkHealth();
    const entries = Object.entries(health);
    return entries.length
      ? entries.map(([k, v]) => `${k}: ${String(v)}`)
      : ['backend отвечает'];
  }

  if (kind === 'files') {
    const res = await api.listFiles({ limit: 20 });
    return [
      `зарегистрировано файлов: ${res.total}`,
      ...res.files.slice(0, 8).map(
        (f) =>
          `${f.filename} · ${f.status} · листов ${f.total_sheets} · строк ${f.total_rows} · SHA-256 ${f.file_hash.slice(0, 12)}…`,
      ),
    ];
  }

  if (kind === 'traces') {
    const res = await api.listTraces({ limit: 8 });
    return [
      `записей в журнале трасс: ${res.total}`,
      ...res.items.slice(0, 6).map(
        (i) => `${i.status} · ${i.latency_ms} мс · ${i.question.slice(0, 70)}${i.question.length > 70 ? '…' : ''}`,
      ),
    ];
  }

  if (kind === 'metrics') {
    const m = await api.getMetricsSummary();
    const statuses = Object.entries(m.requests_by_status ?? {})
      .map(([k, v]) => `${k}: ${v}`)
      .join(', ');
    return [
      `запросов: ${m.total_requests}${statuses ? ` (${statuses})` : ''}`,
      `доля успешных: ${m.success_rate ?? '—'} % · p50 ${m.latency_p50_ms ?? '—'} мс · p95 ${m.latency_p95_ms ?? '—'} мс`,
      `токены LLM: ${m.total_tokens} · стоимость: ${m.total_cost_rub} руб.`,
      `кэш: ${m.cache_hits ?? 0} попаданий (${m.cache_hit_rate ?? 0} %)`,
    ];
  }

  const c = await api.getLlmConfig();
  return [
    `model: ${c.model}`,
    `temperature ${c.temperature} · max_tokens ${c.max_tokens}`,
    `таймаут ${c.request_timeout_s} с · повторов LLM ${c.llm_max_retries} · повторов графа ${c.graph_max_retry_count} · попыток codegen ${c.max_codegen_attempts}`,
    'поля с API-ключом в ответе нет',
  ];
}

function protocolMarkdown(states: Stored): string {
  const date = new Date().toLocaleString('ru-RU');
  const lines = [
    'ПРОТОКОЛ ПРИЁМОЧНЫХ ИСПЫТАНИЙ № ___',
    'Excel-агент ЕВРАЗ — приложение А (контрольные примеры А-1…А-17)',
    `Заполнен: ${date}`,
    '',
    '| № | Пример | Покрывает | Критерий приёмки | Фактический результат | Пройдено |',
    '|---|--------|-----------|------------------|---------------------|----------|',
  ];

  ANNEX_A_ITEMS.forEach((item, idx) => {
    const state = states[item.id] ?? { verdict: item.verdict, note: item.note ?? '' };
    const checks = item.requirements.map((r) => r.code).join(', ');
    const criteria = item.requirements.map((r) => `${r.code}: ${r.criterion}`).join('; ');
    const fact = (state.note || item.note || VERDICT_META[state.verdict].label).replace(/\|/g, '/');
    const passed =
      state.verdict === 'pass' ? 'да' : state.verdict === 'warn' ? 'с оговоркой' : state.verdict === 'fail' ? 'нет' : '—';
    lines.push(`| ${idx + 1} | ${item.id} · ${item.title} | ${checks} | ${criteria} | ${fact} | ${passed} |`);
  });

  const counts = ANNEX_A_ITEMS.reduce<Record<string, number>>((acc, item) => {
    const v = states[item.id]?.verdict ?? item.verdict;
    acc[v] = (acc[v] ?? 0) + 1;
    return acc;
  }, {});

  lines.push(
    '',
    `Итог: пройдено ${counts.pass ?? 0} · с оговоркой ${counts.warn ?? 0} · не пройдено ${counts.fail ?? 0} · предстоит ${counts.todo ?? 0} (всего 17).`,
    'Выводы: ____________________  Председатель комиссии: ______________  Члены комиссии: ______________',
  );

  return lines.join('\n');
}

export default function AnnexRunner() {
  const navigate = useNavigate();
  const { toasts, showToast, dismiss } = useToast();
  const [activeId, setActiveId] = useState<string>(ANNEX_A_ITEMS[0].id);
  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const [stored, setStored] = useState<Stored>(() => loadStored());
  const [probes, setProbes] = useState<Record<string, ProbeState>>({});
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);
  const tabsRef = useRef<HTMLDivElement | null>(null);
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const visible = useMemo(
    () => (groupFilter ? ANNEX_A_ITEMS.filter((i) => i.group === groupFilter) : ANNEX_A_ITEMS),
    [groupFilter],
  );

  const active: AnnexItem = ANNEX_A_ITEMS.find((i) => i.id === activeId) ?? ANNEX_A_ITEMS[0];

  // Полоса вкладок скроллится по горизонтали — активную удерживаем в зоне видимости.
  useEffect(() => {
    const wrap = tabsRef.current;
    const tab = tabRefs.current[activeId];
    if (!wrap || !tab) return;
    const target = tab.offsetLeft - (wrap.clientWidth - tab.offsetWidth) / 2;
    const max = wrap.scrollWidth - wrap.clientWidth;
    wrap.scrollTo({ left: Math.min(Math.max(target, 0), max), behavior: 'smooth' });
  }, [activeId, groupFilter]);

  const stateOf = useCallback(
    (item: AnnexItem): ItemState => stored[item.id] ?? { verdict: item.verdict, note: item.note ?? '' },
    [stored],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === 'TEXTAREA' || tag === 'INPUT') return;
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      const idx = ANNEX_A_ITEMS.findIndex((i) => i.id === activeId);
      const next =
        e.key === 'ArrowRight'
          ? ANNEX_A_ITEMS[Math.min(idx + 1, ANNEX_A_ITEMS.length - 1)]
          : ANNEX_A_ITEMS[Math.max(idx - 1, 0)];
      setActiveId(next.id);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [activeId]);

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
    saveStored(next);
  };

  const setNote = (id: string, note: string) => {
    const base = stateOf(ANNEX_A_ITEMS.find((i) => i.id === id) as AnnexItem);
    const next = { ...stored, [id]: { ...base, note } };
    setStored(next);
    saveStored(next);
  };

  const resetAll = () => {
    setStored({});
    saveStored({});
    showToast('Статусы сброшены к данным прогона-репетиции', 'info');
  };

  const copyCommand = (cmd: string) => {
    navigator.clipboard.writeText(cmd).then(() => {
      setCopiedCmd(cmd);
      showToast('Команда скопирована', 'success');
      window.setTimeout(() => setCopiedCmd(null), 1600);
    });
  };

  const copySql = (sqlText: string) => {
    navigator.clipboard.writeText(sqlText).then(() => showToast('SQL запрос скопирован', 'success'));
  };

  const copyProtocol = () => {
    navigator.clipboard.writeText(protocolMarkdown(stored)).then(() =>
      showToast('Протокол (приложение Б) скопирован в буфер обмена', 'success'),
    );
  };

  const downloadProtocol = () => {
    const blob = new Blob([protocolMarkdown(stored)], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pmi_protocol_annex_a_${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

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

  const counts = useMemo(() => {
    const acc: Record<PmiVerdict, number> = { pass: 0, warn: 0, fail: 0, todo: 0 };
    ANNEX_A_ITEMS.forEach((item) => {
      acc[stateOf(item).verdict] += 1;
    });
    return acc;
  }, [stateOf]);

  const progress = Math.round(((counts.pass + counts.warn * 0.5) / ANNEX_A_ITEMS.length) * 100);
  const probe = probes[active.id] ?? IDLE_PROBE;
  const activeState = stateOf(active);
  const activeIndex = ANNEX_A_ITEMS.findIndex((i) => i.id === active.id);

  return (
    <section className="annex">
      <div className="annex__head">
        <div>
          <h2 className="demo__title">Прогон ПМИ: 17 контрольных примеров</h2>
          <p className="demo__subtitle">
            Вкладка на каждый пункт приложения А (таблица А.1): шаги и ожидаемый результат дословно из ПМИ,
            проверяемые требования с пунктами ТЗ и критериями приёмки, фактические данные стенда, команды
            и ссылки на разделы системы. Статусы и замечания правятся на месте и сохраняются в браузере —
            итог выгружается в таблицу протокола (приложение Б).
            Общие предусловия (раздел 5 ПМИ): система развёрнута, модель подключена, эталонные файлы
            загружены — кроме А-1 и А-17, где файл и стенд готовятся в ходе проверки.
          </p>
        </div>
        <div className="annex__headActions">
          <button type="button" className="annex__btn" onClick={copyProtocol}>
            <Copy size={15} />
            <span>Протокол в буфер</span>
          </button>
          <button type="button" className="annex__btn" onClick={downloadProtocol}>
            <Download size={15} />
            <span>Скачать .md</span>
          </button>
          <button type="button" className="annex__btn annex__btn--ghost" onClick={resetAll}>
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
        </div>
      </div>

      <div className="annex__filters">
        <button
          type="button"
          className={`annex__filter${groupFilter === null ? ' annex__filter--on' : ''}`}
          onClick={() => applyGroupFilter(null)}
        >
          Все 17
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
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={item.id === active.id}
              ref={(el) => {
                tabRefs.current[item.id] = el;
              }}
              className={`annex__tab annex__tab--${v}${item.id === active.id ? ' annex__tab--active' : ''}`}
              onClick={() => setActiveId(item.id)}
              title={`${item.title} · ${item.requirements.map((r) => r.code).join(', ')}`}
            >
              <span className="annex__tabVerdict">{VERDICT_META[v].short}</span>
              <span className="annex__tabId">{item.id}</span>
              <span className="annex__tabChecks">{item.requirements.map((r) => r.code).join(' ')}</span>
            </button>
          );
        })}
      </div>

      <motion.article
        key={active.id}
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
                          onClick={() => copyCommand(c.cmd)}
                          title="Скопировать команду"
                        >
                          {copiedCmd === c.cmd ? <Check size={14} /> : <Copy size={14} />}
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
            {active.probe && (
              <div className="annex__probe">
                <div className="annex__probeHead">
                  <div>
                    <div className="annex__probeTitle">{active.probe.title}</div>
                    <div className="annex__probeHint">{active.probe.hint}</div>
                  </div>
                  <button
                    type="button"
                    className="annex__btn annex__btn--probe"
                    onClick={() => runItemProbe(active)}
                    disabled={probe.status === 'loading'}
                  >
                    <Play size={14} />
                    <span>{probe.status === 'loading' ? 'Проверяем…' : 'Проверить сейчас'}</span>
                  </button>
                </div>
                {probe.status === 'ok' && (
                  <ul className="annex__probeLines">
                    {probe.lines.map((l) => (
                      <li key={l}>{l}</li>
                    ))}
                  </ul>
                )}
                {probe.status === 'error' && (
                  <div className="annex__probeError">
                    Стенд недоступен: {probe.error}. Проверьте <code>docker compose ps</code> и адрес API.
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
                <SqlBlock sql={s.text} onCopy={copySql} />
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
