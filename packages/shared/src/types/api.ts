/**
 * Shared API types for Copilot OS
 */

export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: ApiError;
  meta?: {
    timestamp: string;
    request_id: string;
    version: string;
  };
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, any>;
  trace_id?: string;
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  pagination: {
    page: number;
    limit: number;
    total: number;
    pages: number;
  };
}

// Health Check
export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  version: string;
  services: {
    database: ServiceStatus;
    redis: ServiceStatus;
    aletheia: ServiceStatus;
  };
  uptime: number;
}

export interface ServiceStatus {
  status: 'up' | 'down' | 'degraded';
  latency_ms?: number;
  error?: string;
}

// Authentication
export interface AuthRequest {
  username: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface User {
  id: string;
  username: string;
  email: string;
  created_at: string;
  last_login?: string;
  is_active: boolean;
  preferences: UserPreferences;
}

export interface UserPreferences {
  theme: 'light' | 'dark' | 'auto';
  language: string;
  default_model: string;
  chat_settings: {
    stream_enabled: boolean;
    auto_scroll: boolean;
    show_timestamps: boolean;
  };
}

// Chat
export interface ChatMessage {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: {
    model?: string;
    tokens?: number;
    latency_ms?: number;
    task_id?: string;
    tool_calls?: ToolCall[];
  };
  status: 'sending' | 'delivered' | 'error' | 'streaming';
}

export interface ChatSession {
  id: string;
  title: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message?: ChatMessage;
  settings: ChatSettings;
}

export interface ChatSettings {
  model: string;
  temperature: number;
  max_tokens: number;
  tools_enabled: {
    web_search: boolean;
    deep_research: boolean;
  };
  research_params?: DeepResearchParams;
}

// Tool Calls
export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, any>;
  result?: any;
  status: 'pending' | 'running' | 'completed' | 'error';
  created_at: string;
  completed_at?: string;
}

// Deep Research
export interface DeepResearchRequest {
  query: string;
  chat_id: string;
  params: DeepResearchParams;
}

export interface DeepResearchParams {
  budget: number;
  max_iterations: number;
  scope: 'focused' | 'broad' | 'comprehensive';
  sources: {
    web_search: boolean;
    academic: boolean;
    news: boolean;
    social: boolean;
  };
  filters: {
    date_range?: {
      start: string;
      end: string;
    };
    language?: string[];
    domain_whitelist?: string[];
    domain_blacklist?: string[];
  };
}

export interface DeepResearchResponse {
  task_id: string;
  status: TaskStatus;
  estimated_duration_s: number;
  stream_url: string;
}

export interface TaskStatus {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number; // 0-100
  current_step: string;
  total_steps: number;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  error?: string;
  result?: DeepResearchResult;
}

export interface DeepResearchResult {
  summary: string;
  key_findings: string[];
  sources: ResearchSource[];
  evidence: Evidence[];
  confidence_score: number;
  methodology: string[];
  artifacts: {
    report_url: string;
    sources_bib_url: string;
    raw_data_url: string;
  };
  metrics: ResearchMetrics;
}

export interface ResearchSource {
  id: string;
  url: string;
  title: string;
  excerpt: string;
  relevance_score: number;
  credibility_score: number;
  publication_date?: string;
  author?: string;
  domain: string;
  type: 'web' | 'academic' | 'news' | 'social' | 'other';
}

export interface Evidence {
  id: string;
  claim: string;
  support_level: 'strong' | 'moderate' | 'weak';
  sources: string[]; // source IDs
  confidence: number;
  quotes: string[];
}

export interface ResearchMetrics {
  total_sources_found: number;
  sources_analyzed: number;
  iterations_completed: number;
  budget_used: number;
  time_elapsed_s: number;
  tokens_used: number;
  api_calls_made: number;
}

// Streaming
export interface StreamEvent {
  type: 'token' | 'step' | 'source' | 'error' | 'complete' | 'heartbeat';
  data: any;
  timestamp: string;
  task_id?: string;
}

export interface TokenStreamEvent extends StreamEvent {
  type: 'token';
  data: {
    token: string;
    cumulative_text: string;
    position: number;
  };
}

export interface StepStreamEvent extends StreamEvent {
  type: 'step';
  data: {
    step: string;
    description: string;
    progress: number;
    eta_s?: number;
  };
}

export interface SourceStreamEvent extends StreamEvent {
  type: 'source';
  data: ResearchSource;
}

export interface ErrorStreamEvent extends StreamEvent {
  type: 'error';
  data: {
    error: string;
    code: string;
    recoverable: boolean;
  };
}

export interface CompleteStreamEvent extends StreamEvent {
  type: 'complete';
  data: DeepResearchResult;
}

// Models
export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  description: string;
  capabilities: {
    chat: boolean;
    completion: boolean;
    function_calling: boolean;
    vision: boolean;
  };
  limits: {
    max_tokens: number;
    context_window: number;
    max_output_tokens: number;
  };
  pricing: {
    input_cost_per_token: number;
    output_cost_per_token: number;
    currency: string;
  };
  status: 'available' | 'limited' | 'deprecated';
}

// Reports
export interface ReportRequest {
  task_id: string;
  format: 'markdown' | 'html' | 'pdf';
  options?: {
    include_sources: boolean;
    include_raw_data: boolean;
    include_metadata: boolean;
    template?: string;
  };
}

export interface ReportResponse {
  download_url: string;
  expires_at: string;
  format: string;
  size_bytes: number;
  checksum: string;
}

// History
export interface HistoryRequest {
  chat_id?: string;
  user_id?: string;
  limit?: number;
  offset?: number;
  date_from?: string;
  date_to?: string;
  include_messages?: boolean;
}

export interface HistoryResponse {
  chats: ChatSession[];
  total: number;
  messages?: ChatMessage[];
}