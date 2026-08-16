// Типы данных API бэкенда EVRAZ RAG Service

export interface FileResponse {
  id: number;
  filename: string;
  file_hash: string;
  total_sheets: number;
  total_rows: number;
  total_cells: number;
  uploaded_at: string;
  processed_at?: string | null;
  status: string;
  error_message?: string | null;
}

export interface FileListResponse {
  files: FileResponse[];
  total: number;
}

export interface SheetResponse {
  id: number;
  file_id: number;
  sheet_index: number;
  original_name: string;
  normalized_name: string;
  description?: string | null;
  row_count: number;
  col_count: number;
  period?: string | null;
  sheet_kind?: string | null;
  sheet_kind_auto?: boolean | null;
  created_at: string;
}

export interface ColumnResponse {
  id: number;
  sheet_id: number;
  col_index: number;
  original_name: string;
  normalized_name: string;
  data_type: string;
  description?: string | null;
  sample_values?: unknown[] | null;
}

export interface CellResponse {
  id: number;
  sheet_id: number;
  row_num: number;
  col_index: number;
  value_text?: string | null;
  value_number?: number | null;
  value_date?: string | null;
  original_value?: string | null;
}

export interface FileDetailResponse extends FileResponse {
  sheets: SheetResponse[];
}

export interface SheetDetailResponse extends SheetResponse {
  columns: ColumnResponse[];
}

export interface UploadResponse {
  message: string;
  file: FileResponse;
}

export interface ConversationTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface SourceInfo {
  chunk: string;
  score: number;
  source_type: string;
  source_id: number;
  rank: number;
}

export interface AskResponse {
  answer: string;
  confidence: number;
  sources: SourceInfo[];
  request_id: string;
  latency_ms: number;
  mode_used: string;
  response_mode?: string;
  query_type: string;
  sql_query: string;
  sql_result_preview: unknown[];
  retry_count: number;
  status: string;
  self_corrected: boolean;
  trace_id?: string | null;
}

export interface AskRequest {
  question: string;
  top_k?: number;
  mode?: 'agent';
  response_mode?: 'detailed' | 'concise';
  conversation_history?: ConversationTurn[];
  conversation_id?: string | null;
}

export interface TraceStepInfo {
  step: string;
  data?: unknown;
}

export interface TraceResponse {
  request_id: string;
  question: string;
  answer: string;
  status: string;
  latency_ms: number;
  trace: Record<string, unknown>;
  steps: TraceStepInfo[];
}

export interface TraceListItem {
  request_id: string;
  question: string;
  status: string;
  latency_ms: number;
  created_at?: string | null;
}

export interface MetricsSummary {
  total_requests: number;
  requests_by_status: Record<string, number>;
  avg_latency_ms: number;
  total_tokens: number;
  tokens_by_node: Record<string, Record<string, number>>;
  total_cost_rub: number;
  cost_by_node: Record<string, number>;
}

export type HealthResponse = {
  status?: string;
  [key: string]: unknown;
};