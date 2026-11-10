/**
 * MCP (Model Context Protocol) Types
 *
 * TypeScript definitions matching backend protocol.py
 */

export enum ToolCategory {
  DOCUMENT_ANALYSIS = "document_analysis",
  DATA_ANALYTICS = "data_analytics",
  VISUALIZATION = "visualization",
  RESEARCH = "research",
  COMPLIANCE = "compliance",
}

export enum ToolCapability {
  SYNC = "sync",
  ASYNC = "async",
  STREAMING = "streaming",
  IDEMPOTENT = "idempotent",
  CACHEABLE = "cacheable",
  STATEFUL = "stateful",
}

export interface ToolSpec {
  name: string;
  version: string;
  display_name: string;
  description: string;
  category: ToolCategory;
  capabilities: ToolCapability[];
  input_schema: Record<string, any>;
  output_schema: Record<string, any>;
  tags: string[];
  author: string;
  requires_auth: boolean;
  rate_limit?: {
    calls_per_minute: number;
  };
  timeout_ms: number;
  max_payload_size_kb: number;
}

export interface ToolInvokeRequest {
  tool: string;
  version?: string;
  payload: Record<string, any>;
  context?: Record<string, any>;
  idempotency_key?: string;
}

export interface ToolError {
  code: string;
  message: string;
  details?: Record<string, any>;
  retry_after_ms?: number;
}

export interface ToolInvokeResponse<T = any> {
  success: boolean;
  tool: string;
  version: string;
  result?: T;
  error?: ToolError;
  metadata: Record<string, any>;
  invocation_id: string;
  duration_ms: number;
  cached: boolean;
}

export interface ToolMetrics {
  tool: string;
  version: string;
  invocation_count: number;
  success_count: number;
  error_count: number;
  avg_duration_ms: number;
  p95_duration_ms: number;
  p99_duration_ms: number;
  last_invoked_at?: string;
  cache_hit_rate: number;
}

// Tool-specific result types

export interface AuditFileResult {
  job_id: string;
  status: "done" | "error";
  findings: Array<{
    id: string;
    category: string;
    rule: string;
    issue: string;
    severity: "high" | "medium" | "low";
    location?: {
      page?: number;
      bbox?: number[];
    };
    suggestion?: string;
  }>;
  summary: {
    total_findings: number;
    policy_id: string;
    policy_name: string;
    disclaimer_coverage?: number;
    findings_by_severity: Record<string, number>;
  };
  attachments?: any[];
}

export interface ExcelAnalyzerResult {
  doc_id: string;
  sheet_name: string;
  stats?: {
    row_count: number;
    column_count: number;
    columns: Array<{
      name: string;
      dtype: string;
      non_null_count: number;
      null_count: number;
    }>;
  };
  aggregates?: Record<
    string,
    {
      sum: number;
      mean: number;
      median: number;
      std: number;
      min: number;
      max: number;
    }
  >;
  validation?: {
    total_missing_values: number;
    columns_with_missing: string[];
    type_mismatches: any[];
  };
  preview?: Record<string, any>[];
}

export interface VizToolResult {
  library: "plotly" | "echarts";
  spec: Record<string, any>;
  preview_data: Record<string, any>[];
  metadata: {
    data_points: number;
    columns: string[];
  };
}

// Task Management Types (202 Accepted Pattern)

export type TaskStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type TaskPriority = "low" | "normal" | "high";

export interface TaskCreateRequest {
  tool: string;
  version?: string;
  payload: Record<string, any>;
  priority?: TaskPriority;
}

export interface TaskCreateResponse {
  task_id: string;
  status: TaskStatus;
  poll_url: string;
  cancel_url: string;
  estimated_duration_ms: number;
}

export interface TaskStatusResponse {
  task_id: string;
  tool: string;
  status: TaskStatus;
  progress: number; // 0.0 to 1.0
  progress_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  result?: any; // Available when status = "completed"
  error?: ToolError; // Available when status = "failed"
}

export interface TaskCancelResponse {
  task_id: string;
  status: string;
  message: string;
}

export interface TaskListResponse {
  task_id: string;
  tool: string;
  status: TaskStatus;
  progress: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

// Poll Options

export interface PollOptions {
  /**
   * Polling interval in milliseconds (default: 1000)
   */
  intervalMs?: number;

  /**
   * Maximum number of poll attempts (default: 300 = 5 minutes at 1s interval)
   */
  maxAttempts?: number;

  /**
   * Timeout in milliseconds (default: 300000 = 5 minutes)
   */
  timeoutMs?: number;

  /**
   * Progress callback fired on each poll
   */
  onProgress?: (status: TaskStatusResponse) => void;

  /**
   * AbortSignal for cancellation
   */
  signal?: AbortSignal;
}

// Error Code Enum (matches backend)

export enum ErrorCode {
  VALIDATION_ERROR = "VALIDATION_ERROR",
  TIMEOUT = "TIMEOUT",
  TOOL_BUSY = "TOOL_BUSY",
  BACKEND_DEP_UNAVAILABLE = "BACKEND_DEP_UNAVAILABLE",
  RATE_LIMIT = "RATE_LIMIT",
  PERMISSION_DENIED = "PERMISSION_DENIED",
  TOOL_NOT_FOUND = "TOOL_NOT_FOUND",
  EXECUTION_ERROR = "EXECUTION_ERROR",
  CANCELLED = "CANCELLED",
}
