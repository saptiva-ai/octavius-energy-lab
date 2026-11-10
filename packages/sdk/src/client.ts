import type {
  FeatureFlagMap,
  ToolGate,
  ToolInvokeRequest,
  ToolInvokeResponse,
  ToolSpec,
} from "./types"

export interface MCPClientOptions {
  baseUrl?: string
  fetchFn?: typeof fetch
  getAuthToken?: () => Promise<string | null> | string | null
  defaultHeaders?: HeadersInit
}

export class MCPClient {
  private readonly baseUrl: string
  private readonly fetchFn: typeof fetch
  private readonly getAuthToken?: () => Promise<string | null> | string | null
  private readonly defaultHeaders: HeadersInit

  constructor(options: MCPClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "/api/mcp"
    this.fetchFn = options.fetchFn ?? fetch.bind(globalThis)
    this.getAuthToken = options.getAuthToken
    this.defaultHeaders = options.defaultHeaders ?? {
      "Content-Type": "application/json",
    }
  }

  async listTools(): Promise<ToolSpec[]> {
    const response = await this.request<ToolSpec[]>("/tools", {
      method: "GET",
    })
    return response ?? []
  }

  async invokeTool<TPayload extends Record<string, unknown>, TOutput = Record<string, unknown>>(
    payload: ToolInvokeRequest<TPayload>,
  ): Promise<ToolInvokeResponse<TOutput>> {
    return this.request<ToolInvokeResponse<TOutput>>("/invoke", {
      method: "POST",
      body: JSON.stringify(payload),
    })
  }

  private async request<T>(
    path: string,
    init: RequestInit,
  ): Promise<T> {
    const headers = new Headers(this.defaultHeaders)
    if (this.getAuthToken) {
      const token = await this.getAuthToken()
      if (token) {
        headers.set("Authorization", `Bearer ${token}`)
      }
    }

    const response = await this.fetchFn(`${this.baseUrl}${path}`, {
      ...init,
      headers,
    })

    if (!response.ok) {
      const detail = await safeJson(response)
      throw new Error(detail?.detail ?? `MCP request failed with ${response.status}`)
    }

    return (await response.json()) as T
  }
}

export function filterToolsByFlags(
  tools: ToolSpec[],
  flags: FeatureFlagMap | null,
  gates: ToolGate[] = [],
  userRoles: string[] = [],
): ToolSpec[] {
  return tools.filter((tool) => {
    if (flags && flags[tool.name] === false) {
      return false
    }

    const gate = gates.find((g) => g.tool === tool.name)
    if (!gate) {
      return true
    }

    if (!gate.enabled) {
      return false
    }

    if (!gate.role) {
      return true
    }

    return userRoles.includes(gate.role)
  })
}

async function safeJson(response: Response): Promise<any> {
  try {
    return await response.json()
  } catch {
    return null
  }
}
