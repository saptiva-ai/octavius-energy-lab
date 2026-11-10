/**
 * Zod validation schemas for API requests and responses
 */

import { z } from 'zod';

// Common schemas
const IdSchema = z.string().uuid();
const TimestampSchema = z.string().datetime();
const PaginationSchema = z.object({
  page: z.number().min(1).default(1),
  limit: z.number().min(1).max(100).default(20),
});

// Auth schemas
export const AuthRequestSchema = z.object({
  username: z.string().min(1).max(255),
  password: z.string().min(8).max(255),
});

export const TokenRefreshSchema = z.object({
  refresh_token: z.string(),
});

// User schemas
export const UserPreferencesSchema = z.object({
  theme: z.enum(['light', 'dark', 'auto']).default('auto'),
  language: z.string().min(2).max(5).default('en'),
  default_model: z.string().default('SAPTIVA_CORTEX'),
  chat_settings: z.object({
    stream_enabled: z.boolean().default(true),
    auto_scroll: z.boolean().default(true),
    show_timestamps: z.boolean().default(false),
  }),
});

export const UserUpdateSchema = z.object({
  email: z.string().email().optional(),
  preferences: UserPreferencesSchema.optional(),
});

// Chat schemas
export const ChatMessageSchema = z.object({
  role: z.enum(['user', 'assistant', 'system']),
  content: z.string().min(1).max(10000),
  metadata: z.object({
    model: z.string().optional(),
    tokens: z.number().optional(),
    latency_ms: z.number().optional(),
    task_id: z.string().optional(),
  }).optional(),
});

export const ChatRequestSchema = z.object({
  message: ChatMessageSchema,
  chat_id: z.string().uuid().optional(),
  model: z.string().default('SAPTIVA_CORTEX'),
  stream: z.boolean().default(true),
  tools_enabled: z.object({
    web_search: z.boolean().default(false),
    deep_research: z.boolean().default(false),
  }).optional(),
});

export const ChatSettingsSchema = z.object({
  model: z.string(),
  temperature: z.number().min(0).max(2).default(0.7),
  max_tokens: z.number().min(1).max(8192).default(1024),
  tools_enabled: z.object({
    web_search: z.boolean().default(false),
    deep_research: z.boolean().default(false),
  }),
  research_params: z.object({
    budget: z.number().min(1).max(100).default(20),
    max_iterations: z.number().min(1).max(10).default(5),
    scope: z.enum(['focused', 'broad', 'comprehensive']).default('focused'),
  }).optional(),
});

// Deep Research schemas
export const DeepResearchParamsSchema = z.object({
  budget: z.number().min(1).max(100).default(20),
  max_iterations: z.number().min(1).max(10).default(5),
  scope: z.enum(['focused', 'broad', 'comprehensive']).default('focused'),
  sources: z.object({
    web_search: z.boolean().default(true),
    academic: z.boolean().default(false),
    news: z.boolean().default(true),
    social: z.boolean().default(false),
  }).default({}),
  filters: z.object({
    date_range: z.object({
      start: z.string().datetime(),
      end: z.string().datetime(),
    }).optional(),
    language: z.array(z.string()).optional(),
    domain_whitelist: z.array(z.string().url()).optional(),
    domain_blacklist: z.array(z.string().url()).optional(),
  }).optional(),
});

export const DeepResearchRequestSchema = z.object({
  query: z.string().min(10).max(1000),
  chat_id: z.string().uuid(),
  params: DeepResearchParamsSchema.default({}),
});

// Streaming schemas
export const StreamEventSchema = z.object({
  type: z.enum(['token', 'step', 'source', 'error', 'complete', 'heartbeat']),
  data: z.any(),
  timestamp: TimestampSchema,
  task_id: z.string().optional(),
});

// Report schemas
export const ReportRequestSchema = z.object({
  task_id: z.string().uuid(),
  format: z.enum(['markdown', 'html', 'pdf']).default('markdown'),
  options: z.object({
    include_sources: z.boolean().default(true),
    include_raw_data: z.boolean().default(false),
    include_metadata: z.boolean().default(true),
    template: z.string().optional(),
  }).optional(),
});

// History schemas
export const HistoryRequestSchema = z.object({
  chat_id: z.string().uuid().optional(),
  user_id: z.string().uuid().optional(),
  limit: z.number().min(1).max(100).default(20),
  offset: z.number().min(0).default(0),
  date_from: z.string().datetime().optional(),
  date_to: z.string().datetime().optional(),
  include_messages: z.boolean().default(false),
});

// API Response schemas
export const ApiResponseSchema = z.object({
  success: z.boolean(),
  data: z.any().optional(),
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.any()).optional(),
    trace_id: z.string().optional(),
  }).optional(),
  meta: z.object({
    timestamp: TimestampSchema,
    request_id: z.string(),
    version: z.string(),
  }).optional(),
});

export const PaginatedResponseSchema = ApiResponseSchema.extend({
  pagination: z.object({
    page: z.number().min(1),
    limit: z.number().min(1),
    total: z.number().min(0),
    pages: z.number().min(0),
  }),
});

// Health check schema
export const HealthStatusSchema = z.object({
  status: z.enum(['healthy', 'degraded', 'unhealthy']),
  timestamp: TimestampSchema,
  version: z.string(),
  services: z.object({
    database: z.object({
      status: z.enum(['up', 'down', 'degraded']),
      latency_ms: z.number().optional(),
      error: z.string().optional(),
    }),
    redis: z.object({
      status: z.enum(['up', 'down', 'degraded']),
      latency_ms: z.number().optional(),
      error: z.string().optional(),
    }),
    aletheia: z.object({
      status: z.enum(['up', 'down', 'degraded']),
      latency_ms: z.number().optional(),
      error: z.string().optional(),
    }),
  }),
  uptime: z.number().min(0),
});

// Model info schema
export const ModelInfoSchema = z.object({
  id: z.string(),
  name: z.string(),
  provider: z.string(),
  description: z.string(),
  capabilities: z.object({
    chat: z.boolean(),
    completion: z.boolean(),
    function_calling: z.boolean(),
    vision: z.boolean(),
  }),
  limits: z.object({
    max_tokens: z.number(),
    context_window: z.number(),
    max_output_tokens: z.number(),
  }),
  pricing: z.object({
    input_cost_per_token: z.number(),
    output_cost_per_token: z.number(),
    currency: z.string(),
  }),
  status: z.enum(['available', 'limited', 'deprecated']),
});

// Export type inference helpers
export type AuthRequest = z.infer<typeof AuthRequestSchema>;
export type TokenRefresh = z.infer<typeof TokenRefreshSchema>;
export type UserPreferences = z.infer<typeof UserPreferencesSchema>;
export type UserUpdate = z.infer<typeof UserUpdateSchema>;
export type ChatMessage = z.infer<typeof ChatMessageSchema>;
export type ChatRequest = z.infer<typeof ChatRequestSchema>;
export type ChatSettings = z.infer<typeof ChatSettingsSchema>;
export type DeepResearchParams = z.infer<typeof DeepResearchParamsSchema>;
export type DeepResearchRequest = z.infer<typeof DeepResearchRequestSchema>;
export type StreamEvent = z.infer<typeof StreamEventSchema>;
export type ReportRequest = z.infer<typeof ReportRequestSchema>;
export type HistoryRequest = z.infer<typeof HistoryRequestSchema>;
export type ApiResponse = z.infer<typeof ApiResponseSchema>;
export type PaginatedResponse = z.infer<typeof PaginatedResponseSchema>;
export type HealthStatus = z.infer<typeof HealthStatusSchema>;
export type ModelInfo = z.infer<typeof ModelInfoSchema>;