/**
 * EVRAZ AI Agent — Frontend Application
 * Главный модуль, управляющий состоянием и UI.
 */

import api from './api.js';

// ============================================================
// Состояние приложения
// ============================================================

const state = {
  files: [],
  selectedFileId: null,
  currentQuestion: '',
  messages: [],
  isAsking: false,
};

// ============================================================
// DOM references
// ============================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
  healthStatus: $('#healthStatus'),
  fileList: $('#fileList'),
  fileInput: $('#fileInput'),
  dropzone: $('#dropzone'),
  uploadForm: $('#uploadForm'),
  uploadBtn: $('#uploadBtn'),
  refreshFilesBtn: $('#refreshFilesBtn'),

  chatMessages: $('#chatMessages'),
  chatForm: $('#chatForm'),
  questionInput: $('#questionInput'),
  askBtn: $('#askBtn'),
  modeSelect: $('#modeSelect'),
  topKInput: $('#topKInput'),

  tabs: $$('.tab'),
  tabChat: $('#tabChat'),
  tabDetails: $('#tabDetails'),
  tabTrace: $('#tabTrace'),

  detailsPlaceholder: $('#detailsPlaceholder'),
  detailsContent: $('#detailsContent'),
  detailsFileName: $('#detailsFileName'),
  detailsMeta: $('#detailsMeta'),
  detailsSheets: $('#detailsSheets'),

  traceInput: $('#traceInput'),
  traceBtn: $('#traceBtn'),
  traceRefreshBtn: $('#traceRefreshBtn'),
  traceResult: $('#traceResult'),
  tracePlaceholder: $('#tracePlaceholder'),
  traceHistory: $('#traceHistory'),
  traceHistoryList: $('#traceHistoryList'),

  modalOverlay: $('#modalOverlay'),
  modalTitle: $('#modalTitle'),
  modalBody: $('#modalBody'),
  modalClose: $('#modalClose'),

  toastContainer: $('#toastContainer'),
};

// ============================================================
// Утилиты
// ============================================================

function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleString('ru-RU');
}

function formatBytes(bytes) {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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
    el.scrollTop = el.scrollHeight;
  });
}

function getConfidenceColor(score) {
  if (score >= 0.7) return 'var(--color-success)';
  if (score >= 0.4) return 'var(--color-warning)';
  return 'var(--color-error)';
}

// ============================================================
// Toast уведомления
// ============================================================

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  dom.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ============================================================
// Health Check
// ============================================================

async function checkHealth() {
  try {
    await api.checkHealth();
    dom.healthStatus.innerHTML = `
      <span class="status-dot status-dot--ok"></span>
      <span>Сервер работает</span>
    `;
  } catch (err) {
    dom.healthStatus.innerHTML = `
      <span class="status-dot status-dot--error"></span>
      <span>Сервер недоступен</span>
    `;
  }
}

// ============================================================
// Файлы
// ============================================================

async function loadFiles() {
  try {
    const data = await api.listFiles({ limit: 100 });
    state.files = data.files || [];
    renderFileList();
  } catch (err) {
    showToast(`Ошибка загрузки файлов: ${err.message}`, 'error');
  }
}

function renderFileList() {
  if (state.files.length === 0) {
    dom.fileList.innerHTML = `<div class="file-list__empty">Файлы не загружены</div>`;
    return;
  }

  dom.fileList.innerHTML = state.files.map((file) => {
    const isActive = file.id === state.selectedFileId;
    const statusCls = `file-item__status--${file.status}`;
    const statusIcon = file.status === 'processed' ? '✅' : file.status === 'error' ? '❌' : '⏳';

    return `
      <div class="file-item ${isActive ? 'file-item--active' : ''}" data-file-id="${file.id}">
        <span class="file-item__icon">📊</span>
        <div class="file-item__info">
          <div class="file-item__name">${escapeHtml(file.filename)}</div>
          <div class="file-item__meta">${file.total_rows} строк · ${file.total_sheets} листов · ${formatDate(file.uploaded_at)}</div>
        </div>
        <span class="file-item__status ${statusCls}">${statusIcon}</span>
        <button class="file-item__delete" data-action="delete" data-file-id="${file.id}" title="Удалить">✕</button>
      </div>
    `;
  }).join('');

  // Клик по файлу
  dom.fileList.querySelectorAll('.file-item').forEach((el) => {
    el.addEventListener('click', (e) => {
      if (e.target.closest('[data-action="delete"]')) return;
      const fileId = parseInt(el.dataset.fileId);
      selectFile(fileId);
    });
  });

  // Кнопки удаления
  dom.fileList.querySelectorAll('[data-action="delete"]').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const fileId = parseInt(btn.dataset.fileId);
      if (confirm('Удалить файл и все связанные данные?')) {
        await deleteFileById(fileId);
      }
    });
  });
}

async function selectFile(fileId) {
  state.selectedFileId = fileId;
  renderFileList();

  // Переключаемся на вкладку деталей
  switchTab('details');

  try {
    const file = await api.getFile(fileId);
    renderFileDetails(file);
  } catch (err) {
    showToast(`Ошибка загрузки деталей: ${err.message}`, 'error');
  }
}

async function deleteFileById(fileId) {
  try {
    await api.deleteFile(fileId);
    showToast('Файл удалён', 'success');
    if (state.selectedFileId === fileId) {
      state.selectedFileId = null;
      dom.detailsContent.hidden = true;
      dom.detailsPlaceholder.hidden = false;
    }
    await loadFiles();
  } catch (err) {
    showToast(`Ошибка удаления: ${err.message}`, 'error');
  }
}

// ============================================================
// Детали файла
// ============================================================

function renderFileDetails(file) {
  dom.detailsPlaceholder.hidden = true;
  dom.detailsContent.hidden = false;

  dom.detailsFileName.textContent = `📊 ${file.filename}`;

  dom.detailsMeta.innerHTML = `
    <span class="details-meta__item">📅 ${formatDate(file.uploaded_at)}</span>
    <span class="details-meta__item">📄 ${file.total_sheets} листов</span>
    <span class="details-meta__item">📏 ${file.total_rows} строк</span>
    <span class="details-meta__item">🔢 ${file.total_cells} ячеек</span>
    <span class="details-meta__item">${file.status === 'processed' ? '✅ Обработан' : file.status === 'error' ? '❌ Ошибка' : '⏳ В обработке'}</span>
  `;

  dom.detailsSheets.innerHTML = (file.sheets || []).map((sheet) => `
    <div class="details-sheet">
      <div class="details-sheet__header">
        <span class="details-sheet__name">📋 ${escapeHtml(sheet.original_name)}</span>
        <span class="details-sheet__meta">${sheet.row_count} × ${sheet.col_count}</span>
      </div>
      <div class="details-sheet__body">
        <div class="details-columns">
          ${(sheet.columns || []).map((col) => `
            <div class="details-column">
              <span class="details-column__name">${escapeHtml(col.original_name)}</span>
              <span class="details-column__type">${col.data_type}</span>
            </div>
          `).join('')}
        </div>
        <button class="btn btn--sm details-sheet__view-btn" data-sheet-id="${sheet.id}" data-file-id="${file.id}">
          👁 Просмотреть данные
        </button>
      </div>
    </div>
  `).join('');

  // Кнопки просмотра данных
  dom.detailsSheets.querySelectorAll('[data-sheet-id]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const sheetId = parseInt(btn.dataset.sheetId);
      const fileId = parseInt(btn.dataset.fileId);
      viewSheetData(fileId, sheetId);
    });
  });
}

async function viewSheetData(fileId, sheetId) {
  try {
    const sheet = await api.getSheetDetail(fileId, sheetId);
    const cells = await api.getSheetCells(fileId, sheetId, { limit: 500 });

    dom.modalTitle.textContent = `📋 ${sheet.original_name} (${sheet.row_count} × ${sheet.col_count})`;

    // Группируем ячейки по строкам
    const rows = {};
    cells.forEach((cell) => {
      if (!rows[cell.row_num]) rows[cell.row_num] = {};
      rows[cell.row_num][cell.col_index] = cell.value_text ?? cell.value_number ?? '';
    });

    const colNames = (sheet.columns || []).sort((a, b) => a.col_index - b.col_index);

    let html = '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:0.8rem;">';

    // Заголовки
    html += '<thead><tr>';
    html += '<th style="padding:6px 8px;border:1px solid var(--color-border);background:var(--color-surface-2);text-align:left;">#</th>';
    colNames.forEach((col) => {
      html += `<th style="padding:6px 8px;border:1px solid var(--color-border);background:var(--color-surface-2);text-align:left;white-space:nowrap;">${escapeHtml(col.original_name)}</th>`;
    });
    html += '</tr></thead><tbody>';

    // Данные
    const sortedRows = Object.keys(rows).sort((a, b) => a - b);
    sortedRows.forEach((rowNum) => {
      html += '<tr>';
      html += `<td style="padding:4px 8px;border:1px solid var(--color-border);color:var(--color-text-muted);">${rowNum}</td>`;
      colNames.forEach((col) => {
        const val = rows[rowNum][col.col_index] ?? '';
        html += `<td style="padding:4px 8px;border:1px solid var(--color-border);">${escapeHtml(String(val))}</td>`;
      });
      html += '</tr>';
    });

    html += '</tbody></table></div>';
    html += `<p style="margin-top:8px;font-size:0.8rem;color:var(--color-text-muted);">Показано ${sortedRows.length} строк из ${sheet.row_count}</p>`;

    dom.modalBody.innerHTML = html;
    dom.modalOverlay.hidden = false;
  } catch (err) {
    showToast(`Ошибка загрузки данных: ${err.message}`, 'error');
  }
}

// ============================================================
// Чат
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
  // Бейдж self-correction
  if (meta.selfCorrected) {
    metaHtml += `<span class="chat-message__badge" style="border-color:var(--color-warning);color:var(--color-warning);">🔄 Self-Correction</span>`;
  }
  if (meta.requestId) {
    metaHtml += `
      <span class="chat-message__badge" style="font-family:var(--font-mono);font-size:0.7rem;cursor:pointer;"
            title="Нажмите чтобы скопировать request_id"
            onclick="navigator.clipboard.writeText('${meta.requestId}').then(() => showToast('request_id скопирован', 'success'))">
        🆔 ${meta.requestId.substring(0, 8)}…
      </span>
      <button class="chat-message__sources-btn" data-request-id="${meta.requestId}">🔍 Trace</button>
    `;
  }
  if (meta.sources && meta.sources.length > 0) {
    metaHtml += `<button class="chat-message__sources-btn" data-sources='${JSON.stringify(meta.sources)}'>📚 Источники (${meta.sources.length})</button>`;
  }

  msgEl.innerHTML = `
    ${header}
    <div class="chat-message__content">${escapeHtml(content)}</div>
    ${metaHtml ? `<div class="chat-message__meta">${metaHtml}</div>` : ''}
  `;

  dom.chatMessages.appendChild(msgEl);
  scrollToBottom(dom.chatMessages);

  // Обработчики кнопок
  msgEl.querySelectorAll('[data-request-id]').forEach((btn) => {
    btn.addEventListener('click', () => {
      dom.traceInput.value = btn.dataset.requestId;
      switchTab('trace');
      loadTrace(btn.dataset.requestId);
    });
  });

  msgEl.querySelectorAll('[data-sources]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const sources = JSON.parse(btn.dataset.sources);
      showSourcesModal(sources);
    });
  });

  state.messages.push({ type, content, meta });
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

// ============================================================
// Индикатор процесса агента
// ============================================================

const AGENT_STEPS = {
  rag:        { icon: '🔍', label: 'Поиск данных',         desc: 'Гибридный поиск по загруженным Excel-файлам (BM25 + векторные эмбеддинги)' },
  classifier: { icon: '🏷️', label: 'Классификация',        desc: 'Определение типа запроса: поиск, агрегация, сравнение листов или дельта' },
  planner:    { icon: '📋', label: 'Планирование',         desc: 'Составление плана действий и выбор релевантных листов/колонок' },
  codegen:    { icon: '💻', label: 'Генерация SQL',        desc: 'Создание SQL-запроса на основе плана и схемы данных (с валидацией)' },
  executor:   { icon: '⚡', label: 'Выполнение SQL',       desc: 'Запуск SQL-запроса к базе данных и получение результата' },
  verifier:   { icon: '✅', label: 'Верификация',          desc: 'Проверка ответа: соответствует ли он вопросу и данным' },
  answer:     { icon: '💬', label: 'Формирование ответа',  desc: 'Формулировка финального ответа пользователю' },
};

function showAgentProgress(mode) {
  const el = document.createElement('div');
  el.className = 'chat-message chat-message--assistant';
  el.id = 'agentProgress';

  // Показываем шаги в зависимости от режима
  const steps = mode === 'rag'
    ? ['rag', 'answer']
    : ['rag', 'classifier', 'planner', 'codegen', 'executor', 'verifier', 'answer'];

  el.innerHTML = `
    <div class="chat-message__header">🤖 Ассистент</div>
    <div class="agent-progress" id="agentProgressInner">
      ${steps.map((stepKey, i) => {
        const step = AGENT_STEPS[stepKey];
        return `
          <div class="agent-progress__step" data-step="${stepKey}" data-index="${i}">
            <div class="agent-progress__indicator">
              <span class="agent-progress__icon">${step.icon}</span>
              <div class="agent-progress__line"></div>
            </div>
            <div class="agent-progress__info">
              <div class="agent-progress__label">${step.label}</div>
              <div class="agent-progress__desc">${step.desc}</div>
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `;

  dom.chatMessages.appendChild(el);
  scrollToBottom(dom.chatMessages);

  // Активируем первый шаг
  activateAgentStep(0);
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

  // Скролл к активному шагу
  const activeStep = container.querySelector('.agent-progress__step--active');
  if (activeStep) {
    activeStep.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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
  if (el) el.remove();
}

async function handleAskQuestion(question) {
  if (state.isAsking) return;
  if (!question.trim()) return;

  state.isAsking = true;
  dom.askBtn.disabled = true;
  dom.questionInput.disabled = true;

  const mode = dom.modeSelect.value;
  const topK = parseInt(dom.topKInput.value) || 10;

  addMessage('user', question);

  // Собираем историю диалога для контекста
  // Берём последние N сообщений (user + assistant), исключая системные и ошибки
  const conversation_history = state.messages
    .filter((m) => m.type === 'user' || m.type === 'assistant')
    .slice(-10)  // последние 10 сообщений (5 пар вопрос-ответ)
    .map((m) => ({
      role: m.type === 'user' ? 'user' : 'assistant',
      content: m.content,
    }));

  // Показываем прогресс агента
  showAgentProgress(mode);

  const totalSteps = mode === 'rag' ? 2 : 7;
  for (let i = 0; i < totalSteps; i++) {
    await new Promise(r => setTimeout(r, 600 + Math.random() * 400));
    activateAgentStep(i);
  }

  try {
    const result = await api.askQuestion({
      question,
      top_k: topK,
      mode,
      conversation_history,
    });

    completeAgentProgress();
    await new Promise(r => setTimeout(r, 300));
    removeAgentProgress();

    addMessage('assistant', result.answer, {
      mode: result.mode_used,
      confidence: result.confidence,
      latency: result.latency_ms,
      requestId: result.request_id,
      sources: result.sources,
      sqlQuery: result.sql_query,
      sqlResultPreview: result.sql_result_preview,
      selfCorrected: result.self_corrected || false,
    });
  } catch (err) {
    removeAgentProgress();
    addMessage('error', `❌ Ошибка: ${err.message}`);
  } finally {
    state.isAsking = false;
    dom.askBtn.disabled = false;
    dom.questionInput.disabled = false;
    dom.questionInput.focus();
  }
}

function showSourcesModal(sources) {
  dom.modalTitle.textContent = `📚 Источники (${sources.length})`;
  dom.modalBody.innerHTML = `
    <div class="sources-list">
      ${sources.map((s, i) => `
        <div class="source-item">
          <div class="source-item__header">
            <span class="source-item__rank">#${s.rank || i + 1}</span>
            <span class="source-item__score">Score: ${(s.score || 0).toFixed(4)}</span>
            <span class="source-item__type">${s.source_type || 'unknown'}</span>
          </div>
          <div class="source-item__text">${escapeHtml(s.chunk || '')}</div>
        </div>
      `).join('')}
    </div>
  `;
  dom.modalOverlay.hidden = false;
}

// ============================================================
// Трассировка
// ============================================================

async function loadTraceHistory() {
  try {
    const traces = await api.listTraces({ limit: 20 });

    if (!traces || traces.length === 0) {
      dom.traceHistoryList.innerHTML = `<div class="trace-history__empty">История пуста</div>`;
      return;
    }

    dom.traceHistoryList.innerHTML = traces.map((t) => {
      const statusCls = `trace-history__status--${t.status}`;
      const statusIcon = t.status === 'success' ? '✅' : t.status === 'failed' ? '❌' : '⚠️';
      const time = t.created_at ? formatDate(t.created_at) : '';

      return `
        <div class="trace-history__item" data-request-id="${t.request_id}">
          <span class="trace-history__question">${escapeHtml(t.question || '—')}</span>
          <span class="trace-history__status ${statusCls}">${statusIcon}</span>
          <span class="trace-history__time">${time}</span>
        </div>
      `;
    }).join('');

    dom.traceHistoryList.querySelectorAll('.trace-history__item').forEach((el) => {
      el.addEventListener('click', () => {
        const rid = el.dataset.requestId;
        dom.traceInput.value = rid;
        loadTrace(rid);
      });
    });
  } catch (err) {
    // История не критична, просто игнорируем ошибку
    console.warn('Failed to load trace history:', err);
  }
}

async function loadTrace(requestId) {
  if (!requestId.trim()) return;

  dom.tracePlaceholder.hidden = true;
  dom.traceResult.hidden = false;
  dom.traceResult.innerHTML = '<p style="color:var(--color-text-muted);">Загрузка...</p>';

  try {
    const trace = await api.getTrace(requestId);

    const stepIcons = {
      question: '❓',
      classifier: '🏷',
      planner: '📋',
      codegen: '💻',
      executor: '⚡',
      verifier: '✅',
      retrieval: '🔍',
      verification: '🔎',
      answer: '💬',
    };

    dom.traceResult.innerHTML = `
      <div style="margin-bottom:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
        <strong>Request ID:</strong>
        <code style="color:var(--color-primary);font-size:0.8rem;">${escapeHtml(trace.request_id)}</code>
        <button class="btn btn--sm" onclick="navigator.clipboard.writeText('${trace.request_id}').then(() => showToast('request_id скопирован', 'success'))" title="Копировать">📋</button>
        <span style="color:var(--color-text-muted);font-size:0.85rem;">⏱ ${formatMs(trace.latency_ms)}</span>
        <span style="color:var(--color-text-muted);font-size:0.85rem;">Статус: ${trace.status}</span>
      </div>
      ${(trace.steps || []).map((step) => `
        <div class="trace-step">
          <div class="trace-step__header">
            <span class="trace-step__icon">${stepIcons[step.step] || '📌'}</span>
            <span>${step.step}</span>
          </div>
          <div class="trace-step__body">${escapeHtml(JSON.stringify(step.data, null, 2))}</div>
        </div>
      `).join('')}
    `;
  } catch (err) {
    dom.traceResult.innerHTML = `<p style="color:var(--color-error);">❌ Ошибка: ${err.message}</p>`;
  }
}

// ============================================================
// Вкладки
// ============================================================

function switchTab(tabName) {
  dom.tabs.forEach((tab) => {
    const isActive = tab.dataset.tab === tabName;
    tab.classList.toggle('tab--active', isActive);
  });

  dom.tabChat.hidden = tabName !== 'chat';
  dom.tabChat.classList.toggle('tab-content--active', tabName === 'chat');
  dom.tabDetails.hidden = tabName !== 'details';
  dom.tabDetails.classList.toggle('tab-content--active', tabName === 'details');
  dom.tabTrace.hidden = tabName !== 'trace';
  dom.tabTrace.classList.toggle('tab-content--active', tabName === 'trace');
}

// ============================================================
// Escape HTML
// ============================================================

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ============================================================
// Инициализация событий
// ============================================================

function init() {
  // Health check
  checkHealth();
  setInterval(checkHealth, 30000);

  // Загрузка файлов
  loadFiles();

  // Drag & drop
  dom.dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dom.dropzone.classList.add('upload-form__dropzone--dragover');
  });

  dom.dropzone.addEventListener('dragleave', () => {
    dom.dropzone.classList.remove('upload-form__dropzone--dragover');
  });

  dom.dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dom.dropzone.classList.remove('upload-form__dropzone--dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      dom.fileInput.files = files;
      dom.uploadBtn.disabled = false;
    }
  });

  // Выбор файла
  dom.fileInput.addEventListener('change', () => {
    dom.uploadBtn.disabled = !dom.fileInput.files.length;
  });

  dom.dropzone.addEventListener('click', () => {
    dom.fileInput.click();
  });

  // Загрузка
  dom.uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const file = dom.fileInput.files[0];
    if (!file) return;

    dom.uploadBtn.disabled = true;
    dom.uploadBtn.textContent = '⏳ Загрузка...';

    try {
      const result = await api.uploadFile(file);
      showToast(`Файл "${result.file.filename}" загружен`, 'success');
      dom.fileInput.value = '';
      dom.uploadBtn.textContent = '⬆ Загрузить';
      dom.uploadBtn.disabled = true;
      await loadFiles();
    } catch (err) {
      showToast(`Ошибка загрузки: ${err.message}`, 'error');
      dom.uploadBtn.textContent = '⬆ Загрузить';
      dom.uploadBtn.disabled = false;
    }
  });

  // Обновление списка файлов
  dom.refreshFilesBtn.addEventListener('click', loadFiles);

  // Чат
  dom.chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const question = dom.questionInput.value.trim();
    if (question) {
      handleAskQuestion(question);
      dom.questionInput.value = '';
    }
  });

  // Вкладки
  dom.tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      switchTab(tab.dataset.tab);
    });
  });

  // Трассировка
  loadTraceHistory();

  dom.traceBtn.addEventListener('click', () => {
    loadTrace(dom.traceInput.value.trim());
  });

  dom.traceRefreshBtn.addEventListener('click', loadTraceHistory);

  dom.traceInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      loadTrace(dom.traceInput.value.trim());
    }
  });

  // Модальное окно
  dom.modalClose.addEventListener('click', () => {
    dom.modalOverlay.hidden = true;
  });

  dom.modalOverlay.addEventListener('click', (e) => {
    if (e.target === dom.modalOverlay) {
      dom.modalOverlay.hidden = true;
    }
  });

  // Клавиша Escape для модалки
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      dom.modalOverlay.hidden = true;
    }
  });

  // Включаем кнопку отправки вопроса при наличии текста
  dom.questionInput.addEventListener('input', () => {
    dom.askBtn.disabled = !dom.questionInput.value.trim() || state.isAsking;
  });

  console.log('🔷 EVRAZ AI Agent Frontend initialized');
}

// ============================================================
// Старт
// ============================================================

document.addEventListener('DOMContentLoaded', init);