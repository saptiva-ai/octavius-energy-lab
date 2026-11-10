"""
Lazy MCP Routes - On-demand tool loading endpoints.

These routes support the optimized MCP pattern where tools are
discovered and loaded only when needed, reducing context usage
by ~98% compared to loading all tools upfront.

Endpoints:
- GET /mcp/lazy/discover - List available tools (minimal metadata)
- GET /mcp/lazy/tools/{tool_name} - Get specific tool spec (loads on-demand)
- POST /mcp/lazy/invoke - Invoke tool (loads on-demand)
- GET /mcp/lazy/stats - Registry statistics
"""

import time
from typing import Callable, Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..models.user import User
from .lazy_registry import get_lazy_registry
from .metrics import metrics_collector
from .protocol import ErrorCode, ToolError, ToolInvokeRequest, ToolInvokeResponse
from .security import (
    MCPScope,
    PayloadValidator,
    RateLimitConfig,
    ScopeValidator,
    get_user_scopes,
    rate_limiter,
)

logger = structlog.get_logger(__name__)


def create_lazy_mcp_router(
    auth_dependency: Callable,
    on_invoke: Optional[Callable[[ToolInvokeResponse], None]] = None,
) -> APIRouter:
    """
    Create lazy MCP router with on-demand tool loading.

    Args:
        auth_dependency: Auth dependency (e.g., get_current_user)
        on_invoke: Optional callback after tool invocation

    Returns:
        FastAPI router
    """
    router = APIRouter(prefix="/mcp/lazy", tags=["mcp-lazy"])
    lazy_registry = get_lazy_registry()

    def _require_admin_scope(user: User, required_scope: MCPScope) -> None:
        user_scopes = get_user_scopes(user)
        try:
            ScopeValidator.require_scope(user_scopes, required_scope)
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            )

    @router.get("/discover")
    async def discover_tools(
        category: Optional[str] = Query(None, description="Filter by category"),
        search: Optional[str] = Query(None, description="Search in name/description"),
        current_user: User = Depends(auth_dependency),
    ):
        """
        Discover available tools without loading them.

        Returns minimal metadata to reduce context usage.
        Tools are NOT loaded until explicitly requested.

        **Optimization**: Returns only ~50 bytes per tool vs ~5KB
        when loading full tool definitions.

        Args:
            category: Optional category filter (compliance, analytics, etc.)
            search: Optional search query
            current_user: Authenticated user

        Returns:
            List of tool metadata (name, category, description, loaded status)

        Example:
            GET /mcp/lazy/discover?category=compliance

            Response:
            [
              {
                "name": "audit_file",
                "category": "compliance",
                "description": "Tool: audit_file",
                "loaded": false
              },
              ...
            ]
        """
        user_scopes = get_user_scopes(current_user)
        try:
            ScopeValidator.require_scope(user_scopes, MCPScope.TOOLS_ALL)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        logger.info(
            "Tool discovery requested",
            user_id=str(current_user.id),
            category=category,
            search=search,
        )

        tools = lazy_registry.discover_tools(category=category, search_query=search)

        logger.info(
            "Tools discovered",
            user_id=str(current_user.id),
            count=len(tools),
            loaded_count=sum(1 for t in tools if t["loaded"]),
        )

        return {
            "tools": tools,
            "total": len(tools),
            "loaded": sum(1 for t in tools if t["loaded"]),
            "optimization": "Minimal metadata returned to reduce context usage",
        }

    @router.get("/tools/{tool_name}")
    async def get_tool_spec(
        tool_name: str,
        current_user: User = Depends(auth_dependency),
    ):
        """
        Get tool specification (loads tool on-demand if needed).

        This endpoint loads the actual tool definition only when
        requested, avoiding unnecessary context usage.

        Args:
            tool_name: Name of tool to load
            current_user: Authenticated user

        Returns:
            Full tool specification

        Example:
            GET /mcp/lazy/tools/audit_file

            Response:
            {
              "name": "audit_file",
              "version": "1.0.0",
              "description": "...",
              "input_schema": {...},
              "output_schema": {...},
              "loaded_on_demand": true
            }
        """
        user_scopes = get_user_scopes(current_user)
        try:
            ScopeValidator.require_scope(user_scopes, MCPScope.TOOLS_ALL)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        logger.info(
            "Tool spec requested (will load on-demand)",
            user_id=str(current_user.id),
            tool=tool_name,
        )

        # Load tool on-demand
        spec = await lazy_registry.get_tool_spec(tool_name)

        if not spec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool '{tool_name}' not found",
            )

        logger.info("Tool spec loaded", user_id=str(current_user.id), tool=tool_name)

        # Convert ToolSpec to dict
        spec_dict = {
            "name": spec.name,
            "version": spec.version,
            "display_name": spec.display_name,
            "description": spec.description,
            "category": (
                spec.category.value
                if hasattr(spec.category, "value")
                else spec.category
            ),
            "capabilities": (
                [c.value for c in spec.capabilities] if spec.capabilities else []
            ),
            "input_schema": spec.input_schema,
            "output_schema": spec.output_schema,
            "tags": spec.tags,
            "requires_auth": spec.requires_auth,
            "rate_limit": spec.rate_limit,
            "timeout_ms": spec.timeout_ms,
            "loaded_on_demand": True,
        }

        return spec_dict

    @router.post("/invoke", response_model=ToolInvokeResponse)
    async def invoke_tool(
        request: ToolInvokeRequest,
        current_user: User = Depends(auth_dependency),
    ):
        """
        Invoke tool with on-demand loading.

        The tool is loaded dynamically only when invoked,
        not at startup. This minimizes memory and context usage.

        **Optimization**: Tool definition is loaded from disk
        only when needed, not kept in memory.

        Args:
            request: Tool invocation request
            current_user: Authenticated user

        Returns:
            Tool invocation response

        Example:
            POST /mcp/lazy/invoke
            {
              "tool": "audit_file",
              "payload": {"doc_id": "123"},
              "context": {}
            }
        """
        invocation_id = str(uuid4())
        start_time = time.time()
        requested_version = request.version or "latest"
        payload = request.payload or {}
        context = (request.context or {}).copy()
        context["user_id"] = str(current_user.id)

        user_scopes = get_user_scopes(current_user)
        user_type = (
            "admin"
            if ScopeValidator.check_scope(user_scopes, MCPScope.ADMIN_ALL)
            else "user"
        )

        def _record_and_build_error(
            code: ErrorCode,
            message: str,
            user_message: str,
            outcome: str,
            details: Optional[dict] = None,
            retry_after_ms: Optional[int] = None,
        ) -> ToolInvokeResponse:
            duration_ms = (time.time() - start_time) * 1000
            metrics_collector.record_tool_invocation(
                tool=request.tool,
                version=requested_version,
                status="error",
                duration_seconds=duration_ms / 1000,
                outcome=outcome,
                user_type=user_type,
            )
            return ToolInvokeResponse(
                success=False,
                tool=request.tool,
                version=requested_version,
                result=None,
                error=ToolError(
                    code=code,
                    message=message,
                    user_message=user_message,
                    details=details,
                    retry_after_ms=retry_after_ms,
                ),
                metadata={},
                invocation_id=invocation_id,
                duration_ms=duration_ms,
                cached=False,
            )

        logger.info(
            "Tool invocation requested (will load on-demand)",
            user_id=str(current_user.id),
            tool=request.tool,
        )

        # Security Layer 1: Payload validation
        try:
            PayloadValidator.validate_size(payload, max_size_kb=1024)
            PayloadValidator.validate_structure(payload)
        except ValueError as exc:
            metrics_collector.record_validation_failure(
                tool=request.tool,
                version=requested_version,
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )
            return _record_and_build_error(
                code=ErrorCode.VALIDATION_ERROR,
                message=str(exc),
                user_message="El payload enviado no es válido para esta herramienta.",
                outcome="validation_error",
            )

        # Security Layer 2: Authorization scopes
        try:
            ScopeValidator.validate_tool_access(user_scopes, request.tool)
        except PermissionError as exc:
            required_scope = ScopeValidator.get_required_scope(request.tool)
            if required_scope:
                metrics_collector.record_permission_denied(
                    tool=request.tool,
                    required_scope=required_scope.value,
                )
            return _record_and_build_error(
                code=ErrorCode.PERMISSION_DENIED,
                message=str(exc),
                user_message="No tienes permisos para usar esta herramienta.",
                outcome="permission_denied",
                details={
                    "required_scope": required_scope.value if required_scope else None
                },
            )

        # Security Layer 3: Rate limiting
        rate_limit_key = f"{current_user.id}:{request.tool}"
        rate_limit_config = RateLimitConfig(
            calls_per_minute=60,
            calls_per_hour=1000,
        )
        allowed, retry_after_ms = await rate_limiter.check_rate_limit(
            rate_limit_key,
            rate_limit_config,
        )

        if not allowed:
            metrics_collector.record_rate_limit_exceeded(
                tool=request.tool,
                user_type=user_type,
            )
            return _record_and_build_error(
                code=ErrorCode.RATE_LIMIT,
                message=f"Rate limit exceeded for tool '{request.tool}'",
                user_message="Demasiadas solicitudes. Intenta de nuevo más tarde.",
                outcome="rate_limit",
                retry_after_ms=retry_after_ms,
            )

        # Invoke tool (loads on-demand if needed)
        tool_request = ToolInvokeRequest(
            tool=request.tool,
            version=request.version,
            payload=payload,
            context=context,
            idempotency_key=request.idempotency_key,
        )

        response = await lazy_registry.invoke(tool_request)

        outcome_label = (
            "success"
            if response.success
            else (response.error.code.value.lower() if response.error else "error")
        )
        metrics_collector.record_tool_invocation(
            tool=response.tool,
            version=response.version,
            status="success" if response.success else "error",
            duration_seconds=response.duration_ms / 1000,
            outcome=outcome_label,
            user_type=user_type,
        )

        logger.info(
            "Tool invocation completed",
            user_id=str(current_user.id),
            tool=request.tool,
            success=response.success,
            duration_ms=response.duration_ms,
        )

        # Optional callback for telemetry
        if on_invoke:
            try:
                on_invoke(response)
            except Exception:  # pragma: no cover - telemetry best effort
                pass

        return response

    @router.get("/stats")
    async def get_registry_stats(
        current_user: User = Depends(auth_dependency),
    ):
        """
        Get lazy registry statistics.

        Shows how many tools are discovered vs loaded,
        demonstrating memory efficiency.

        Returns:
            Registry statistics

        Example response:
            {
              "tools_discovered": 5,
              "tools_loaded": 2,
              "tools_available": ["audit_file", "excel_analyzer", ...],
              "tools_loaded_list": ["audit_file", "extract_document_text"],
              "memory_efficiency": "60.0%"
            }
        """
        _require_admin_scope(current_user, MCPScope.ADMIN_METRICS)

        logger.info("Registry stats requested", user_id=str(current_user.id))

        stats = lazy_registry.get_registry_stats()

        return {
            **stats,
            "optimization_note": (
                f"Only {stats['tools_loaded']}/{stats['tools_discovered']} tools "
                f"loaded in memory ({stats['memory_efficiency']} efficiency)"
            ),
        }

    @router.delete("/tools/{tool_name}/unload")
    async def unload_tool(
        tool_name: str,
        current_user: User = Depends(auth_dependency),
    ):
        """
        Unload a tool to free memory.

        Useful for long-running processes that need to
        manage memory usage dynamically.

        Args:
            tool_name: Name of tool to unload
            current_user: Authenticated user

        Returns:
            Unload status
        """
        _require_admin_scope(current_user, MCPScope.ADMIN_TOOLS_MANAGE)

        logger.info(
            "Tool unload requested", user_id=str(current_user.id), tool=tool_name
        )

        success = lazy_registry.unload_tool(tool_name)

        if success:
            return {
                "message": f"Tool '{tool_name}' unloaded successfully",
                "tool": tool_name,
                "unloaded": True,
            }
        else:
            return {
                "message": f"Tool '{tool_name}' was not loaded",
                "tool": tool_name,
                "unloaded": False,
            }

    return router
