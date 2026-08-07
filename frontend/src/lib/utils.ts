export const EVRAZ_COLORS = {
  red: '#E31837',
  gold: '#C8A84E',
  navy: '#003057',
  navyLight: '#004a7a',
  steel: '#4A4E54',
  silver: '#8A8D8F',
  white: '#F5F5F5',
} as const;

export const CHART_COLORS = [
  EVRAZ_COLORS.red,
  EVRAZ_COLORS.gold,
  '#22d3ee',
  '#a78bfa',
  '#34d399',
  '#fbbf24',
  '#f87171',
  '#60a5fa',
  EVRAZ_COLORS.navyLight,
  EVRAZ_COLORS.steel,
];

export function formatDate(dateStr?: string | null): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU');
}

export function formatMs(ms?: number | null): string {
  if (!ms) return '';
  if (ms < 1000) return `${ms} мс`;
  return `${(ms / 1000).toFixed(2)} с`;
}

export function confidenceLabel(score: number) {
  if (score >= 0.7) return { text: 'Высокая', cls: 'high' };
  if (score >= 0.4) return { text: 'Средняя', cls: 'medium' };
  return { text: 'Низкая', cls: 'low' };
}

export function modeLabel(mode: string) {
  const labels: Record<string, { text: string; cls: string }> = {
    rag: { text: 'RAG', cls: 'rag' },
    agent: { text: 'Agent', cls: 'agent' },
    rag_fallback: { text: 'RAG (fallback)', cls: 'rag_fallback' },
    auto: { text: 'Auto', cls: 'auto' },
  };
  return labels[mode] || { text: mode, cls: '' };
}

export function shortId(id?: string | null): string {
  return id ? id.slice(0, 8) : '?';
}