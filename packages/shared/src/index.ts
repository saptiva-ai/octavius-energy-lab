/**
 * Shared package exports for Copilot OS
 */

// Types (main API types)
export type {
  ApiResponse,
  ApiError,
  PaginatedResponse,
  HealthStatus,
  ServiceStatus,
  AuthRequest,
  AuthResponse,
  User,
  UserPreferences,
  ChatMessage,
  ChatSession,
  ChatSettings,
  ToolCall,
  DeepResearchRequest,
  DeepResearchParams,
  DeepResearchResponse,
  TaskStatus,
  DeepResearchResult,
  ResearchSource,
  Evidence,
  ResearchMetrics,
  StreamEvent,
  TokenStreamEvent,
  StepStreamEvent,
  SourceStreamEvent,
  ErrorStreamEvent,
  CompleteStreamEvent,
  ModelInfo,
  ReportRequest,
  ReportResponse,
  HistoryRequest,
  HistoryResponse,
} from './types/api';

// Schemas and validation (Zod schemas and inferred types)
export {
  AuthRequestSchema,
  TokenRefreshSchema,
  UserPreferencesSchema,
  UserUpdateSchema,
  ChatMessageSchema,
  ChatRequestSchema,
  ChatSettingsSchema,
  DeepResearchParamsSchema,
  DeepResearchRequestSchema,
  StreamEventSchema,
  ReportRequestSchema,
  HistoryRequestSchema,
  ApiResponseSchema,
  PaginatedResponseSchema,
  HealthStatusSchema,
  ModelInfoSchema,
} from './schemas/validation';

// Export inferred types from schemas (to avoid conflicts)
export type {
  AuthRequest as ZodAuthRequest,
  TokenRefresh,
  UserPreferences as ZodUserPreferences,
  UserUpdate,
  ChatMessage as ZodChatMessage,
  ChatRequest,
  ChatSettings as ZodChatSettings,
  DeepResearchParams as ZodDeepResearchParams,
  DeepResearchRequest as ZodDeepResearchRequest,
  StreamEvent as ZodStreamEvent,
  ReportRequest as ZodReportRequest,
  HistoryRequest as ZodHistoryRequest,
  ApiResponse as ZodApiResponse,
  PaginatedResponse as ZodPaginatedResponse,
  HealthStatus as ZodHealthStatus,
  ModelInfo as ZodModelInfo,
} from './schemas/validation';

// Constants
export * from './constants/index';

// Re-export commonly used Zod types
export { z } from 'zod';