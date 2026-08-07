import { useEffect, useRef } from 'react';
import { Chart, registerables } from 'chart.js';
import { EVRAZ_COLORS, CHART_COLORS } from '@/lib/utils';

Chart.register(...registerables);

interface ResultChartProps {
  data: unknown[];
}

function isNumericString(v: unknown): boolean {
  return typeof v === 'string' && !Number.isNaN(parseFloat(v));
}

export default function ResultChart({ data }: ResultChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data || data.length === 0) return;

    const preview = data as Array<Record<string, unknown>>;
    const keys = Object.keys(preview[0] || {});
    if (keys.length < 2) return;

    let labelKey = keys[0];
    let valueKey = keys[1];

    for (const key of keys) {
      const sample = preview[0][key];
      if (
        (typeof sample === 'number' || isNumericString(sample)) &&
        key !== labelKey
      ) {
        valueKey = key;
        break;
      }
    }

    const labels = preview.map((r) => String(r[labelKey] ?? ''));
    const values = preview.map((r) => {
      const v = parseFloat(String(r[valueKey]));
      return Number.isNaN(v) ? 0 : v;
    });

    if (labels.length === 0 || values.every((v) => v === 0)) return;

    const isTimeSeries = labels.some((l) => /^\d{4}-\d{2}$/.test(l));
    const colors = values.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);

    chartRef.current?.destroy();

    chartRef.current = new Chart(canvas, {
      type: isTimeSeries ? 'line' : 'bar',
      data: {
        labels,
        datasets: [
          {
            label: valueKey,
            data: values,
            ...(isTimeSeries
              ? {
                  borderColor: EVRAZ_COLORS.gold,
                  backgroundColor: 'rgba(200, 168, 78, 0.08)',
                  borderWidth: 2,
                  fill: true,
                  tension: 0.4,
                  pointBackgroundColor: EVRAZ_COLORS.gold,
                  pointBorderColor: '#001a33',
                  pointBorderWidth: 2,
                  pointRadius: 4,
                  pointHoverRadius: 6,
                }
              : {
                  backgroundColor: colors.map((c) => c + '33'),
                  borderColor: colors,
                  borderWidth: 2,
                  borderRadius: 6,
                  hoverBackgroundColor: colors.map((c) => c + '66'),
                }),
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 800, easing: 'easeOutQuart' },
        plugins: {
          legend: { labels: { color: '#e8eaf0', font: { family: 'Inter' } } },
          tooltip: {
            backgroundColor: 'rgba(0, 26, 51, 0.9)',
            titleColor: '#e8eaf0',
            bodyColor: '#8a8d8f',
            borderColor: 'rgba(200, 168, 78, 0.2)',
            borderWidth: 1,
            padding: 12,
            cornerRadius: 8,
          },
        },
        scales: {
          x: { ticks: { color: '#8a8d8f', font: { family: 'Inter' } }, grid: { color: 'rgba(200,168,78,0.03)' } },
          y: { ticks: { color: '#8a8d8f', font: { family: 'Inter' } }, grid: { color: 'rgba(200,168,78,0.03)' }, beginAtZero: true },
        },
      },
    });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [data]);

  if (!data || data.length === 0) return null;

  return (
    <div className="chat-message__chart" style={{ height: 280 }}>
      <canvas ref={canvasRef} />
    </div>
  );
}