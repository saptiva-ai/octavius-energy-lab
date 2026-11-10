"""
MCP Routes - FastAPI endpoints for tool discovery and invocation.

Provides:
- GET /mcp/tools - List available tools
- POST /mcp/invoke - Invoke a tool
- GET /mcp/tools/{tool_name} - Get tool specification
- GET /mcp/health - MCP health check
"""

from typing import Callable, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..models.user import User
from .protocol import ToolInvokeRequest, ToolInvokeResponse, ToolSpec
from .registry import ToolRegistry

logger = structlog.get_logger(__name__)


def create_mcp_router(
    registry: ToolRegistry,
    auth_dependency: Callable,
    on_invoke: Optional[Callable[[ToolInvokeResponse], None]] = None,
) -> APIRouter:
    """
    Create MCP router with dependency injection.

    Args:
        registry: ToolRegistry instance
        auth_dependency: Auth dependency (e.g., get_current_user)
        on_invoke: Optional callback after tool invocation (for telemetry)

    Returns:
        FastAPI router
    """
    router = APIRouter(prefix="/mcp", tags=["mcp"])

    @router.get("/tools", response_model=List[ToolSpec])
    async def list_tools(
        category: Optional[str] = Query(None, description="Filter by category"),
        search: Optional[str] = Query(None, description="Search query"),
        current_user: User = Depends(auth_dependency),
    ):
        """
        List available MCP tools.

        Args:
            category: Optional category filter
            search: Optional search query (matches name, description, tags)
            current_user: Authenticated user

        Returns:
            List of tool specifications
        """
        logger.info(
            "MCP tools listing requested",
            user_id=str(current_user.id),
            category=category,
            search=search,
        )

        if search:
            tools = registry.search_tools(search)
        else:
            tools = registry.list_tools(category=category)

        logger.info(
            "MCP tools listed",
            user_id=str(current_user.id),
            tool_count=len(tools),
        )

        return tools

    @router.get("/tools/{tool_name}", response_model=ToolSpec)
    async def get_tool_spec(
        tool_name: str,
        version: Optional[str] = Query(None, description="Tool version"),
        current_user: User = Depends(auth_dependency),
    ):
        """
        Get tool specification by name.

        Args:
            tool_name: Tool name
            version: Optional version (defaults to latest)
            current_user: Authenticated user

        Returns:
            Tool specification

        Raises:
            HTTPException: If tool not found
        """
        logger.info(
            "MCP tool spec requested",
            user_id=str(current_user.id),
            tool=tool_name,
            version=version,
        )

        tool = registry.get_tool(tool_name, version)

        if not tool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool '{tool_name}' not found",
            )

        return tool.get_spec()

    @router.post("/invoke", response_model=ToolInvokeResponse)
    async def invoke_tool(
        request: ToolInvokeRequest,
        current_user: User = Depends(auth_dependency),
    ):
        """
        Invoke an MCP tool.

        Args:
            request: Tool invocation request
            current_user: Authenticated user

        Returns:
            Tool invocation response (success or error)
        """
        # Inject user_id into context
        context = request.context or {}
        context["user_id"] = str(current_user.id)

        logger.info(
            "MCP tool invocation requested",
            user_id=str(current_user.id),
            tool=request.tool,
            version=request.version,
            idempotency_key=request.idempotency_key,
        )

        # Invoke tool via registry
        response = await registry.invoke(
            ToolInvokeRequest(
                tool=request.tool,
                version=request.version,
                payload=request.payload,
                context=context,
                idempotency_key=request.idempotency_key,
            )
        )

        logger.info(
            "MCP tool invocation completed",
            user_id=str(current_user.id),
            tool=request.tool,
            success=response.success,
            duration_ms=response.duration_ms,
            error_code=response.error.code if response.error else None,
        )

        # Callback for telemetry (increment_tool_invocation, etc.)
        if on_invoke:
            try:
                on_invoke(response)
            except Exception:  # pragma: no cover - telemetry best-effort
                pass

        return response

    @router.get("/health")
    async def mcp_health_check():
        """
        MCP health check endpoint.

        Returns:
            Health status with tool count
        """
        tools = registry.list_tools()

        return {
            "status": "ok",
            "mcp_version": "1.0.0",
            "tools_registered": len(tools),
            "tools": [{"name": t.name, "version": t.version} for t in tools],
        }

    return router
