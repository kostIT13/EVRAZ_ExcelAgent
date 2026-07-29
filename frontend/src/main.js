/**
 * EVRAZ AI Agent — Modern Frontend Application
 * Корпоративный дизайн ЕВРАЗ с дашбордом, чатом, файлами и трассировкой.
 */

/* global console */

import api from './api.js';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

// ============================================================
// Цветовая палитра ЕВРАЗ для графиков
// ============================================================
const EVRAZ_COLORS = {
  red: '#E31837',
  gold: '#C8A84E',
  navy: '#003057',
  navyLight: '#004a7a',
  steel: '#4A4E54',
  silver: '#8A8D8F',
  white: '#F5F5F5',
};

const CHART_COLORS = [
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

// ============================================================
// Состояние приложения
// ============================================================
const state = {
  files: [],
  selectedFileId: null,
  currentQuestion: '',
  messages: [],
  isAsking: false,
  charts: [],
  currentPage: 'dashboard',
};

// ============================================================
// DOM references
// ============================================================
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
  // Health
  healthStatus: $('#healthStatus'),

  // Navigation
  navItems: $$('.nav__item'),
  pages: {
    dashboard: $('#pageDashboard'),
    chat: $('#pageChat'),
    files: $('#pageFiles'),
    trace: $('#pageTrace'),
  },

  // Dashboard
  statFiles: $('#statFiles'),
  statSheets: $('#statSheets'),
  statMonths: $('#statMonths'),
  statQueries: $('#statQueries'),
  dashboardPriceChart: $('#dashboardPriceChart'),
  dashboardSourceChart: $('#dashboardSourceChart'),
  dashboardTopItemsChart: $('#dashboardTopItemsChart'),
  recentActivity: $('#recentActivity'),

  // Chat page - Files
  fileList: $('#fileList'),
  fileInput: $('#fileInput'),
  dropzone: $('#dropzone'),
  uploadForm: $('#uploadForm'),
  uploadBtn: $('#uploadBtn'),
  refreshFilesBtn: $('#refreshFilesBtn'),

  // Chat page - Chat
  chatMessages: $('#chatMessages'),
  chatForm: $('#chatForm'),
  questionInput: $('#questionInput'),
  askBtn: $('#askBtn'),
  modeSelect: $('#modeSelect'),
  topKInput: $('#topKInput'),

  // Chat page - Tabs
  tabs: $$('.tab'),
  tabChat: $('#tabChat'),
  tabDetails: $('#tabDetails'),
  tabTrace: $('#tabTrace'),

  // Chat page - Details
  detailsPlaceholder: $('#detailsPlaceholder'),
  detailsContent: $('#detailsContent'),
  detailsFileName: $('#detailsFileName'),
  detailsMeta: $('#detailsMeta'),
  detailsSheets: $('#detailsSheets'),

  // Chat page - Trace
  traceInput: $('#traceInput'),
  traceBtn: $('#traceBtn'),
  traceRefreshBtn: $('#traceRefreshBtn'),
  traceResult: $('#traceResult'),
  tracePlaceholder: $('#tracePlaceholder'),
  traceHistory: $('#traceHistory'),
  traceHistoryList: $('#traceHistoryList'),

  // Files page
  filesFileList: $('#filesFileList'),
  filesFileInput: $('#filesFileInput'),
  filesDropzone: $('#filesDropzone'),
  filesUploadForm: $('#filesUploadForm'),
  filesUploadBtn: $('#filesUploadBtn'),
  filesRefreshBtn: $('#filesRefreshBtn'),
  filesDetailTitle: $('#filesDetailTitle'),
  filesDetailContent: $('#filesDetailContent'),

  // Trace page
  pageTraceInput: $('#pageTraceInput'),
  pageTraceBtn: $('#pageTraceBtn'),
  pageTraceRefreshBtn: $('#pageTraceRefreshBtn'),
  pageTraceHistoryList: $('#pageTraceHistoryList'),
  pageTraceResult: $('#pageTraceResult'),

  // Modal
  modalOverlay: $('#modalOverlay'),
  modalTitle: $('#modalTitle'),
  modalBody: $('#modalBody'),
  modalClose: $('#modalClose'),

  // Toast
  toastContainer: $('#toastContainer'),
};

// ============================================================
// Утилиты
// ============================================================
function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleString('ru-RU');
}

function formatMs(ms) {
  if (ms < 1000) return `${ms} мс`;
  return `${(ms / 1000).toFixed(2)} с`;
}

function confidenceLabel(score) {
  if (score >= 0.7) return { text: 'Высокая', cls: 'high' };
  if (score >= 0.4) return { text: 'Средняя', cls: 'medium' };
  return { text: 'Низкая', cls: 'low' };
}

function modeLabel(mode) {
  const labels = {
    rag: { text: 'RAG', cls: 'rag' },
    agent: { text: 'Agent', cls: 'agent' },
    rag_fallback: { text: 'RAG (fallback)', cls: 'rag_fallback' },
  };
  return labels[mode] || { text: mode, cls: '' };
}

function scrollToBottom(el) {
  requestAnimationFrame(() => {
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  });
}

/**
 * Плавный скролл страницы к указанному элементу
 * @param {HTMLElement|string} target - элемент или CSS-селектор
 * @param {Object} options - { offset, behavior, block }
 */
function scrollToElement(target, options = {}) {
  const el = typeof target === 'string' ? document.querySelector(target) : target;
  if (!el) return;

  const {
    offset = 0,
    behavior = 'smooth',
    block = 'start',
  } = options;

  const top = el.getBoundingClientRect().top + window.scrollY - offset;
  window.scrollTo({ top, behavior });

  // Для контейнеров с overflow: auto
  const scrollableParent = el.closest('.scrollable, .chat-messages, .file-list, .dashboard, .trace-result, .details-content');
  if (scrollableParent) {
    const parentTop = el.getBoundingClientRect().top - scrollableParent.getBoundingClientRect().top + scrollableParent.scrollTop - offset;
    scrollableParent.scrollTo({ top: parentTop, behavior });
  }
}

/**
 * Плавный скролл в конец прокручиваемого контейнера
 * @param {HTMLElement} el - контейнер
 */
function scrollToBottomSmooth(el) {
  if (!el) return;
  el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function shortId(id) {
  return id ? id.slice(0, 8) : '?';
}

// ============================================================
// Toast уведомления
// ============================================================
function showToast(message, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast toast--${type}`;
  el.textContent = message;
  dom.toastContainer.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateX(120%) scale(0.9)';
    el.style.transition = '0.3s ease';
    setTimeout(() => el.remove(), 300);
  }, 3500);
}

// ============================================================
// Модальное окно
// ============================================================
function showModal(title, bodyHtml) {
  dom.modalTitle.textContent = title;
  dom.modalBody.innerHTML = bodyHtml;
  dom.modalOverlay.hidden = false;
}

function hideModal() {
  dom.modalOverlay.hidden = true;
}

dom.modalClose.addEventListener('click', hideModal);
dom.modalOverlay.addEventListener('click', (e) => {
  if (e.target === dom.modalOverlay) hideModal();
});

// ============================================================
// Chart.js — Визуализация данных
// ============================================================
function destroyCharts() {
  state.charts.forEach(c => c.destroy());
  state.charts = [];
}

function createBarChart(canvasId, data, label = 'Значение') {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;

  const labels = data.map(d => d.label);
  const values = data.map(d => d.value);
  const colors = data.map((d, i) => d.color || CHART_COLORS[i % CHART_COLORS.length]);

  const chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label,
        data: values,
        backgroundColor: colors.map(c => c + '33'),
        borderColor: colors,
        borderWidth: 2,
        borderRadius: 6,
        hoverBackgroundColor: colors.map(c => c + '66'),
      }],
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

  state.charts.push(chart);
  return chart;
}

function createLineChart(canvasId, data, label = 'Динамика') {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;

  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(d => d.label),
      datasets: [{
        label,
        data: data.map(d => d.value),
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
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 1000, easing: 'easeOutQuart' },
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

  state.charts.push(chart);
  return chart;
}

function createDoughnutChart(canvasId, data) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;

  const colors = data.map((d, i) => d.color || CHART_COLORS[i % CHART_COLORS.length]);

  const chart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: data.map(d => d.label),
      datasets: [{
        data: data.map(d => d.value),
        backgroundColor: colors,
        borderColor: '#0a1420',
        borderWidth: 2,
        hoverOffset: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 800, easing: 'easeOutQuart' },
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#e8eaf0', font: { family: 'Inter', size: 11 }, padding: 12 },
        },
        tooltip: {
          backgroundColor: 'rgba(0, 26, 51, 0.9)',
          titleColor: '#e8eaf0',
          bodyColor: '#8a8d8f',
          borderColor: 'rgba(200, 168, 78, 0.2)',
          borderWidth: 1,
          padding: 12,
          cornerRadius: 8,
          callbacks: {
            label: (ctx) => {
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct = ((ctx.parsed / total) * 100).toFixed(1);
              return ` ${ctx.label}: ${pct}%`;
            },
          },
        },
      },
    },
  });

  state.charts.push(chart);
  return chart;
}

// ============================================================
// Навигация по страницам
// ============================================================
function navigateTo(page) {
  if (state.currentPage === page) return;
  state.currentPage = page;

  // Обновляем nav
  dom.navItems.forEach(item => {
    item.classList.toggle('nav__item--active', item.dataset.page === page);
  });

  // Показываем нужную страницу
  Object.entries(dom.pages).forEach(([key, el]) => {
    el.classList.toggle('page--active', key === page);
  });

  // Плавный скролл страницы вверх при переключении
  const mainEl = document.querySelector('.main');
  if (mainEl) {
    mainEl.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // Загружаем данные для дашборда при переходе
  if (page === 'dashboard') {
    loadDashboard();
  }
}

// Обработчики навигации
dom.navItems.forEach(item => {
  item.addEventListener('click', () => navigateTo(item.dataset.page));
});

// ============================================================
// ДАШБОРД
// ============================================================
async function loadDashboard() {
  try {
    // Статистика
    const [filesData, traces] = await Promise.all([
      api.listFiles({ limit: 100 }).catch(() => ({ files: [] })),
      api.listTraces({ limit: 5 }).catch(() => []),
    ]);

    const files = filesData.files || [];
    let totalSheets = 0;
    let totalMonths = 0;

    for (const f of files) {
      totalSheets += f.total_sheets || f.sheet_count || 0;
    }

    // Получаем количество месяцев через API
    try {
      const monthsResult = await api.askQuestion({
        question: 'О скольки месяцах у тебя есть информация?',
        mode: 'agent',
        top_k: 5,
        conversation_history: [],
      });
      if (monthsResult && monthsResult.sql_result_preview && monthsResult.sql_result_preview.length > 0) {
        totalMonths = monthsResult.sql_result_preview[0].количество_месяцев || 0;
      }
    } catch (e) {
      // fallback — months остаётся 0
    }

    dom.statFiles.textContent = files.length || '—';
    dom.statSheets.textContent = totalSheets || '—';
    dom.statMonths.textContent = totalMonths || '—';
    dom.statQueries.textContent = Array.isArray(traces) ? traces.length : '—';

    // Загружаем данные для графиков
    loadDashboardCharts();

    // Последние запросы
    renderRecentActivity(traces);

  } catch (err) {
    console.error('Dashboard load error:', err);
  }
}

async function loadDashboardCharts() {
  destroyCharts();

  // График 1: Динамика цен по месяцам
  try {
    const priceData = await api.askQuestion({
      question: 'Покажи среднюю цену по всем месяцам',
      mode: 'agent',
      top_k: 10,
      conversation_history: [],
    });

    if (priceData.sql_result_preview && priceData.sql_result_preview.length > 0) {
      const months = priceData.sql_result_preview.map(r => r.period || r.label || '');
      const prices = priceData.sql_result_preview.map(r => {
        const val = r.avg_price || r.average_price || r.price_value || r.value || 0;
        return parseFloat(val) || 0;
      });

      if (months.length > 0) {
        createLineChart('dashboardPriceChart',
          months.map((m, i) => ({ label: m, value: prices[i] })),
          'Средняя цена (руб/тн)'
        );
      }
    }
  } catch (e) {
    // Если данных нет, показываем заглушку
    createLineChart('dashboardPriceChart', [
      { label: 'Янв', value: 0 },
      { label: 'Фев', value: 0 },
      { label: 'Мар', value: 0 },
    ], 'Средняя цена (руб/тн)');
  }

  // График 2: Распределение по источникам цен
  try {
    const sourceData = await api.askQuestion({
      question: 'Покажи количество записей по каждому источнику цен',
      mode: 'agent',
      top_k: 10,
      conversation_history: [],
    });

    if (sourceData.sql_result_preview && sourceData.sql_result_preview.length > 0) {
      const sources = sourceData.sql_result_preview.map(r => r.price_source || r.source || r.label || '');
      const counts = sourceData.sql_result_preview.map(r => {
        const val = r.count || r.cnt || r.quantity || r.value || 0;
        return parseInt(val) || 0;
      });

      if (sources.length > 0) {
        createDoughnutChart('dashboardSourceChart',
          sources.map((s, i) => ({ label: s, value: counts[i], color: CHART_COLORS[i % CHART_COLORS.length] }))
        );
      }
    }
  } catch (e) {
    createDoughnutChart('dashboardSourceChart', [
      { label: 'Нет данных', value: 1, color: EVRAZ_COLORS.steel },
    ]);
  }

  // График 3: Топ-10 материалов по средней цене
  try {
    const topData = await api.askQuestion({
      question: 'Покажи топ 10 материалов по средней цене',
      mode: 'agent',
      top_k: 10,
      conversation_history: [],
    });

    if (topData.sql_result_preview && topData.sql_result_preview.length > 0) {
      const items = topData.sql_result_preview.map(r => {
        const name = r.item_name_normalized || r.item_name || r.material || r.label || '';
        // сокращаем длинные названия
        return name.length > 25 ? name.slice(0, 22) + '...' : name;
      });
      const values = topData.sql_result_preview.map(r => {
        const val = r.avg_price || r.average_price || r.price_value || r.value || 0;
        return parseFloat(val) || 0;
      });

      if (items.length > 0) {
        createBarChart('dashboardTopItemsChart',
          items.map((item, i) => ({ label: item, value: values[i] })),
          'Средняя цена (руб/тн)'
        );
      }
    }
  } catch (e) {
    createBarChart('dashboardTopItemsChart', [
      { label: 'Нет данных', value: 0 },
    ], 'Средняя цена (руб/тн)');
  }
}

function renderRecentActivity(traces) {
  if (!Array.isArray(traces) || traces.length === 0) {
    dom.recentActivity.innerHTML = `
      <div class="empty-state" style="padding:24px;">
        <div class="empty-state__text">Нет активности</div>
      </div>`;
    return;
  }

  dom.recentActivity.innerHTML = traces.map(t => {
    const status = t.status === 'success' ? 'success' : 'error';
    const icon = t.status === 'success' ? '✅' : '❌';
    const question = (t.question || t.request_id || '').slice(0, 50);
    return `
      <div class="activity-item" style="cursor:pointer;" data-request-id="${t.request_id || ''}">
        <div class="activity-item__icon activity-item__icon--${status}">${icon}</div>
        <span class="activity-item__text">${escapeHtml(question)}</span>
        <span class="activity-item__time">${t.created_at ? formatDate(t.created_at) : ''}</span>
      </div>`;
  }).join('');

  // Клик по активности открывает трассировку
  dom.recentActivity.querySelectorAll('.activity-item').forEach(el => {
    el.addEventListener('click', () => {
      const rid = el.dataset.requestId;
      if (rid) {
        navigateTo('trace');
        setTimeout(() => loadTraceDetail(rid), 100);
      }
    });
  });
}

// ============================================================
// ЧАТ
// ============================================================
function addMessage(type, content, meta = {}) {
  const msgEl = document.createElement('div');
  msgEl.className = `chat-message chat-message--${type}`;
  msgEl.dataset.requestId = meta.requestId || '';

  let header = '';
  if (type === 'user') {
    header = `<div class="chat-message__header">Вы</div>`;
  } else if (type === 'assistant') {
    header = `<div class="chat-message__header">🤖 Ассистент</div>`;
  }

  // Мета-информация
  let metaHtml = '';
  if (meta.mode) {
    const ml = modeLabel(meta.mode);
    metaHtml += `<span class="chat-message__badge chat-message__badge--${ml.cls}">${ml.text}</span>`;
  }
  if (meta.confidence !== undefined) {
    const cl = confidenceLabel(meta.confidence);
    metaHtml += `<span class="chat-message__badge chat-message__badge--${cl.cls}">Уверенность: ${cl.text} (${(meta.confidence * 100).toFixed(0)}%)</span>`;
  }
  if (meta.latency) {
    metaHtml += `<span class="chat-message__badge">⏱ ${formatMs(meta.latency)}</span>`;
  }
  if (meta.selfCorrected) {
    metaHtml += `<span class="chat-message__badge" style="border-color:var(--color-warning);color:var(--color-warning);">🔄 Self-Correction</span>`;
  }
  if (meta.requestId) {
    metaHtml += `
      <span class="chat-message__badge" style="font-family:var(--font-mono);font-size:0.68rem;cursor:pointer;"
            title="Нажмите чтобы скопировать request_id"
            onclick="navigator.clipboard.writeText('${meta.requestId}');showToast('Request ID скопирован','success')">
        🆔 ${shortId(meta.requestId)}
      </span>
      <button class="chat-message__sources-btn" data-request-id="${meta.requestId}">🔍 Trace</button>
    `;
  }
  if (meta.sources && meta.sources.length > 0) {
    metaHtml += `<button class="chat-message__sources-btn" data-sources='${JSON.stringify(meta.sources)}'>📚 Источники (${meta.sources.length})</button>`;
  }

  // SQL блок
  let sqlHtml = '';
  if (meta.sqlQuery) {
    sqlHtml = `
      <div class="chat-message__sql">
        <div class="chat-message__sql-label">SQL запрос</div>
        <code>${escapeHtml(meta.sqlQuery)}</code>
      </div>`;
  }

  // График
  let chartHtml = '';
  const chartId = `chart-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  if (meta.sqlResultPreview && meta.sqlResultPreview.length > 0) {
    chartHtml = `<div class="chat-message__chart" id="${chartId}"><div class="chart-container" style="height:280px;"><canvas id="${chartId}-canvas"></canvas></div></div>`;
  }

  msgEl.innerHTML = `
    ${header}
    <div class="chat-message__content">${escapeHtml(content)}</div>
    ${sqlHtml}
    ${chartHtml}
    ${metaHtml ? `<div class="chat-message__meta">${metaHtml}</div>` : ''}
  `;

  dom.chatMessages.appendChild(msgEl);
  scrollToBottom(dom.chatMessages);

  // Рендерим график если есть данные
  if (meta.sqlResultPreview && meta.sqlResultPreview.length > 0) {
    setTimeout(() => renderChatChart(chartId, meta), 100);
  }

  // Обработчики кнопок
  msgEl.querySelectorAll('[data-request-id]').forEach(btn => {
    btn.addEventListener('click', () => {
      const rid = btn.dataset.requestId;
      if (rid) {
        navigateTo('trace');
        setTimeout(() => loadTraceDetail(rid), 100);
      }
    });
  });
  msgEl.querySelectorAll('[data-sources]').forEach(btn => {
    btn.addEventListener('click', () => {
      const sources = JSON.parse(btn.dataset.sources);
      showSourcesModal(sources);
    });
  });
}

function renderChatChart(containerId, meta) {
  const canvas = document.getElementById(`${containerId}-canvas`);
  if (!canvas) return;

  const preview = meta.sqlResultPreview || [];
  const keys = Object.keys(preview[0] || {});
  if (keys.length < 2) return;

  const labelKey = keys[0];
  const valueKey = keys[1];

  const labels = preview.map(r => String(r[labelKey] || ''));
  const values = preview.map(r => parseFloat(r[valueKey]) || 0);

  // Определяем тип графика
  const isTimeSeries = labels.some(l => /^\d{4}-\d{2}$/.test(l));

  if (isTimeSeries) {
    createLineChart(`${containerId}-canvas`,
      labels.map((l, i) => ({ label: l, value: values[i] })),
      valueKey
    );
  } else {
    createBarChart(`${containerId}-canvas`,
      labels.map((l, i) => ({ label: l, value: values[i] })),
      valueKey
    );
  }
}

function showTypingIndicator() {
  const el = document.createElement('div');
  el.className = 'chat-message chat-message--assistant';
  el.id = 'typingIndicator';
  el.innerHTML = `
    <div class="chat-message__header">🤖 Ассистент</div>
    <div class="chat-message__content typing-indicator">
      <span class="typing-indicator__dot"></span>
      <span class="typing-indicator__dot"></span>
      <span class="typing-indicator__dot"></span>
    </div>
  `;
  dom.chatMessages.appendChild(el);
  scrollToBottom(dom.chatMessages);
}

function removeTypingIndicator() {
  const el = document.getElementById('typingIndicator');
  if (el) el.remove();
}

function showAgentProgress() {
  removeAgentProgress();
  const steps = [
    { icon: '🔍', label: 'Анализ вопроса', desc: 'Определяю тип запроса...' },
    { icon: '📝', label: 'Генерация SQL', desc: 'Формирую SQL-запрос...' },
    { icon: '⚡', label: 'Выполнение', desc: 'Выполняю запрос к БД...' },
    { icon: '🧠', label: 'Формирование ответа', desc: 'Анализирую результат...' },
  ];

  const el = document.createElement('div');
  el.className = 'chat-message chat-message--assistant';
  el.id = 'agentProgress';

  el.innerHTML = `
    <div class="chat-message__header">🤖 Ассистент</div>
    <div class="agent-progress" id="agentProgressInner">
      ${steps.map((step, i) => `
        <div class="agent-progress__step" data-step="${i}" data-index="${i}">
          <div class="agent-progress__indicator">
            <span class="agent-progress__icon">${step.icon}</span>
            <div class="agent-progress__line"></div>
          </div>
          <div class="agent-progress__info">
            <div class="agent-progress__label">${step.label}</div>
            <div class="agent-progress__desc">${step.desc}</div>
          </div>
        </div>
      `).join('')}
    </div>
  `;

  dom.chatMessages.appendChild(el);
  scrollToBottom(dom.chatMessages);
}

function activateAgentStep(index) {
  const container = document.getElementById('agentProgressInner');
  if (!container) return;

  const steps = container.querySelectorAll('.agent-progress__step');
  steps.forEach((step, i) => {
    step.classList.remove('agent-progress__step--active', 'agent-progress__step--done');
    if (i < index) {
      step.classList.add('agent-progress__step--done');
    } else if (i === index) {
      step.classList.add('agent-progress__step--active');
    }
  });

  const activeStep = container.querySelector('.agent-progress__step--active');
  if (activeStep) {
    scrollToBottom(dom.chatMessages);
  }
}

function completeAgentProgress() {
  const container = document.getElementById('agentProgressInner');
  if (!container) return;

  const steps = container.querySelectorAll('.agent-progress__step');
  steps.forEach((step) => {
    step.classList.remove('agent-progress__step--active');
    step.classList.add('agent-progress__step--done');
  });
}

function removeAgentProgress() {
  const el = document.getElementById('agentProgress');
  if (el) {
    el.remove();
  }
}

async function handleAskQuestion(question) {
  if (!question.trim() || state.isAsking) return;

  state.isAsking = true;
  dom.askBtn.disabled = true;
  dom.questionInput.disabled = true;

  // Добавляем сообщение пользователя
  addMessage('user', question);
  dom.questionInput.value = '';

  const mode = dom.modeSelect.value;
  const topK = parseInt(dom.topKInput.value) || 10;

  // Показываем прогресс для agent режима
  if (mode === 'agent' || mode === 'auto') {
    showAgentProgress();
  } else {
    showTypingIndicator();
  }

  try {
    const result = await api.askQuestion({
      question,
      top_k: topK,
      mode,
      conversation_history: [],
    });

    // Убираем индикаторы
    removeTypingIndicator();
    removeAgentProgress();

    const answer = result.answer || 'Не удалось получить ответ';
    const meta = {
      mode: result.mode_used || mode,
      confidence: result.confidence,
      latency: result.latency_ms,
      requestId: result.request_id,
      sources: result.sources,
      sqlQuery: result.sql_query,
      sqlResultPreview: result.sql_result_preview,
      selfCorrected: result.self_corrected,
    };

    addMessage('assistant', answer, meta);

  } catch (err) {
    removeTypingIndicator();
    removeAgentProgress();
    addMessage('error', `❌ Ошибка: ${err.message || 'Неизвестная ошибка'}`);
  } finally {
    state.isAsking = false;
    dom.askBtn.disabled = true;
    dom.questionInput.disabled = false;
    dom.questionInput.focus();
  }
}

function showSourcesModal(sources) {
  if (!sources || sources.length === 0) {
    showToast('Нет источников для отображения', 'info');
    return;
  }

  const html = `
    <div class="sources-list">
      ${sources.map((s, i) => `
        <div class="source-item">
          <div class="source-item__header">
            <span class="source-item__rank">#${s.rank || i + 1}</span>
            <span class="source-item__score">Score: ${(s.score * 100).toFixed(1)}%</span>
            <span class="source-item__type">${s.source_type || ''}</span>
          </div>
          <div class="source-item__text">${escapeHtml(s.chunk || '')}</div>
        </div>
      `).join('')}
    </div>
  `;

  showModal('📚 Источники', html);
}

// ============================================================
// ФАЙЛЫ
// ============================================================
async function loadFiles(listEl = dom.fileList, selectCallback = null) {
  try {
    const data = await api.listFiles({ limit: 100 });
    state.files = data.files || [];

    if (state.files.length === 0) {
      listEl.innerHTML = `<div class="file-list__empty">Файлы не загружены</div>`;
      return;
    }

    listEl.innerHTML = state.files.map(f => {
      const isActive = f.id === state.selectedFileId;
      const statusClass = `file-item__status--${f.status || 'uploaded'}`;
      const statusText = f.status === 'processed' ? '✅' : f.status === 'error' ? '❌' : '⏳';
      return `
        <div class="file-item ${isActive ? 'file-item--active' : ''}" data-file-id="${f.id}">
          <span class="file-item__icon">📄</span>
          <div class="file-item__info">
            <div class="file-item__name">${escapeHtml(f.filename || 'unknown')}</div>
            <div class="file-item__meta">${f.sheet_count || 0} листов • ${formatDate(f.uploaded_at)}</div>
          </div>
          <span class="file-item__status ${statusClass}">${statusText}</span>
          <button class="file-item__delete" data-file-id="${f.id}" title="Удалить">✕</button>
        </div>`;
    }).join('');

    // Обработчики клика
    listEl.querySelectorAll('.file-item').forEach(item => {
      item.addEventListener('click', (e) => {
        if (e.target.closest('.file-item__delete')) return;
        const fid = parseInt(item.dataset.fileId);
        state.selectedFileId = fid;
        loadFiles(listEl, selectCallback);
        if (selectCallback) selectCallback(fid);
        loadFileDetails(fid);
      });
    });

    // Обработчики удаления
    listEl.querySelectorAll('.file-item__delete').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const fid = parseInt(btn.dataset.fileId);
        if (confirm('Удалить файл?')) {
          try {
            await api.deleteFile(fid);
            showToast('Файл удалён', 'success');
            loadFiles(listEl, selectCallback);
          } catch (err) {
            showToast(`Ошибка удаления: ${err.message}`, 'error');
          }
        }
      });
    });

  } catch (err) {
    listEl.innerHTML = `<div class="file-list__empty">Ошибка загрузки: ${err.message}</div>`;
  }
}

async function loadFileDetails(fileId) {
  try {
    const file = await api.getFile(fileId);
    dom.detailsFileName.textContent = `📄 ${file.filename || 'Файл'}`;

    const metaItems = [
      `📊 ${file.sheet_count || 0} листов`,
      `📅 ${formatDate(file.uploaded_at)}`,
      file.status === 'processed' ? '✅ Обработан' : file.status === 'error' ? '❌ Ошибка' : '⏳ Загружен',
    ];
    dom.detailsMeta.innerHTML = metaItems.map(m => `<span class="details-meta__item">${m}</span>`).join('');

    if (file.sheets && file.sheets.length > 0) {
      dom.detailsSheets.innerHTML = file.sheets.map(sheet => `
        <div class="details-sheet">
          <div class="details-sheet__header">
            <span class="details-sheet__name">📋 ${escapeHtml(sheet.original_name || sheet.normalized_name || 'Лист')}</span>
            <span class="details-sheet__meta">${sheet.row_count || 0} строк × ${sheet.col_count || 0} колонок</span>
          </div>
          <div class="details-sheet__body">
            <div class="details-columns">
              ${(sheet.columns || []).map(col => `
                <div class="details-column">
                  <span class="details-column__name">${escapeHtml(col.original_name || col.normalized_name || '')}</span>
                  <span class="details-column__type">${col.data_type || ''}</span>
                </div>
              `).join('')}
            </div>
            ${sheet.period ? `<div style="margin-top:8px;font-size:0.78rem;color:var(--evraz-gold);">📅 Период: ${sheet.period}</div>` : ''}
          </div>
        </div>
      `).join('');
    } else {
      dom.detailsSheets.innerHTML = '<div style="padding:16px;color:var(--color-text-muted);">Нет информации о листах</div>';
    }

    dom.detailsPlaceholder.hidden = true;
    dom.detailsContent.hidden = false;

    // Обновляем детальную страницу файлов
    renderFilesDetailPage(file);

  } catch (err) {
    showToast(`Ошибка загрузки деталей: ${err.message}`, 'error');
  }
}

function renderFilesDetailPage(file) {
  const content = dom.filesDetailContent;
  if (!file) {
    content.innerHTML = `
      <div class="empty-state">
        <div class="empty-state__icon">📊</div>
        <div class="empty-state__text">Выберите файл для просмотра детальной информации</div>
      </div>`;
    return;
  }

  dom.filesDetailTitle.textContent = `📋 ${file.filename || 'Файл'}`;

  let sheetsHtml = '';
  if (file.sheets && file.sheets.length > 0) {
    sheetsHtml = file.sheets.map(sheet => `
      <div class="details-sheet">
        <div class="details-sheet__header">
          <span class="details-sheet__name">📋 ${escapeHtml(sheet.original_name || sheet.normalized_name || 'Лист')}</span>
          <span class="details-sheet__meta">${sheet.row_count || 0} строк × ${sheet.col_count || 0} колонок</span>
        </div>
        <div class="details-sheet__body">
          <div class="details-columns">
            ${(sheet.columns || []).map(col => `
              <div class="details-column">
                <span class="details-column__name">${escapeHtml(col.original_name || col.normalized_name || '')}</span>
                <span class="details-column__type">${col.data_type || ''}</span>
              </div>
            `).join('')}
          </div>
          ${sheet.period ? `<div style="margin-top:8px;font-size:0.78rem;color:var(--evraz-gold);">📅 Период: ${sheet.period}</div>` : ''}
        </div>
      </div>
    `).join('');
  }

  content.innerHTML = `
    <div style="padding:16px 18px;overflow-y:auto;height:100%;">
      <div class="details-header">
        <h3 style="color:var(--evraz-gold);">📄 ${escapeHtml(file.filename || 'Файл')}</h3>
        <div class="details-meta">
          <span class="details-meta__item">📊 ${file.sheet_count || 0} листов</span>
          <span class="details-meta__item">📅 ${formatDate(file.uploaded_at)}</span>
          <span class="details-meta__item">${file.status === 'processed' ? '✅ Обработан' : file.status === 'error' ? '❌ Ошибка' : '⏳ Загружен'}</span>
        </div>
      </div>
      <div style="margin-top:16px;">
        <h4 style="font-size:0.85rem;margin-bottom:12px;color:var(--evraz-gold);">📑 Листы</h4>
        ${sheetsHtml || '<div style="color:var(--color-text-muted);">Нет данных о листах</div>'}
      </div>
    </div>
  `;
}

// ============================================================
// ТРАССИРОВКА
// ============================================================
async function loadTraceHistory(listEl = dom.traceHistoryList, clickCallback = null) {
  try {
    const traces = await api.listTraces({ limit: 20 });

    if (!Array.isArray(traces) || traces.length === 0) {
      listEl.innerHTML = `<div class="trace-history__empty">История пуста</div>`;
      return;
    }

    listEl.innerHTML = traces.map(t => {
      const statusClass = t.status === 'success' ? 'success' : t.status === 'low_confidence' ? 'low_confidence' : 'failed';
      return `
        <div class="trace-history__item" data-request-id="${t.request_id || ''}">
          <span class="trace-history__question">${escapeHtml((t.question || t.request_id || '').slice(0, 60))}</span>
          <span class="trace-history__status trace-history__status--${statusClass}">${t.status || '?'}</span>
          <span class="trace-history__time">${t.created_at ? formatDate(t.created_at) : ''}</span>
        </div>`;
    }).join('');

    listEl.querySelectorAll('.trace-history__item').forEach(item => {
      item.addEventListener('click', () => {
        const rid = item.dataset.requestId;
        if (rid) {
          if (clickCallback) clickCallback(rid);
          loadTraceDetail(rid);
        }
      });
    });

  } catch (err) {
    listEl.innerHTML = `<div class="trace-history__empty">Ошибка загрузки: ${err.message}</div>`;
  }
}

async function loadTraceDetail(requestId, resultEl = dom.traceResult, placeholderEl = dom.tracePlaceholder) {
  if (!requestId) return;

  try {
    const trace = await api.getTrace(requestId);

    if (placeholderEl) placeholderEl.hidden = true;
    if (resultEl) resultEl.hidden = false;

    if (!trace || trace.error) {
      if (resultEl) {
        resultEl.innerHTML = `<div class="empty-state"><div class="empty-state__icon">🔍</div><div class="empty-state__text">Трассировка не найдена</div></div>`;
      }
      return;
    }

    const steps = trace.steps || [];
    const html = `
      <div style="margin-bottom:16px;">
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
          <span class="details-meta__item">🆔 ${trace.request_id || requestId}</span>
          <span class="details-meta__item">❓ ${escapeHtml(trace.question || '')}</span>
          <span class="details-meta__item">📅 ${trace.created_at ? formatDate(trace.created_at) : ''}</span>
          <span class="details-meta__item">⏱ ${trace.latency_ms ? formatMs(trace.latency_ms) : ''}</span>
        </div>
        <div style="font-size:0.82rem;color:var(--color-text-muted);margin-bottom:12px;">
          Статус: <strong style="color:${trace.status === 'success' ? 'var(--color-success)' : 'var(--color-error)'}">${trace.status || '?'}</strong>
          ${trace.mode_used ? `• Режим: <strong style="color:var(--evraz-gold)">${trace.mode_used}</strong>` : ''}
          ${trace.confidence ? `• Уверенность: <strong>${(trace.confidence * 100).toFixed(0)}%</strong>` : ''}
        </div>
        ${trace.answer ? `<div style="padding:12px 16px;background:var(--color-surface-2);border:1px solid var(--glass-border);border-radius:var(--radius-sm);margin-bottom:12px;font-size:0.88rem;line-height:1.6;">${escapeHtml(trace.answer)}</div>` : ''}
      </div>
      ${steps.map((step, i) => `
        <div class="trace-step">
          <div class="trace-step__header">
            <span class="trace-step__icon">${step.icon || '●'}</span>
            <span>${escapeHtml(step.label || step.node || step.name || `Шаг ${i + 1}`)}</span>
            ${step.duration_ms ? `<span style="margin-left:auto;font-size:0.72rem;color:var(--color-text-muted);">${formatMs(step.duration_ms)}</span>` : ''}
          </div>
          <div class="trace-step__body">${escapeHtml(step.output || step.result || JSON.stringify(step, null, 2))}</div>
        </div>
      `).join('')}
    `;

    if (resultEl) resultEl.innerHTML = html;

  } catch (err) {
    if (resultEl) {
      resultEl.innerHTML = `<div class="empty-state"><div class="empty-state__icon">❌</div><div class="empty-state__text">Ошибка: ${err.message}</div></div>`;
    }
  }
}

// ============================================================
// Загрузка файлов
// ============================================================
function setupFileUpload(inputEl, dropzoneEl, formEl, btnEl, listEl, callback) {
  let selectedFile = null;

  inputEl.addEventListener('change', () => {
    selectedFile = inputEl.files[0] || null;
    btnEl.disabled = !selectedFile;
    if (selectedFile) {
      dropzoneEl.querySelector('span:nth-child(2)').textContent = selectedFile.name;
    }
  });

  dropzoneEl.addEventListener('click', () => inputEl.click());

  dropzoneEl.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzoneEl.classList.add('upload-form__dropzone--dragover');
  });

  dropzoneEl.addEventListener('dragleave', () => {
    dropzoneEl.classList.remove('upload-form__dropzone--dragover');
  });

  dropzoneEl.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzoneEl.classList.remove('upload-form__dropzone--dragover');
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith('.xlsx') || file.name.endsWith('.xls'))) {
      selectedFile = file;
      inputEl.files = e.dataTransfer.files;
      btnEl.disabled = false;
      dropzoneEl.querySelector('span:nth-child(2)').textContent = file.name;
    }
  });

  formEl.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    btnEl.disabled = true;
    btnEl.textContent = '⏳ Загрузка...';

    try {
      await api.uploadFile(selectedFile);
      showToast('Файл загружен успешно', 'success');
      selectedFile = null;
      inputEl.value = '';
      dropzoneEl.querySelector('span:nth-child(2)').textContent = 'Выберите файл или перетащите сюда';
      btnEl.textContent = '⬆ Загрузить';
      btnEl.disabled = true;
      if (callback) callback();
      loadFiles(listEl);
    } catch (err) {
      showToast(`Ошибка загрузки: ${err.message}`, 'error');
      btnEl.textContent = '⬆ Загрузить';
      btnEl.disabled = false;
    }
  });
}

// ============================================================
// Health check
// ============================================================
async function checkHealth() {
  try {
    await api.checkHealth();
    dom.healthStatus.innerHTML = `
      <span class="status-dot status-dot--ok"></span>
      <span>Сервер работает</span>`;
  } catch {
    dom.healthStatus.innerHTML = `
      <span class="status-dot status-dot--error"></span>
      <span>Нет подключения</span>`;
  }
}

// ============================================================
// Инициализация
// ============================================================
async function init() {
  try {
    // Health check
    checkHealth();
    setInterval(checkHealth, 30000);

    // Навигация по вкладкам внутри чата
    dom.tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        dom.tabs.forEach(t => t.classList.remove('tab--active'));
        tab.classList.add('tab--active');

        const tabName = tab.dataset.tab;
        dom.tabChat.classList.toggle('tab-content--active', tabName === 'chat');
        dom.tabDetails.classList.toggle('tab-content--active', tabName === 'details');
        dom.tabTrace.classList.toggle('tab-content--active', tabName === 'trace');
      });
    });

    // Загрузка файлов (страница чата)
    loadFiles(dom.fileList, (fid) => loadFileDetails(fid)).catch(e => console.warn('Init: loadFiles(chat) failed', e));

    // Загрузка файлов (страница файлов)
    loadFiles(dom.filesFileList, (fid) => {
      api.getFile(fid).then(f => renderFilesDetailPage(f)).catch(() => {});
    }).catch(e => console.warn('Init: loadFiles(files) failed', e));

    // Загрузка истории трассировки (страница чата)
    loadTraceHistory(dom.traceHistoryList, (rid) => loadTraceDetail(rid)).catch(e => console.warn('Init: loadTraceHistory(chat) failed', e));

    // Загрузка истории трассировки (страница трассировки)
    loadTraceHistory(dom.pageTraceHistoryList, (rid) => loadTraceDetail(rid, dom.pageTraceResult, null)).catch(e => console.warn('Init: loadTraceHistory(trace) failed', e));

    // Upload формы
    setupFileUpload(dom.fileInput, dom.dropzone, dom.uploadForm, dom.uploadBtn, dom.fileList, () => {
      loadFiles(dom.filesFileList);
    });
    setupFileUpload(dom.filesFileInput, dom.filesDropzone, dom.filesUploadForm, dom.filesUploadBtn, dom.filesFileList, () => {
      loadFiles(dom.fileList);
    });

    // Обновление списка файлов
    dom.refreshFilesBtn.addEventListener('click', () => {
      loadFiles(dom.fileList);
      loadFiles(dom.filesFileList);
    });
    dom.filesRefreshBtn.addEventListener('click', () => {
      loadFiles(dom.filesFileList);
      loadFiles(dom.fileList);
    });

    // Чат
    dom.chatForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const question = dom.questionInput.value.trim();
      if (question) {
        handleAskQuestion(question);
      }
    });

    dom.questionInput.addEventListener('input', () => {
      dom.askBtn.disabled = !dom.questionInput.value.trim() || state.isAsking;
    });

    // Трассировка (страница чата)
    dom.traceBtn.addEventListener('click', () => {
      const rid = dom.traceInput.value.trim();
      if (rid) {
        dom.tracePlaceholder.hidden = true;
        dom.traceResult.hidden = false;
        loadTraceDetail(rid);
      }
    });

    dom.traceInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        dom.traceBtn.click();
      }
    });

    dom.traceRefreshBtn.addEventListener('click', () => {
      loadTraceHistory(dom.traceHistoryList);
    });

    // Трассировка (полная страница)
    dom.pageTraceBtn.addEventListener('click', () => {
      const rid = dom.pageTraceInput.value.trim();
      if (rid) {
        loadTraceDetail(rid, dom.pageTraceResult, null);
      }
    });

    dom.pageTraceInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        dom.pageTraceBtn.click();
      }
    });

    dom.pageTraceRefreshBtn.addEventListener('click', () => {
      loadTraceHistory(dom.pageTraceHistoryList);
    });

    // Загружаем дашборд
    loadDashboard();

    // Периодическое обновление дашборда
    setInterval(() => {
      if (state.currentPage === 'dashboard') {
        loadDashboard();
      }
    }, 60000);

    // Обновление трассировки
    setInterval(() => {
      if (state.currentPage === 'trace') {
        loadTraceHistory(dom.pageTraceHistoryList);
      }
      loadTraceHistory(dom.traceHistoryList);
    }, 15000);

    console.log('🚀 EVRAZ AI Agent initialized');
  } catch (err) {
    console.error('Init error:', err);
  }
}

// Запуск
document.addEventListener('DOMContentLoaded', init);