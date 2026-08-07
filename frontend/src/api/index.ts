import type {
  AskRequest,
  AskResponse,
  CellResponse,
  ColumnResponse,
  FileDetailResponse,
  FileListResponse,
  HealthResponse,
  SheetDetailResponse,
  SheetResponse,
  TraceListItem,
  TraceResponse,
  UploadResponse,
} from '@/types/api';

const API_BASE = '/api';

async function request<T>(method: string, path: string, options: { body?: unknown; params?: Record<string, unknown> } = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const { body, params } = options;

  const fetchOptions: RequestInit = {
    method,
    headers: {
      Accept: 'application/json',
    },
  };

  if (body) {
    if (body instanceof FormData) {
      fetchOptions.body = body;
    } else {
      fetchOptions.headers = { ...fetchOptions.headers, 'Content-Type': 'application/json' };
      fetchOptions.body = JSON.stringify(body);
    }
  }

  const finalUrl = params
    ? `${url}?${new URLSearchParams(
        Object.entries(params)
          .filter(([, v]) => v !== undefined && v !== null)
          .map(([k, v]) => [k, String(v)])
      ).toString()}`
    : url;

  const response = await fetch(finalUrl, fetchOptions);

  if (response.status === 204) {
    return null as T;
  }

  const data = await response.json();

  if (!response.ok) {
    const message = data.detail || `HTTP ${response.status}: ${response.statusText}`;
    throw new Error(message);
  }

  return data as T;
}

function get<T>(path: string, options?: { params?: Record<string, unknown> }) {
  return request<T>('GET', path, options);
}

function post<T>(path: string, options?: { body?: unknown }) {
  return request<T>('POST', path, options);
}

function del<T>(path: string) {
  return request<T>('DELETE', path);
}

// ---------- Health ----------
export function checkHealth() {
  return get<HealthResponse>('/health');
}

// ---------- Files ----------
export function uploadFile(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return post<UploadResponse>('/files/upload', { body: formData });
}

export function listFiles(params: { limit?: number; status?: string } = {}) {
  return get<FileListResponse>('/files', { params });
}

export function getFile(fileId: number) {
  return get<FileDetailResponse>(`/files/${fileId}`);
}

export function deleteFile(fileId: number) {
  return del<void>(`/files/${fileId}`);
}

export function getFileSheets(fileId: number) {
  return get<SheetResponse[]>(`/files/${fileId}/sheets`);
}

export function getSheetDetail(fileId: number, sheetId: number) {
  return get<SheetDetailResponse>(`/files/${fileId}/sheets/${sheetId}`);
}

export function getSheetColumns(fileId: number, sheetId: number) {
  return get<ColumnResponse[]>(`/files/${fileId}/sheets/${sheetId}/columns`);
}

export function getSheetCells(fileId: number, sheetId: number, params: { skip?: number; limit?: number } = {}) {
  return get<CellResponse[]>(`/files/${fileId}/sheets/${sheetId}/cells`, { params });
}

export function reindexFile(fileId: number) {
  return post<{ message: string }>(`/files/${fileId}/reindex`);
}

// ---------- Ask ----------
export function askQuestion(req: AskRequest) {
  return post<AskResponse>('/ask', {
    body: {
      question: req.question,
      top_k: req.top_k ?? 10,
      mode: req.mode ?? 'auto',
      conversation_history: req.conversation_history ?? [],
    },
  });
}

// ---------- Trace ----------
export function listTraces(params: { limit?: number } = {}) {
  return get<TraceListItem[]>(`/trace`, { params });
}

export function getTrace(requestId: string) {
  return get<TraceResponse>(`/trace/${requestId}`);
}

export const api = {
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

export default api;