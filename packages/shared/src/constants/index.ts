/**
 * Shared constants for Copilot OS
 */

// API Endpoints
export const API_ENDPOINTS = {
  AUTH: {
    LOGIN: '/api/auth/login',
    REFRESH: '/api/auth/refresh',
    LOGOUT: '/api/auth/logout',
    ME: '/api/auth/me',
  },
  CHAT: {
    SEND: '/api/chat',
    SESSIONS: '/api/chat/sessions',
    SESSION: (id: string) => `/api/chat/sessions/${id}`,
    MESSAGES: (chatId: string) => `/api/chat/sessions/${chatId}/messages`,
  },
  RESEARCH: {
    START: '/api/deep-research',
    STATUS: (taskId: string) => `/api/deep-research/${taskId}/status`,
    CANCEL: (taskId: string) => `/api/deep-research/${taskId}/cancel`,
  },
  STREAM: {
    CHAT: (chatId: string) => `/api/stream/chat/${chatId}`,
    TASK: (taskId: string) => `/api/stream/task/${taskId}`,
  },
  REPORTS: {
    DOWNLOAD: (taskId: string) => `/api/reports/${taskId}/download`,
    METADATA: (taskId: string) => `/api/reports/${taskId}/metadata`,
  },
  HISTORY: {
    LIST: '/api/history',
    CHAT: (chatId: string) => `/api/history/${chatId}`,
  },
  HEALTH: '/api/health',
  MODELS: '/api/models',
} as const;

// Model IDs - Aligned with SAPTIVA API
export const MODELS = {
  SAPTIVA: {
    CORTEX: 'SAPTIVA_CORTEX',
    TURBO: 'SAPTIVA_TURBO',
    GUARD: 'SAPTIVA_GUARD',
    OCR: 'SAPTIVA_OCR',
  },
} as const;

// Model configurations
export const MODEL_CONFIGS = {
  [MODELS.SAPTIVA.CORTEX]: {
    name: 'Saptiva Cortex',
    description: 'Modelo principal para conversaciones generales y razonamiento complejo',
    maxTokens: 8192,
    contextWindow: 32768,
    supportsTools: true,
    supportsStreaming: true,
  },
  [MODELS.SAPTIVA.TURBO]: {
    name: 'Saptiva Turbo',
    description: 'Modelo optimizado para respuestas rápidas y tareas simples',
    maxTokens: 4096,
    contextWindow: 16384,
    supportsTools: true,
    supportsStreaming: true,
  },
  [MODELS.SAPTIVA.GUARD]: {
    name: 'Saptiva Guard',
    description: 'Modelo especializado en moderación de contenido y seguridad',
    maxTokens: 2048,
    contextWindow: 8192,
    supportsTools: false,
    supportsStreaming: false,
  },
  [MODELS.SAPTIVA.OCR]: {
    name: 'Saptiva OCR',
    description: 'Modelo para reconocimiento óptico de caracteres y análisis de imágenes',
    maxTokens: 2048,
    contextWindow: 8192,
    supportsTools: false,
    supportsStreaming: false,
  },
} as const;

// Deep Research
export const RESEARCH_SCOPES = {
  FOCUSED: 'focused',
  BROAD: 'broad',
  COMPREHENSIVE: 'comprehensive',
} as const;

export const RESEARCH_SOURCE_TYPES = {
  WEB: 'web',
  ACADEMIC: 'academic',
  NEWS: 'news',
  SOCIAL: 'social',
  OTHER: 'other',
} as const;

// Task statuses
export const TASK_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const;

// Stream event types
export const STREAM_EVENT_TYPES = {
  TOKEN: 'token',
  STEP: 'step',
  SOURCE: 'source',
  ERROR: 'error',
  COMPLETE: 'complete',
  HEARTBEAT: 'heartbeat',
} as const;

// Message roles
export const MESSAGE_ROLES = {
  USER: 'user',
  ASSISTANT: 'assistant',
  SYSTEM: 'system',
} as const;

// Message status
export const MESSAGE_STATUS = {
  SENDING: 'sending',
  DELIVERED: 'delivered',
  ERROR: 'error',
  STREAMING: 'streaming',
} as const;

// Error codes
export const ERROR_CODES = {
  // Authentication
  INVALID_CREDENTIALS: 'INVALID_CREDENTIALS',
  TOKEN_EXPIRED: 'TOKEN_EXPIRED',
  TOKEN_INVALID: 'TOKEN_INVALID',
  UNAUTHORIZED: 'UNAUTHORIZED',
  
  // Validation
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  INVALID_INPUT: 'INVALID_INPUT',
  MISSING_FIELD: 'MISSING_FIELD',
  
  // Rate limiting
  RATE_LIMIT_EXCEEDED: 'RATE_LIMIT_EXCEEDED',
  TOO_MANY_REQUESTS: 'TOO_MANY_REQUESTS',
  
  // External services
  ALETHEIA_UNAVAILABLE: 'ALETHEIA_UNAVAILABLE',
  ALETHEIA_TIMEOUT: 'ALETHEIA_TIMEOUT',
  MODEL_UNAVAILABLE: 'MODEL_UNAVAILABLE',
  
  // Resources
  RESOURCE_NOT_FOUND: 'RESOURCE_NOT_FOUND',
  CHAT_NOT_FOUND: 'CHAT_NOT_FOUND',
  TASK_NOT_FOUND: 'TASK_NOT_FOUND',
  USER_NOT_FOUND: 'USER_NOT_FOUND',
  
  // General
  INTERNAL_ERROR: 'INTERNAL_ERROR',
  SERVICE_UNAVAILABLE: 'SERVICE_UNAVAILABLE',
  NETWORK_ERROR: 'NETWORK_ERROR',
} as const;

// HTTP Status codes
export const HTTP_STATUS = {
  OK: 200,
  CREATED: 201,
  NO_CONTENT: 204,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  METHOD_NOT_ALLOWED: 405,
  CONFLICT: 409,
  UNPROCESSABLE_ENTITY: 422,
  TOO_MANY_REQUESTS: 429,
  INTERNAL_SERVER_ERROR: 500,
  SERVICE_UNAVAILABLE: 503,
  GATEWAY_TIMEOUT: 504,
} as const;

// Limits
export const LIMITS = {
  MAX_PROMPT_LENGTH: 10000,
  MAX_CHAT_TITLE_LENGTH: 100,
  MAX_CHAT_SESSIONS_PER_USER: 1000,
  MAX_MESSAGES_PER_CHAT: 10000,
  MAX_CONCURRENT_STREAMS: 10,
  MAX_FILE_SIZE_MB: 10,
  MAX_UPLOAD_FILES: 5,
  
  // Rate limiting
  DEFAULT_RATE_LIMIT: 100, // requests per minute
  BURST_RATE_LIMIT: 20, // burst size
  
  // Pagination
  DEFAULT_PAGE_SIZE: 20,
  MAX_PAGE_SIZE: 100,
  
  // Research
  MAX_RESEARCH_BUDGET: 100,
  MAX_RESEARCH_ITERATIONS: 10,
  MAX_RESEARCH_SOURCES: 1000,
} as const;

// Timeouts (in milliseconds)
export const TIMEOUTS = {
  HTTP_REQUEST: 30000, // 30 seconds
  ALETHEIA_REQUEST: 120000, // 2 minutes
  STREAM_HEARTBEAT: 30000, // 30 seconds
  SSE_RECONNECT: 5000, // 5 seconds
  AUTH_TOKEN_REFRESH: 60000, // 1 minute before expiry
  DATABASE_QUERY: 10000, // 10 seconds
  REDIS_OPERATION: 5000, // 5 seconds
} as const;

// File types
export const ALLOWED_FILE_TYPES = [
  'text/plain',
  'text/markdown',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
] as const;

export const FILE_EXTENSIONS = {
  'text/plain': ['.txt'],
  'text/markdown': ['.md', '.markdown'],
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
} as const;

// Feature flags
export const FEATURES = {
  DEEP_RESEARCH: 'deep_research',
  WEB_SEARCH: 'web_search',
  FILE_UPLOAD: 'file_upload',
  VOICE_INPUT: 'voice_input',
  EXPORT_CHAT: 'export_chat',
  CHAT_SHARING: 'chat_sharing',
  ANALYTICS: 'analytics',
} as const;

// Theme colors (for UI consistency)
export const THEME_COLORS = {
  PRIMARY: {
    50: '#f6f5ff',
    100: '#edebfe',
    200: '#ddd6fe',
    300: '#c4b5fd',
    400: '#a78bfa',
    500: '#8b5cf6',
    600: '#7c3aed',
    700: '#6d28d9',
    800: '#5b21b6',
    900: '#4c1d95',
  },
  GRAY: {
    50: '#f9fafb',
    100: '#f3f4f6',
    200: '#e5e7eb',
    300: '#d1d5db',
    400: '#9ca3af',
    500: '#6b7280',
    600: '#4b5563',
    700: '#374151',
    800: '#1f2937',
    900: '#111827',
  },
} as const;