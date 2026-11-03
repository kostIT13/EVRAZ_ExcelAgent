import { useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, RotateCcw, Square } from 'lucide-react';
import { api } from '@/api';
import { DEMO_FIVE } from '@/data/pmiRunBook';
import { findMatch, fmt, numbersIn, type AskCase } from '@/lib/pmiChecks';

type RowState = 'idle' | 'running' | 'done' | 'error';

interface Row {
  item: AskCase;
  state: RowState;
  ok?: boolean;
  found?: number;
  latencyMs?: number;
  /** null — стенд не отдаёт флаг кэша (образ собран раньше поля). */
  fromCache?: boolean | null;
  requestId?: string;
  error?: string;
}

/** Тот же допуск сравнения, что у автопроверок прогона и у benchmark_core. */
const TOLERANCE_PCT = 1;

const freshRows = (): Row[] => DEMO_FIVE.map((item) => ({ item, state: 'idle' as RowState }));

const secs = (ms: number) => `${(ms / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} с`;

/**
 * Прогон пяти задач Заказчика прямо в карточке А-6 — то же, что
 * `python benchmark/run_first5.py`, но из браузера и без очистки кэша:
 * уже отвечённые стендом вопросы приходят за миллисекунды, поэтому
 * «бенчмарк» помещается в несколько секунд показа комиссии.
 */
export default function BenchmarkFiveRunner() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<Row[]>(freshRows);
  const [running, setRunning] = useState(false);
  const [clearFirst, setClearFirst] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const cancelRef = useRef(false);

  const patch = (idx: number, next: Partial<Row>) =>
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...next } : r)));

  const run = useCallback(async () => {
    setRunning(true);
    setNote(null);
    setElapsedMs(null);
    cancelRef.current = false;
    setRows(freshRows());

    if (clearFirst) {
      try {
        const res = await api.clearCache();
        setNote(`Кэш очищен (${res.cleared} ответов) — все пять вопросов считаются заново, это 3–6 минут.`);
      } catch (e) {
        setNote(`Кэш очистить не удалось (${(e as Error).message}) — пройдёт по текущему кэшу.`);
      }
    }

    const started = performance.now();
    for (let i = 0; i < DEMO_FIVE.length; i += 1) {
      if (cancelRef.current) break;
      patch(i, { state: 'running' });
      const item = DEMO_FIVE[i];
      try {
        const a = await api.askQuestion({ question: item.question, response_mode: 'detailed' });
        const found = findMatch(numbersIn(a.answer), item.expect, TOLERANCE_PCT);
        patch(i, {
          state: 'done',
          ok: found !== undefined,
          found,
          latencyMs: a.latency_ms,
          fromCache: typeof a.from_cache === 'boolean' ? a.from_cache : null,
          requestId: a.request_id,
        });
      } catch (e) {
        patch(i, { state: 'error', error: (e as Error).message });
      }
    }
    setElapsedMs(Math.round(performance.now() - started));
    setRunning(false);
  }, [clearFirst]);

  const stop = () => {
    cancelRef.current = true;
    setNote('Останавливаем после текущего вопроса — посчитанные строки остаются.');
  };

  const reset = () => {
    setRows(freshRows());
    setNote(null);
    setElapsedMs(null);
  };

  const done = rows.filter((r) => r.state === 'done' || r.state === 'error');
  const okCount = rows.filter((r) => r.ok).length;
  const known = rows.filter((r) => typeof r.fromCache === 'boolean');
  const cacheHits = known.filter((r) => r.fromCache).length;
  const finished = !running && done.length > 0;
  const complete = done.length === rows.length;
  const rate = rows.length ? Math.round((okCount / rows.length) * 1000) / 10 : 0;
  const progress = rows.findIndex((r) => r.state === 'running');

  const cacheSummary = !known.length
    ? 'флаг кэша образ сервиса не отдаёт — пересоберите service'
    : `из кэша ${cacheHits} из ${known.length}`;

  return (
    <div className="b5">
      <div className="b5__head">
        <div>
          <div className="b5__title">Прогон пяти задач Заказчика — как бенчмарк, но из браузера</div>
          <div className="b5__hint">
            Те же пять вопросов и то же правило сравнения (допуск {TOLERANCE_PCT} %), что у{' '}
            <code>python benchmark/run_first5.py</code>. Кэш перед прогоном не чистим: вопросы,
            на которые стенд уже отвечал, приходят за миллисекунды — прогон занимает секунды и
            показывает то же число правильных ответов. Новый вопрос считается 30–80 с.
          </div>
        </div>
        <div className="b5__actions">
          {running ? (
            <button type="button" className="annex__btn annex__btn--ghost" onClick={stop}>
              <Square size={14} />
              <span>Стоп после текущего</span>
            </button>
          ) : (
            <button type="button" className="annex__btn annex__btn--probe" onClick={run}>
              <Play size={14} />
              <span>Запустить прогон (5)</span>
            </button>
          )}
          {done.length > 0 && !running && (
            <button type="button" className="annex__btn annex__btn--ghost" onClick={reset}>
              <RotateCcw size={14} />
              <span>Сбросить</span>
            </button>
          )}
        </div>
      </div>

      <label className="b5__flag">
        <input
          type="checkbox"
          checked={clearFirst}
          onChange={(e) => setClearFirst(e.target.checked)}
          disabled={running}
        />
        <span>
          Очистить кэш перед прогоном (<code>POST /cache/clear</code>) — ответы считаются заново,
          3–6 минут; так видно, что цифра посчитана агентом заново, а не взята из кэша.
        </span>
      </label>

      {running && (
        <div className="b5__progress">
          Считаем вопрос {progress >= 0 ? progress + 1 : done.length + 1} из {rows.length}…
        </div>
      )}

      {finished && complete && (
        <div className={`b5__verdict${okCount === rows.length ? ' b5__verdict--ok' : ' b5__verdict--warn'}`}>
          PASS RATE: {rate.toLocaleString('ru-RU')} % · {okCount} из {rows.length} · {cacheSummary}
          {elapsedMs !== null ? ` · ${secs(elapsedMs)}` : ''}
        </div>
      )}

      {finished && !complete && (
        <div className="b5__verdict b5__verdict--warn">
          Прогон не завершён: посчитано {done.length} из {rows.length} · верно {okCount} — доля
          правильных считается только по полному прогону
        </div>
      )}

      {note && <div className="b5__note">{note}</div>}

      <ol className="b5__list">
        {rows.map((r, idx) => (
          <li key={r.item.question} className={`b5__row b5__row--${r.state}`}>
            <span className="b5__mark">
              {r.state === 'running' ? '…' : r.state === 'error' ? '!' : r.state === 'done' ? (r.ok ? '✓' : '✕') : idx + 1}
            </span>
            <div className="b5__body">
              <div className="b5__q">{r.item.question}</div>
              <div className="b5__meta">
                <span className="b5__tag">{r.item.label ?? `вопрос ${idx + 1}`}</span>
                <span className="b5__tag">эталон {fmt(r.item.expect)}</span>
                {r.state === 'done' && (
                  <>
                    <span className={`b5__tag b5__tag--${r.ok ? 'ok' : 'bad'}`}>
                      {r.ok ? `в ответе ${fmt(r.found ?? 0)}` : 'эталонного числа в ответе нет'}
                    </span>
                    <span className="b5__tag">{r.latencyMs} мс</span>
                    <span className={`b5__tag${r.fromCache ? ' b5__tag--cache' : ''}`}>
                      {r.fromCache === null
                        ? 'флаг кэша недоступен'
                        : r.fromCache
                          ? 'из кэша'
                          : 'посчитано заново'}
                    </span>
                  </>
                )}
                {r.state === 'error' && <span className="b5__tag b5__tag--bad">сбой запроса</span>}
              </div>
              {r.error && <div className="b5__err">{r.error}</div>}
              {r.requestId && (
                <button
                  type="button"
                  className="annex__link"
                  onClick={() => navigate(`/trace?request_id=${encodeURIComponent(r.requestId!)}`)}
                  title="Трасса этого ответа: узлы, SQL, длительность"
                >
                  Трасса запроса {r.requestId.slice(0, 8)}… →
                </button>
              )}
            </div>
          </li>
        ))}
      </ol>

      <div className="b5__foot">
        Полный набор К-1 (44 вопроса) и разбивка по типам — <code>python benchmark/run_all.py</code>;
        здесь только пять задач Заказчика из таблицы А.1.
      </div>
    </div>
  );
}
