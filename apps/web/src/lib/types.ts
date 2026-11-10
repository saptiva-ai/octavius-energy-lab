/**
 * Type definitions for the application
 */

import type {
  AuditArtifact,
  ChatMessageMetadata,
} from "./contracts/message-metadata";

// User/auth related types
export interface UserPreferencesProfile {
  theme: string;
  language: string;
  defaultModel: string;
  chatSettings: Record<string, unknown>;
}

export interface UserProfile {
  id: string;
  username: string;
  email: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
  lastLogin?: string | null;
  preferences: UserPreferencesProfile;
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  user: UserProfile;
}

export interface RefreshTokenResponse {
  accessToken: string;
  expiresIn: number;
}

export interface RegisterPayload {
  username: string;
  email: string;
  password: string;
}

// Chat related types
export type ChatMessageStatus = "sending" | "streaming" | "delivered" | "error";
export type ChatMessageKind =
  | "user"
  | "assistant"
  | "system"
  | "file-review"
  | "chart";

// Document review stages
export type ReviewStage =
  | "QUEUED"
  | "RECEIVED"
  | "EXTRACT"
  | "LT_GRAMMAR"
  | "LLM_SUGGEST"
  | "SUMMARY"
  | "COLOR_AUDIT"
  | "READY"
  | "FAILED"
  | "UPLOAD"
  | "CACHE"
  | "PROCESSING";

export type FileReviewStatus =
  | "uploading"
  | "uploaded"
  | "processing"
  | "ready"
  | "reviewing"
  | "completed"
  | "error";

export interface FileReviewData {
  docId?: string;
  jobId?: string;
  filename: string;
  fileSize?: number;
  totalPages?: number;
  status: FileReviewStatus;
  stages: ReviewStage[];
  progress?: number;
  currentStage?: string;
  errors?: string[];
}

export interface ChatMessage {
  id: string;
  content: string;
  role: "user" | "assistant" | "system";
  kind?: ChatMessageKind;
  artifact?: AuditArtifact | null;
  timestamp: string | Date;
  status?: ChatMessageStatus;
  model?: string;
  tokens?: number;
  latency?: number;
  toolsUsed?: string[];
  isError?: boolean;
  isStreaming?: boolean;
  task_id?: string;
  // UX-004 file attachments metadata
  attachments?: {
    name: string;
    size: number;
    type: string;
  }[];
  metadata?: ChatMessageMetadata;
  // Document review data (when kind === 'file-review')
  review?: FileReviewData;
}

// P0-BE-UNIQ-EMPTY: Conversation state from backend
export type ConversationState = "draft" | "active" | "creating" | "error";

export interface ChatSession {
  id: string;
  title: string;
  title_override?: boolean; // Whether title was manually set by user
  created_at: string;
  updated_at: string;
  first_message_at: string | null; // Timestamp of first user message (null for empty drafts)
  last_message_at: string | null; // Timestamp of last message (null for empty drafts)
  message_count: number;
  model: string;
  preview?: string;
  pinned?: boolean;
  state?: ConversationState; // P0-BE-UNIQ-EMPTY: Current lifecycle state
  idempotency_key?: string;
  tools_enabled?: Record<string, boolean>;
}

// Helper to check if chat has first message
export function hasFirstMessage(session: ChatSession): boolean {
  return session.first_message_at !== null || session.message_count > 0;
}

// P0-UX-HIST-001: Optimistic conversation with additional UI flags
export interface ChatSessionOptimistic extends ChatSession {
  isOptimistic?: boolean; // Indicates this is a temporary optimistic session
  isNew?: boolean; // Indicates this session was just created (for highlight)
  tempId?: string; // Temporary ID before server reconciliation
  realId?: string; // Real ID after reconciliation (if different from id)
  pending?: boolean; // Indicates optimistic entry awaiting backend confirmation
}

export type ArtifactType = "markdown" | "code" | "graph" | "chart";

// Generic chart artifact data (Plotly-based). The concrete chart viewer for
// the current vertical is rebuilt on top of this contract; this type only
// describes the transport shape shared by chat, canvas and persistence.
export interface ChartData {
  type?: "chart";
  title?: string;
  chart_status?: "success" | "empty" | "error" | "clarification";
  response_text?: string;
  time_range?: {
    start: string;
    end: string;
  };
  plotly_config: {
    data: Array<{
      // x/y: traces cartesianos (line/bar/scatter). node/link: sankey (sin x/y).
      x?: (string | number)[];
      y?: (string | number)[];
      type: string;
      name?: string;
      mode?: string;
      orientation?: string;
      marker?: Record<string, any>;
      line?: Record<string, any>;
      node?: Record<string, any>;
      link?: Record<string, any>;
    }>;
    layout: {
      title?: string;
      xaxis?: Record<string, any>;
      yaxis?: Record<string, any>;
      legend?: Record<string, any>;
      margin?: Record<string, any>;
      [key: string]: any;
    };
    config?: {
      responsive?: boolean;
      displayModeBar?: boolean;
      [key: string]: any;
    };
  };
  data_as_of?: string;
  source?: string;
  // Enriched metadata from backend (optional)
  metadata?: {
    sql_generated?: string;
    metric_interpretation?: string;
    pipeline?: string;
    execution_time_ms?: number;
    [key: string]: any;
  };
  /** Contrato completo del plugin de dominio (retail-advisor), cuando el
   *  chart se construyó desde ahí. Da grounding/freshness/table_data ricos
   *  sin tener que reconstruirlos desde plotly_config. */
  analytics?: import("./contracts").AnalyticsResponse;
}

// 🆕 Canvas-Chart synchronization state (Phase 2)
export interface CanvasChartSync {
  artifactId: string;
  messageId: string;
  isActive: boolean;
}

export interface ArtifactVersion {
  version: number;
  content: string | Record<string, any>;
  created_at: string;
}

export interface ArtifactRecord {
  id: string;
  user_id: string;
  chat_session_id?: string | null;
  title: string;
  type: ArtifactType;
  content: string | Record<string, any>;
  versions: ArtifactVersion[];
  created_at: string;
  updated_at: string;
}

export interface ToolInvocation {
  tool_name: string;
  arguments?: Record<string, any>;
  result?: { id: string; title?: string; type?: string };
}

// Audit report (frontend mirror of backend AuditReportResponse)
export interface AuditStats {
  critical: number;
  high: number;
  medium: number;
  low: number;
  total: number;
}

export interface AuditFinding {
  id?: string | null;
  category: string;
  severity: string;
  message: string;
  page?: number | null;
  suggestion?: string | null;
  rule?: string | null;
  raw?: Record<string, any>;
}

export interface AuditReportResponse {
  doc_name: string;
  stats: AuditStats;
  categories: Record<string, AuditFinding[]>;
  actions: string[];
  metadata: Record<string, any> & {
    filename?: string;
    display_name?: string;
  };
}

// Research related types
export interface ResearchTask {
  id: string;
  query: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  progress?: number;
  result?: any;
  created_at: string;
  updated_at: string;
  estimated_completion?: string;
  stream_url?: string;
  research_type?: "web_search" | "deep_research";
  params?: {
    budget?: number;
    max_iterations?: number;
    scope?: string;
    sources_limit?: number;
    depth_level?: "shallow" | "medium" | "deep";
    focus_areas?: string[];
    language?: string;
    include_citations?: boolean;
  };
}

// Model related types
export interface ModelInfo {
  id: string;
  name: string;
  description: string;
  maxTokens: number;
  supportsStreaming: boolean;
  supportsTools: boolean;
  category: "general" | "coding" | "research" | "creative";
  status: "available" | "unavailable" | "maintenance";
}

// Tool related types
export interface ToolConfig {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  category: "search" | "analysis" | "generation" | "processing";
  parameters?: Record<string, any>;
}

// API response types
export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pages: number;
  limit: number;
}

// Streaming event types (from streaming.ts)
export interface StreamEvent {
  event_type: string;
  task_id: string;
  timestamp: string;
  data: Record<string, any>;
  progress?: number;
}

// Settings types
export interface UserSettings {
  theme: "light" | "dark" | "system";
  language: string;
  notifications: {
    enabled: boolean;
    taskCompletion: boolean;
    errors: boolean;
  };
  chat: {
    defaultModel: string;
    maxTokens: number;
    temperature: number;
    streamEnabled: boolean;
    autoScroll: boolean;
  };
  research: {
    defaultDepthLevel: "shallow" | "medium" | "deep";
    maxSources: number;
    includeCitations: boolean;
    autoExport: boolean;
  };
}

export type SaptivaKeySource = "unset" | "environment" | "database";

export interface SaptivaKeyStatus {
  configured: boolean;
  mode: "demo" | "live";
  source: SaptivaKeySource;
  hint?: string | null;
  statusMessage?: string | null;
  lastValidatedAt?: string | null;
  updatedAt?: string | null;
  updatedBy?: string | null;
}

export interface UpdateSaptivaKeyPayload {
  apiKey: string;
  validate?: boolean;
}

// Error types
export interface AppError {
  code: string;
  message: string;
  details?: any;
  timestamp: string;
  context?: Record<string, any>;
}

// Navigation types
export interface NavItem {
  id: string;
  label: string;
  href: string;
  icon?: React.ComponentType;
  badge?: string | number;
  children?: NavItem[];
}

// File/Report types
export interface ReportMetadata {
  id: string;
  title: string;
  format: "md" | "pdf" | "docx" | "html";
  size: number;
  created_at: string;
  sources_count: number;
  pages?: number;
}

export interface ExportOptions {
  format: "md" | "pdf" | "docx" | "html";
  includeSources: boolean;
  includeMetadata: boolean;
  template?: string;
}

export interface FeatureFlagsResponse {
  deep_research_kill_switch?: boolean;
  deep_research_enabled: boolean;
  deep_research_auto: boolean;
  deep_research_complexity_threshold: number;
  create_chat_optimistic?: boolean;
}

export type ChatModel = {
  id: string;
  value: string;
  label: string;
  description: string;
  tags: string[];
  available?: boolean;
  backendId?: string | null;
};

// Message Feedback types
export type FeedbackRating = "up" | "down";

export interface MessageFeedback {
  id?: string;
  messageId: string;
  conversationId: string;
  rating: FeedbackRating;
  reason?: string;
  createdAt: string;
}

export interface MessageFeedbackCreate {
  messageId: string;
  conversationId: string;
  rating: FeedbackRating;
  reason?: string;
}
