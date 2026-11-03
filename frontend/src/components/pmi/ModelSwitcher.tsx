import { useCallback, useEffect, useState } from 'react';
import { RotateCcw, Zap } from 'lucide-react';
import { api } from '@/api';
import type { LlmModelsResponse, LlmModelSwitchResponse } from '@/types/api';

/**
 * Горячая смена модели прямо в карточке А-5: интерфейс предлагает только те
 * модели, которые отдал прокси, и подтверждает смену отдельным чтением
 * GET /llm/config. Переключение живёт в памяти сервиса — для приёмки Ф-4
 * по-прежнему правится .env и контейнер пересоздаётся.
 */
export default function ModelSwitcher() {
  const [current, setCurrent] = useState('');
  const [envModel, setEnvModel] = useState('');
  const [models, setModels] = useState<LlmModelsResponse | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);
  const [target, setTarget] = useState('');
  const [verify, setVerify] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<LlmModelSwitchResponse | null>(null);
  const [confirmed, setConfirmed] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshCurrent = useCallback(async () => {
    const c = await api.getLlmConfig();
    setCurrent(c.model);
    return c.model;
  }, []);

  useEffect(() => {
    refreshCurrent().catch(() => setError('Стенд не отвечает — GET /llm/config недоступен'));
  }, [refreshCurrent]);

  const loadModels = useCallback(async () => {
    setLoadingModels(true);
    setError(null);
    try {
      const res = await api.listLlmModels();
      setModels(res);
      setEnvModel(res.default);
      setCurrent(res.current);
    } catch (e) {
      setError(`Не удалось прочитать список моделей: ${(e as Error).message}`);
    } finally {
      setLoadingModels(false);
    }
  }, []);

  const onToggle = (open: boolean) => {
    if (open && !models && !loadingModels) void loadModels();
  };

  const apply = async () => {
    const model = target.trim();
    if (!model) return;
    setBusy(true);
    setResult(null);
    setError(null);
    setConfirmed(null);
    try {
      const res = await api.switchLlmModel(model, verify);
      setResult(res);
      // Смена считается подтверждённой только по независимому чтению конфигурации.
      const now = await refreshCurrent();
      setConfirmed(now === res.current);
      setTarget('');
    } catch (e) {
      setError((e as Error).message);
      await refreshCurrent().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    setResult(null);
    setError(null);
    setConfirmed(null);
    try {
      const res = await api.resetLlmModel();
      setResult(res);
      const now = await refreshCurrent();
      setConfirmed(now === res.current);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const inList = Boolean(models?.models.includes(target));
  const canApply = Boolean(target.trim()) && !busy && target.trim() !== current;

  return (
    <details className="ms" onToggle={(e) => onToggle((e.target as HTMLDetailsElement).open)}>
      <summary className="ms__summary">
        <Zap size={15} />
        <span className="ms__title">Сменить модель прямо здесь</span>
        <code className="ms__current">{current || '—'}</code>
        {envModel && envModel !== current && (
          <span className="ms__badge">в .env: {envModel}</span>
        )}
      </summary>

      <div className="ms__body">
        <div className="ms__hint">
          Модель меняется в памяти запущенного сервиса — код и <code>.env</code> не трогаем. Это
          живая демонстрация Ф-4; запись приёмки про смену в файле конфигурации остаётся за
          правкой <code>.env</code> и <code>docker compose up -d --force-recreate service</code>.
        </div>

        {loadingModels && <div className="ms__muted">Читаем список моделей с прокси…</div>}
        {models && !models.listed && (
          <div className="ms__muted">
            Прокси не отдал список ({models.error || 'нет ответа'}) — введите идентификатор модели
            вручную.
          </div>
        )}

        <div className="ms__row">
          <select
            className="ms__select"
            aria-label="Модель из списка прокси"
            value={inList ? target : ''}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value="">— выбрать из списка прокси —</option>
            {models?.models.map((m) => (
              <option key={m} value={m}>
                {m}
                {m === current ? ' · текущая' : ''}
              </option>
            ))}
          </select>
          <input
            className="ms__input"
            aria-label="Идентификатор модели вручную"
            value={target}
            placeholder="…или ввести вручную"
            onChange={(e) => setTarget(e.target.value)}
          />
        </div>

        <label className="ms__flag">
          <input type="checkbox" checked={verify} onChange={(e) => setVerify(e.target.checked)} />
          <span>
            Сначала получить ответ модели-кандидата (1 токен, 1–5 с). Если модель на прокси не
            найдена — переключение отклоняется, текущая остаётся.
          </span>
        </label>

        <div className="ms__actions">
          <button type="button" className="annex__btn annex__btn--probe" onClick={apply} disabled={!canApply}>
            <Zap size={14} />
            <span>{busy ? 'Меняем…' : 'Применить и проверить'}</span>
          </button>
          <button
            type="button"
            className="annex__btn annex__btn--ghost"
            onClick={reset}
            disabled={busy || !current || current === envModel}
            title="POST /llm/model/reset — вернуть LLM_MODEL_PRIMARY из .env"
          >
            <RotateCcw size={14} />
            <span>Вернуть как в .env</span>
          </button>
        </div>

        {result && (
          <ul className="ms__lines">
            <li>
              было <code>{result.previous}</code> → стало <code>{result.current}</code>
              {result.changed ? '' : ' · значение не изменилось'}
            </li>
            <li>
              {result.verified
                ? `проверочный вызов прошёл за ${result.probe_ms} мс`
                : 'проверочный вызов не выполнялся'}
            </li>
            <li>
              GET /llm/config:{' '}
              {confirmed === null
                ? 'сверяем…'
                : confirmed
                  ? `подтверждает ${result.current}`
                  : 'НЕ подтверждает смену'}
            </li>
            <li className="ms__muted">{result.note}</li>
          </ul>
        )}

        {error && <div className="ms__error">{error}</div>}
      </div>
    </details>
  );
}
