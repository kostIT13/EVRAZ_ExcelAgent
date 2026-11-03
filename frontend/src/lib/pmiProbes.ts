import { api } from '@/api';
import type { ProbeKind } from '@/data/pmiAnnexA';

export interface ProbeState {
  status: 'idle' | 'loading' | 'ok' | 'error';
  lines: string[];
  error?: string;
}

export const IDLE_PROBE: ProbeState = { status: 'idle', lines: [] };

/** Живая проверка стенда для карточки контрольного примера или сцены демо. */
export async function runProbe(kind: ProbeKind): Promise<string[]> {
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
