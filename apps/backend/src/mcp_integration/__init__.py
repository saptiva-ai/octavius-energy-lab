"""
MCP (Model Context Protocol) Package.

Provides standardized tool invocation layer for extensible capabilities:
- Tool registry and discovery
- Standardized invocation protocol
- Observability and metrics
- Error handling and validation

Usage:
    from mcp import ToolRegistry
    from mcp.tools import AuditFileTool, ExcelAnalyzerTool

    registry = ToolRegistry()
    registry.register(AuditFileTool())
    registry.register(ExcelAnalyzerTool())

    response = await registry.invoke(ToolInvokeRequest(
        tool="audit_file",
        payload={"doc_id": "doc_123"}
    ))
"""

from .protocol import (
    ToolCapability,
    ToolCategory,
    ToolError,
    ToolInvokeRequest,
    ToolInvokeResponse,
    ToolMetrics,
    ToolSpec,
)
from .registry import ToolRegistry
from .tool import Tool

__all__ = [
    "ToolCategory",
    "ToolCapability",
    "ToolSpec",
    "ToolInvokeRequest",
    "ToolInvokeResponse",
    "ToolError",
    "ToolMetrics",
    "Tool",
    "ToolRegistry",
    "get_mcp_adapter",
]

__version__ = "1.0.0"


# Singleton accessor for MCP adapter (Phase 2 MCP integration)
_mcp_adapter = None


def get_mcp_adapter():
    """
    Get the MCP FastAPI adapter instance.

    This is used for internal tool invocation (not via HTTP).
    The adapter is stored in app.state during application startup.

    Returns:
        MCPFastAPIAdapter instance

    Raises:
        RuntimeError: If adapter has not been initialized
    """
    global _mcp_adapter

    # Try to get from app.state if we have a request context
    try:
        from starlette_context import context

        request = context.get("request", None)
        if request and hasattr(request.app.state, "mcp_adapter"):
            return request.app.state.mcp_adapter
    except Exception:
        pass

    # Fallback: use cached adapter
    if _mcp_adapter:
        return _mcp_adapter

    # Last resort: try to import from main.app
    try:
        from ..main import app

        if hasattr(app.state, "mcp_adapter"):
            _mcp_adapter = app.state.mcp_adapter
            return _mcp_adapter
    except Exception:
        pass

    raise RuntimeError(
        "MCP adapter not initialized. "
        "Ensure application has started and adapter is stored in app.state"
    )
