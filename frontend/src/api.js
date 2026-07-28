/**
 * API клиент для взаимодействия с бэкендом EVRAZ RAG Service.
 * Все запросы идут через /api/ префикс (проксируется Vite в dev режиме).
 */

const API_BASE = '/api';

/**
 * Базовый fetch с обработкой ошибок.
 */
async function request(method, path, options = {}) {
  const url = `${API_BASE}${path}`;
  const { body, params, ...rest } = options;

  const fetchOptions = {
    method,
    headers: {
      'Accept': 'application/json',
      ...rest.headers,
    },
    ...rest,
  };

  if (body) {
    if (body instanceof FormData) {
      delete fetchOptions.headers['Content-Type'];
      fetchOptions.body = body;
    } else {
      fetchOptions.headers['Content-Type'] = 'application/json';
      fetchOptions.body = JSON.stringify(body);
    }
  }

  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, value);
      }
    });
    const qs = searchParams.toString();
    if (qs) {
      // Используем URL с query params
      return request(method, `${path}?${qs}`, { ...options, params: undefined, body });
    }
  }

  const response = await fetch(url, fetchOptions);

  if (response.status === 204) {
    return null;
  }

  const data = await response.json();

  if (!response.ok) {
    const message = data.detail || `HTTP ${response.status}: ${response.statusText}`;
    throw new Error(message);
  }

  return data;
}

// ---------- Утилиты ----------

function get(path, options = {}) {
  return request('GET', path, options);
}

function post(path, options = {}) {
  return request('POST', path, options);
}

function del(path, options = {}) {
  return request('DELETE', path, options);
}

// ---------- Health ----------

export async function checkHealth() {
  return get('/health');
}

// ---------- Files ----------

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  return post('/files/upload', { body: formData });
}

export async function listFiles(params = {}) {
  return get('/files', { params });
}

export async function getFile(fileId) {
  return get(`/files/${fileId}`);
}

export async function deleteFile(fileId) {
  return del(`/files/${fileId}`);
}

export async function getFileSheets(fileId) {
  return get(`/files/${fileId}/sheets`);
}

export async function getSheetDetail(fileId, sheetId) {
  return get(`/files/${fileId}/sheets/${sheetId}`);
}

export async function getSheetColumns(fileId, sheetId) {
  return get(`/files/${fileId}/sheets/${sheetId}/columns`);
}

export async function getSheetCells(fileId, sheetId, params = {}) {
  return get(`/files/${fileId}/sheets/${sheetId}/cells`, { params });
}

export async function reindexFile(fileId) {
  return post(`/files/${fileId}/reindex`);
}

// ---------- Ask (RAG / Agent) ----------

export async function askQuestion({ question, top_k = 10, mode = 'auto', conversation_history = [] }) {
  return post('/ask', {
    body: { question, top_k, mode, conversation_history },
  });
}

// ---------- Trace ----------

export async function listTraces(params = {}) {
  return get('/trace', { params });
}

export async function getTrace(requestId) {
  return get(`/trace/${requestId}`);
}

export default {
  checkHealth,
  uploadFile,
  listFiles,
  getFile,
  deleteFile,
  getFileSheets,
  getSheetDetail,
  getSheetColumns,
  getSheetCells,
  reindexFile,
  askQuestion,
  listTraces,
  getTrace,
};