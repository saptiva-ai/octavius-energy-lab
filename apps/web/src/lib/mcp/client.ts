/**
 * MCP Client - Frontend SDK for Model Context Protocol
 *
 * Provides:
 * - listTools(): Discover available tools
 * - getTool(): Get tool specification
 * - invokeTool(): Execute a tool
 */

import { apiClient } from "../api-client";
import { logDebug, logError, logInfo } from "../logger";
import type {
  ToolSpec,
  ToolInvokeRequest,
  ToolInvokeResponse,
  AuditFileResult,
  ExcelAnalyzerResult,
  VizToolResult,
  TaskCreateRequest,
  TaskCreateResponse,
  TaskStatusResponse,
  TaskCancelResponse,
  TaskListResponse,
  PollOptions,
  TaskStatus,
  ErrorCode,
} from "./types";

export class MCPClient {
  private baseUrl = "/api/mcp";

  /**
   * List all available MCP tools.
   *
   * @param category - Optional category filter
   * @param search - Optional search query
   * @returns List of tool specifications
   */
  async listTools(category?: string, search?: string): Promise<ToolSpec[]> {
    try {
      logDebug("[MCP] Listing tools", { category, search });

      const params = new URLSearchParams();
      if (category) params.append("category", category);
      if (search) params.append("search", search);

      const url = `${this.baseUrl}/tools${params.toString() ? `?${params}` : ""}`;
      const response = await apiClient.get<ToolSpec[]>(url);

      logInfo("[MCP] Tools listed", {
        count: response.data.length,
        category,
        search,
      });

      return response.data;
    } catch (error) {
      logError("[MCP] Failed to list tools", { error });
      throw new Error("Failed to list MCP tools");
    }
  }

  /**
   * Get tool specification by name.
   *
   * @param toolName - Tool name
   * @param version - Optional version (defaults to latest)
   * @returns Tool specification
   */
  async getTool(toolName: string, version?: string): Promise<ToolSpec> {
    try {
      logDebug("[MCP] Getting tool spec", { toolName, version });

      const params = version ? `?version=${version}` : "";
      const url = `${this.baseUrl}/tools/${toolName}${params}`;
      const response = await apiClient.get<ToolSpec>(url);

      logInfo("[MCP] Tool spec retrieved", { toolName, version });

      return response.data;
    } catch (error) {
      logError("[MCP] Failed to get tool spec", { toolName, error });
      throw new Error(`Failed to get tool '${toolName}'`);
    }
  }

  /**
   * Invoke an MCP tool.
   *
   * @param request - Tool invocation request
   * @param signal - Optional AbortSignal for cancellation
   * @returns Tool invocation response
   */
  async invokeTool<T = any>(
    request: ToolInvokeRequest,
    signal?: AbortSignal,
  ): Promise<ToolInvokeResponse<T>> {
    try {
      logInfo("[MCP] Invoking tool", {
        tool: request.tool,
        version: request.version,
        idempotency_key: request.idempotency_key,
      });

      // Check if already aborted
      if (signal?.aborted) {
        throw new Error("Request aborted before invocation");
      }

      const response = await apiClient.post<ToolInvokeResponse<T>>(
        `${this.baseUrl}/invoke`,
        request,
        { signal }, // Pass signal to axios
      );

      if (response.data.success) {
        logInfo("[MCP] Tool invocation succeeded", {
          tool: request.tool,
          duration_ms: response.data.duration_ms,
          cached: response.data.cached,
        });
      } else {
        logError("[MCP] Tool invocation failed", {
          tool: request.tool,
          error: response.data.error,
        });
      }

      return response.data;
    } catch (error) {
      logError("[MCP] Tool invocation error", { tool: request.tool, error });

      // Handle abort error
      if (signal?.aborted || (error as any).name === "AbortError") {
        throw new Error(`Tool invocation cancelled: ${request.tool}`);
      }

      throw new Error(`Tool invocation failed: ${error}`);
    }
  }

  /**
   * Check MCP health status with optional detailed information.
   *
   * @param options - Optional flags for additional information
   * @returns Health status with optional details
   */
  async healthCheck(options?: {
    includeTools?: boolean;
    includeMetrics?: boolean;
    includeTasks?: boolean;
  }): Promise<{
    status: string;
    mcp_version: string;
    fastmcp_version: string;
    timestamp: string;
    tools_registered: number;
    capabilities: {
      task_management: boolean;
      versioning: boolean;
      security: boolean;
      metrics: boolean;
      schema_discovery: boolean;
      cancellation: boolean;
    };
    tools?: Array<{
      name: string;
      version: string;
      available_versions: string[];
      description: string;
    }>;
    metrics?: any;
    tasks?: {
      pending: number;
      running: number;
      queue_healthy: boolean;
    };
  }> {
    try {
      const params = new URLSearchParams();
      if (options?.includeTools) params.append("include_tools", "true");
      if (options?.includeMetrics) params.append("include_metrics", "true");
      if (options?.includeTasks) params.append("include_tasks", "true");

      const url = `${this.baseUrl}/health${params.toString() ? `?${params}` : ""}`;
      const response = await apiClient.get(url);

      return response.data;
    } catch (error) {
      logError("[MCP] Health check failed", { error });
      throw new Error("MCP health check failed");
    }
  }

  /**
   * Discover available MCP tools with powerful filtering.
   *
   * @param filters - Optional filters for tool discovery
   * @returns Filtered list of available tools
   */
  async discoverTools(filters?: {
    category?: string;
    capability?: string;
    tag?: string;
    search?: string;
    includeSchema?: boolean;
    includeVersions?: boolean;
  }): Promise<{
    total: number;
    filtered: number;
    tools: ToolSpec[];
    filters_applied: {
      category?: string;
      capability?: string;
      tag?: string;
      search?: string;
    };
  }> {
    try {
      logDebug("[MCP] Discovering tools", { filters });

      const params = new URLSearchParams();
      if (filters?.category) params.append("category", filters.category);
      if (filters?.capability) params.append("capability", filters.capability);
      if (filters?.tag) params.append("tag", filters.tag);
      if (filters?.search) params.append("search", filters.search);
      if (filters?.includeSchema !== undefined)
        params.append("include_schema", filters.includeSchema.toString());
      if (filters?.includeVersions !== undefined)
        params.append("include_versions", filters.includeVersions.toString());

      const url = `${this.baseUrl}/discover${params.toString() ? `?${params}` : ""}`;
      const response = await apiClient.get(url);

      logInfo("[MCP] Tool discovery completed", {
        total: response.data.total,
        filtered: response.data.filtered,
      });

      return response.data;
    } catch (error) {
      logError("[MCP] Tool discovery failed", { error });
      throw new Error("Tool discovery failed");
    }
  }

  // ========================================================================
  // Task Management (202 Accepted Pattern)
  // ========================================================================

  /**
   * Create a background task for long-running tool execution.
   *
   * Returns immediately with a task_id. Use pollTask() to wait for completion.
   *
   * @param request - Task creation request
   * @returns Task creation response with task_id
   */
  async createTask(request: TaskCreateRequest): Promise<TaskCreateResponse> {
    try {
      logInfo("[MCP] Creating task", {
        tool: request.tool,
        version: request.version,
        priority: request.priority,
      });

      const response = await apiClient.post<TaskCreateResponse>(
        `${this.baseUrl}/tasks`,
        request,
      );

      logInfo("[MCP] Task created", {
        task_id: response.data.task_id,
        tool: request.tool,
        estimated_duration_ms: response.data.estimated_duration_ms,
      });

      return response.data;
    } catch (error) {
      logError("[MCP] Task creation failed", { tool: request.tool, error });
      throw new Error(`Task creation failed: ${error}`);
    }
  }

  /**
   * Get task status.
   *
   * @param taskId - Task ID
   * @returns Task status with progress and result
   */
  async getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
    try {
      const response = await apiClient.get<TaskStatusResponse>(
        `${this.baseUrl}/tasks/${taskId}`,
      );
      return response.data;
    } catch (error) {
      logError("[MCP] Get task status failed", { task_id: taskId, error });
      throw new Error(`Get task status failed: ${error}`);
    }
  }

  /**
   * Cancel a running task.
   *
   * Sends cancellation request. The task will be marked for cancellation,
   * but actual cancellation depends on the tool checking the cancellation flag.
   *
   * @param taskId - Task ID
   * @returns Cancellation response
   */
  async cancelTask(taskId: string): Promise<TaskCancelResponse> {
    try {
      logInfo("[MCP] Cancelling task", { task_id: taskId });

      const response = await apiClient.delete<TaskCancelResponse>(
        `${this.baseUrl}/tasks/${taskId}`,
      );

      logInfo("[MCP] Task cancellation requested", {
        task_id: taskId,
        status: response.data.status,
      });

      return response.data;
    } catch (error) {
      logError("[MCP] Task cancellation failed", { task_id: taskId, error });
      throw new Error(`Task cancellation failed: ${error}`);
    }
  }

  /**
   * List tasks with optional filters.
   *
   * @param filters - Optional filters (status, tool)
   * @returns List of task summaries
   */
  async listTasks(filters?: {
    status?: TaskStatus;
    tool?: string;
  }): Promise<TaskListResponse[]> {
    try {
      const params = new URLSearchParams();
      if (filters?.status) params.append("status", filters.status);
      if (filters?.tool) params.append("tool", filters.tool);

      const url = `${this.baseUrl}/tasks${params.toString() ? `?${params}` : ""}`;
      const response = await apiClient.get<TaskListResponse[]>(url);

      return response.data;
    } catch (error) {
      logError("[MCP] List tasks failed", { error });
      throw new Error("List tasks failed");
    }
  }

  /**
   * Poll a task until completion or timeout.
   *
   * Automatically handles:
   * - Polling with configurable interval
   * - Progress callbacks
   * - Timeout handling
   * - Cancellation via AbortSignal
   *
   * @param taskId - Task ID to poll
   * @param options - Poll options (interval, timeout, onProgress, signal)
   * @returns Final task result
   */
  async pollTask<T = any>(
    taskId: string,
    options: PollOptions = {},
  ): Promise<T> {
    const {
      intervalMs = 1000,
      maxAttempts = 300,
      timeoutMs = 300000,
      onProgress,
      signal,
    } = options;

    logInfo("[MCP] Starting task poll", {
      task_id: taskId,
      interval_ms: intervalMs,
      max_attempts: maxAttempts,
    });

    const startTime = Date.now();
    let attempts = 0;

    while (true) {
      // Check abort signal
      if (signal?.aborted) {
        logInfo("[MCP] Task poll cancelled by abort signal", {
          task_id: taskId,
        });
        await this.cancelTask(taskId).catch(() => {
          /* ignore cancel errors */
        });
        throw new Error(`Task poll cancelled: ${taskId}`);
      }

      // Check timeout
      if (Date.now() - startTime > timeoutMs) {
        logError("[MCP] Task poll timeout", {
          task_id: taskId,
          elapsed_ms: Date.now() - startTime,
        });
        throw new Error(`Task poll timeout after ${timeoutMs}ms`);
      }

      // Check max attempts
      if (attempts >= maxAttempts) {
        logError("[MCP] Task poll max attempts reached", {
          task_id: taskId,
          attempts,
        });
        throw new Error(`Task poll max attempts reached: ${maxAttempts}`);
      }

      attempts++;

      // Poll task status
      const status = await this.getTaskStatus(taskId);

      // Fire progress callback
      if (onProgress) {
        try {
          onProgress(status);
        } catch (error) {
          logError("[MCP] Progress callback error", { error });
        }
      }

      // Check terminal states
      if (status.status === "completed") {
        logInfo("[MCP] Task completed", {
          task_id: taskId,
          attempts,
          elapsed_ms: Date.now() - startTime,
        });
        return status.result as T;
      }

      if (status.status === "failed") {
        logError("[MCP] Task failed", {
          task_id: taskId,
          error: status.error,
        });
        throw new Error(
          `Task failed: ${status.error?.message || "Unknown error"}`,
        );
      }

      if (status.status === "cancelled") {
        logInfo("[MCP] Task was cancelled", { task_id: taskId });
        throw new Error(`Task cancelled: ${taskId}`);
      }

      // Sleep before next poll
      await this.sleep(intervalMs);
    }
  }

  /**
   * Execute a tool as a background task and wait for completion.
   *
   * Convenience method that combines createTask() + pollTask().
   *
   * @param request - Tool invocation request
   * @param options - Poll options
   * @returns Tool result
   */
  async invokeToolAsync<T = any>(
    request: ToolInvokeRequest & { priority?: "low" | "normal" | "high" },
    options: PollOptions = {},
  ): Promise<T> {
    // Create task
    const taskResponse = await this.createTask({
      tool: request.tool,
      version: request.version,
      payload: request.payload,
      priority: request.priority || "normal",
    });

    // Poll until completion
    return this.pollTask<T>(taskResponse.task_id, options);
  }

  /**
   * Sleep for a given number of milliseconds.
   *
   * @param ms - Milliseconds to sleep
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // ========================================================================
  // Typed convenience methods for specific tools
  // ========================================================================

  /**
   * Audit a file using COPILOTO-AUDIT compliance validation.
   *
   * @param docId - Document ID to validate
   * @param options - Validation options
   * @returns Audit report with findings
   */
  async auditFile(
    docId: string,
    options: {
      policyId?: string;
      enableDisclaimer?: boolean;
      enableFormat?: boolean;
      enableLogo?: boolean;
    } = {},
  ): Promise<ToolInvokeResponse<AuditFileResult>> {
    return this.invokeTool<AuditFileResult>({
      tool: "audit_file",
      payload: {
        doc_id: docId,
        policy_id: options.policyId || "auto",
        enable_disclaimer: options.enableDisclaimer ?? true,
        enable_format: options.enableFormat ?? true,
        enable_logo: options.enableLogo ?? true,
      },
    });
  }

  /**
   * Analyze an Excel file.
   *
   * @param docId - Document ID (Excel file)
   * @param options - Analysis options
   * @returns Analysis results with stats, aggregates, validation
   */
  async analyzeExcel(
    docId: string,
    options: {
      sheetName?: string;
      operations?: ("stats" | "aggregate" | "validate" | "preview")[];
      aggregateColumns?: string[];
    } = {},
  ): Promise<ToolInvokeResponse<ExcelAnalyzerResult>> {
    return this.invokeTool<ExcelAnalyzerResult>({
      tool: "excel_analyzer",
      payload: {
        doc_id: docId,
        sheet_name: options.sheetName,
        operations: options.operations || ["stats", "preview"],
        aggregate_columns: options.aggregateColumns || [],
      },
    });
  }

  /**
   * Generate a visualization spec.
   *
   * @param chartType - Type of chart (bar, line, pie, scatter, etc.)
   * @param dataSource - Data source configuration
   * @param options - Chart options
   * @returns Visualization spec (Plotly/ECharts)
   */
  async generateViz(
    chartType: "bar" | "line" | "pie" | "scatter" | "heatmap" | "histogram",
    dataSource:
      | { type: "inline"; data: Record<string, any>[] }
      | { type: "excel"; docId: string; sheetName?: string }
      | { type: "sql"; query: string },
    options: {
      xColumn?: string;
      yColumn?: string;
      title?: string;
      library?: "plotly" | "echarts";
    } = {},
  ): Promise<ToolInvokeResponse<VizToolResult>> {
    const payload: any = {
      chart_type: chartType,
      data_source:
        dataSource.type === "inline"
          ? { type: "inline", data: dataSource.data }
          : dataSource.type === "excel"
            ? {
                type: "excel",
                doc_id: dataSource.docId,
                sheet_name: dataSource.sheetName,
              }
            : { type: "sql", sql_query: dataSource.query },
      x_column: options.xColumn,
      y_column: options.yColumn,
      title: options.title,
      library: options.library || "plotly",
    };

    return this.invokeTool<VizToolResult>({
      tool: "viz_tool",
      payload,
    });
  }
}

// Singleton instance
export const mcpClient = new MCPClient();

// Named exports for convenience

// Tool discovery and invocation
export const listTools = mcpClient.listTools.bind(mcpClient);
export const getTool = mcpClient.getTool.bind(mcpClient);
export const invokeTool = mcpClient.invokeTool.bind(mcpClient);
export const healthCheck = mcpClient.healthCheck.bind(mcpClient);
export const discoverTools = mcpClient.discoverTools.bind(mcpClient);

// Task management (202 Accepted pattern)
export const createTask = mcpClient.createTask.bind(mcpClient);
export const getTaskStatus = mcpClient.getTaskStatus.bind(mcpClient);
export const cancelTask = mcpClient.cancelTask.bind(mcpClient);
export const listTasks = mcpClient.listTasks.bind(mcpClient);
export const pollTask = mcpClient.pollTask.bind(mcpClient);
export const invokeToolAsync = mcpClient.invokeToolAsync.bind(mcpClient);

// Typed convenience methods
export const auditFile = mcpClient.auditFile.bind(mcpClient);
export const analyzeExcel = mcpClient.analyzeExcel.bind(mcpClient);
export const generateViz = mcpClient.generateViz.bind(mcpClient);
