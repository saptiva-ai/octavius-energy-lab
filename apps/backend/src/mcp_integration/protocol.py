"""
MCP Protocol - Type definitions and contracts.

Defines standardized message types for tool invocation:
- ToolSpec: Tool capability advertisement
- ToolInvokeRequest/Response: Invocation messages
- ToolError: Standardized error reporting
- ToolMetrics: Observability metrics
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolCategory(str, Enum):
    """Tool categories for discovery and organization."""

    DOCUMENT_ANALYSIS = "document_analysis"
    DATA_ANALYTICS = "data_analytics"
    VISUALIZATION = "visualization"
    RESEARCH = "research"
    COMPLIANCE = "compliance"


class ToolCapability(str, Enum):
    """Capabilities that tools can advertise."""

    SYNC = "sync"  # Synchronous execution
    ASYNC = "async"  # Asynchronous execution
    STREAMING = "streaming"  # Supports SSE streaming
    IDEMPOTENT = "idempotent"  # Safe to retry
    CACHEABLE = "cacheable"  # Results can be cached
    STATEFUL = "stateful"  # Maintains state across calls


class ToolSpec(BaseModel):
    """Tool specification - advertises tool capabilities."""

    name: str = Field(..., description="Unique tool identifier (e.g., 'audit_file')")
    version: str = Field(..., description="Semantic version (e.g., '1.0.0')")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Tool purpose and use cases")
    category: ToolCategory
    capabilities: List[ToolCapability] = Field(default_factory=list)
    input_schema: Dict[str, Any] = Field(
        ..., description="JSON Schema for input validation"
    )
    output_schema: Dict[str, Any] = Field(
        ..., description="JSON Schema for output structure"
    )
    tags: List[str] = Field(default_factory=list, description="Searchable tags")
    author: str = Field(default="OctaviOS", description="Tool author/maintainer")
    requires_auth: bool = Field(
        default=True, description="Requires user authentication"
    )
    rate_limit: Optional[Dict[str, int]] = Field(
        default=None, description="Rate limit config: {'calls_per_minute': 10}"
    )
    timeout_ms: int = Field(
        default=30000, description="Max execution time in milliseconds"
    )
    max_payload_size_kb: int = Field(
        default=1024, description="Max input payload size in KB"
    )


class ToolInvokeRequest(BaseModel):
    """Request to invoke a tool."""

    tool: str = Field(..., description="Tool name")
    version: Optional[str] = Field(
        None, description="Tool version (defaults to latest)"
    )
    payload: Dict[str, Any] = Field(..., description="Tool-specific input")
    context: Optional[Dict[str, Any]] = Field(
        default=None, description="Execution context (user_id, trace_id, etc.)"
    )
    idempotency_key: Optional[str] = Field(
        None, description="Idempotency key for retry safety"
    )


class ToolInvokeResponse(BaseModel):
    """Response from tool invocation."""

    success: bool
    tool: str
    version: str
    result: Optional[Dict[str, Any]] = None
    error: Optional["ToolError"] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    invocation_id: str = Field(..., description="Unique invocation ID for tracing")
    duration_ms: float = Field(..., description="Execution time in milliseconds")
    cached: bool = Field(default=False, description="Was result served from cache?")


class ErrorCode(str, Enum):
    """
    Standardized error codes for MCP tools.

    Taxonomy:
    - VALIDATION_ERROR: Input validation failed
    - TIMEOUT: Tool execution exceeded timeout
    - TOOL_BUSY: Tool is currently processing another request
    - BACKEND_DEP_UNAVAILABLE: Required backend service unavailable
    - RATE_LIMIT: Rate limit exceeded
    - PERMISSION_DENIED: User lacks required permissions
    - TOOL_NOT_FOUND: Requested tool doesn't exist
    - EXECUTION_ERROR: Generic execution error
    - CANCELLED: Task was cancelled by user
    """

    VALIDATION_ERROR = "VALIDATION_ERROR"
    TIMEOUT = "TIMEOUT"
    TOOL_BUSY = "TOOL_BUSY"
    BACKEND_DEP_UNAVAILABLE = "BACKEND_DEP_UNAVAILABLE"
    RATE_LIMIT = "RATE_LIMIT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    CANCELLED = "CANCELLED"


class ToolError(BaseModel):
    """Standardized tool error."""

    code: ErrorCode = Field(..., description="Standardized error code")
    message: str = Field(..., description="Technical error message for logging")
    user_message: Optional[str] = Field(
        None, description="User-friendly message (safe for display)"
    )
    details: Optional[Dict[str, Any]] = Field(
        None, description="Debug details (not for end users)"
    )
    tool_context: Optional[Dict[str, Any]] = Field(
        None, description="Tool-specific context"
    )
    retry_after_ms: Optional[int] = Field(
        None, description="Retry delay for rate limits"
    )
    trace_id: Optional[str] = Field(None, description="Request trace ID for debugging")


class ToolMetrics(BaseModel):
    """Tool execution metrics for observability."""

    tool: str
    version: str
    invocation_count: int = 0
    success_count: int = 0
    error_count: int = 0
    avg_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    last_invoked_at: Optional[datetime] = None
    cache_hit_rate: float = 0.0


# Forward reference resolution for self-referencing models
ToolInvokeResponse.model_rebuild()
