export type ToolCapability =
  | "documents"
  | "compliance"
  | "analytics"
  | "visualization"
  | "chat-response"
  | string

export interface ToolLimits {
  timeout_ms: number
  max_payload_kb: number
  max_attachment_mb: number
}

export interface ToolSpec {
  name: string
  version: string
  description: string
  capabilities: ToolCapability[]
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  limits: ToolLimits
  owner: string
}

export interface ToolInvokeRequest<TPayload = Record<string, unknown>> {
  tool: string
  version?: string
  payload: TPayload
}

export interface ToolError {
  code: string
  message: string
  retryable: boolean
  details?: Record<string, unknown>
}

export interface ToolInvokeResponse<TOutput = Record<string, unknown>> {
  tool: string
  version: string
  ok: boolean
  output?: TOutput
  error?: ToolError
  latency_ms: number
  request_id: string
  trace_id?: string | null
  metadata?: Record<string, unknown>
}

export interface ToolGate {
  tool: string
  role?: string
  enabled: boolean
}

export type FeatureFlagMap = Record<string, boolean>
