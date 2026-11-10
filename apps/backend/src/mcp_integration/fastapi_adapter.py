"""
FastMCP-FastAPI Adapter

Integrates FastMCP server with existing FastAPI application:
1. Exposes MCP tools via REST endpoints (/api/mcp/tools, /api/mcp/invoke)
2. Maintains backwards compatibility with existing architecture
3. Injects user context from FastAPI auth middleware
4. Provides observability hooks (telemetry, logging)

Best practices:
- Use FastMCP for tool implementation (automatic schema generation)
- Use FastAPI for HTTP/REST API (existing infra, auth, middleware)
- Bridge the two with this adapter
"""

import asyncio
import inspect
from typing import Callable, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastmcp import Client, FastMCP

from ..models.user import User
from .metrics import metrics_collector
from .protocol import ErrorCode
from .security import (
    PayloadValidator,
    RateLimitConfig,
    ScopeValidator,
    get_user_scopes,
    rate_limiter,
)
from .tasks import TaskPriority, TaskStatus, task_manager
from .versioning import versioned_registry

logger = structlog.get_logger(__name__)


class MCPFastAPIAdapter:
    """
    Adapter to expose FastMCP server via FastAPI REST endpoints.

    Provides:
    - GET /mcp/tools - List available tools with schemas
    - POST /mcp/invoke - Invoke a tool with payload
    - GET /mcp/health - Health check
    """

    def __init__(
        self,
        mcp_server: FastMCP,
        auth_dependency: Callable,
        on_invoke: Optional[Callable] = None,
        async_threshold_ms: int = 5000,  # Tools estimated > 5s run async
    ):
        """
        Initialize adapter.

        Args:
            mcp_server: FastMCP server instance
            auth_dependency: FastAPI auth dependency (e.g., get_current_user)
            on_invoke: Optional callback after tool invocation (for telemetry)
            async_threshold_ms: Threshold for async execution (default: 5000ms)
        """
        self.mcp_server = mcp_server
        self.auth_dependency = auth_dependency
        self.on_invoke = on_invoke
        self.client = Client(mcp_server)  # In-memory client for testing
        self.async_threshold_ms = async_threshold_ms

    def create_router(self, prefix: str = "/mcp", tags: List[str] = None) -> APIRouter:
        """
        Create FastAPI router with MCP endpoints.

        Args:
            prefix: URL prefix (default: "/mcp")
            tags: OpenAPI tags (default: ["mcp"])

        Returns:
            FastAPI router
        """
        router = APIRouter(prefix=prefix, tags=tags or ["mcp"])

        @router.get("/tools")
        async def list_tools(
            current_user: User = Depends(self.auth_dependency),
        ):
            """
            List available MCP tools.

            Returns tool specifications with:
            - name, version, display_name, description
            - category, capabilities, tags
            - input_schema, output_schema (JSON Schema)
            - rate_limit, timeout_ms, max_payload_size_kb
            """
            logger.info("MCP tools listing requested", user_id=str(current_user.id))

            # Use FastMCP introspection to list tools
            tools = []
            tool_map = await self._get_tool_map()
            for tool_name, tool_obj in tool_map.items():
                callable_ref = getattr(tool_obj, "fn", tool_obj)
                # Check if tool has multiple versions in versioned registry
                available_versions = versioned_registry.list_versions(tool_name)
                latest_version = versioned_registry.get_latest(tool_name)

                # If no versions registered, use default 1.0.0
                if not available_versions:
                    available_versions = ["1.0.0"]
                    latest_version = "1.0.0"

                # Extract metadata from FastMCP tool
                tool_spec = {
                    "name": tool_name,
                    "version": latest_version,
                    "available_versions": available_versions,  # NEW: List all versions
                    "display_name": self._resolve_tool_display_name(tool_name),
                    "description": self._resolve_tool_description(tool_obj, tool_name),
                    "category": "general",  # Could be extracted from tool metadata
                    "capabilities": ["async"],  # FastMCP tools are async by default
                    "tags": [],
                    "author": "OctaviOS",
                    "requires_auth": True,
                    "input_schema": self._get_tool_input_schema(tool_obj, callable_ref),
                    "output_schema": self._get_tool_output_schema(
                        tool_obj, callable_ref
                    ),
                    "timeout_ms": 30000,
                    "max_payload_size_kb": 1024,
                }
                tools.append(tool_spec)

            logger.info(
                "MCP tools listed", user_id=str(current_user.id), tool_count=len(tools)
            )
            return tools

        @router.post("/invoke")
        async def invoke_tool(
            request: dict,
            current_user: User = Depends(self.auth_dependency),
        ):
            """
            Invoke an MCP tool.

            Request format:
            {
                "tool": "audit_file",
                "version": "1.0.0",  // optional
                "payload": {
                    "doc_id": "doc_123",
                    "policy_id": "auto"
                },
                "context": {},  // optional
                "idempotency_key": "..."  // optional
            }

            Returns:
            {
                "success": true,
                "tool": "audit_file",
                "version": "1.0.0",
                "result": {...},
                "error": null,
                "metadata": {...},
                "invocation_id": "inv_123",
                "duration_ms": 1234.56,
                "cached": false
            }
            """
            import time
            from uuid import uuid4

            tool_name = request.get("tool")
            version_constraint = request.get(
                "version"
            )  # NEW: Optional version constraint
            payload = request.get("payload", {})
            idempotency_key = request.get("idempotency_key")

            if not tool_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing required field: tool",
                )

            logger.info(
                "MCP tool invocation requested",
                user_id=str(current_user.id),
                tool=tool_name,
                version_constraint=version_constraint,
                idempotency_key=idempotency_key,
            )

            invocation_id = str(uuid4())
            start_time = time.time()

            try:
                # Security Layer 1: Validate payload size
                try:
                    PayloadValidator.validate_size(payload, max_size_kb=1024)
                    PayloadValidator.validate_structure(payload)
                except ValueError as e:
                    duration_ms = (time.time() - start_time) * 1000

                    # Record validation failure metrics
                    metrics_collector.record_tool_invocation(
                        tool=tool_name,
                        version=version_constraint or "latest",
                        status="error",
                        duration_seconds=duration_ms / 1000,
                        outcome="validation_error",
                        user_type="user",
                    )
                    metrics_collector.record_validation_failure(
                        tool=tool_name,
                        version=version_constraint or "latest",
                        error_code="VALIDATION_ERROR",
                    )

                    return {
                        "success": False,
                        "tool": tool_name,
                        "version": version_constraint or "latest",
                        "result": None,
                        "error": {
                            "code": ErrorCode.VALIDATION_ERROR.value,
                            "message": str(e),
                            "user_message": "Request payload validation failed",
                        },
                        "metadata": {},
                        "invocation_id": invocation_id,
                        "duration_ms": (time.time() - start_time) * 1000,
                        "cached": False,
                    }

                # Security Layer 2: Check authorization scopes
                user_scopes = get_user_scopes(current_user)
                try:
                    ScopeValidator.validate_tool_access(user_scopes, tool_name)
                except PermissionError as e:
                    duration_ms = (time.time() - start_time) * 1000

                    # Record permission denied metrics
                    required_scope = ScopeValidator.get_required_scope(tool_name)
                    metrics_collector.record_tool_invocation(
                        tool=tool_name,
                        version=version_constraint or "latest",
                        status="error",
                        duration_seconds=duration_ms / 1000,
                        outcome="permission_denied",
                        user_type="user",
                    )
                    metrics_collector.record_permission_denied(
                        tool=tool_name,
                        required_scope=(
                            required_scope.value if required_scope else "unknown"
                        ),
                    )

                    logger.warning(
                        "Tool access denied: missing scope",
                        user_id=str(current_user.id),
                        tool=tool_name,
                        error=str(e),
                    )
                    return {
                        "success": False,
                        "tool": tool_name,
                        "version": version_constraint or "latest",
                        "result": None,
                        "error": {
                            "code": ErrorCode.PERMISSION_DENIED.value,
                            "message": str(e),
                            "user_message": "You don't have permission to use this tool",
                        },
                        "metadata": {},
                        "invocation_id": invocation_id,
                        "duration_ms": (time.time() - start_time) * 1000,
                        "cached": False,
                    }

                # Security Layer 3: Rate limiting
                rate_limit_key = f"{current_user.id}:{tool_name}"
                rate_limit_config = RateLimitConfig(
                    calls_per_minute=60,  # 60 per minute
                    calls_per_hour=1000,  # 1000 per hour
                )

                allowed, retry_after_ms = await rate_limiter.check_rate_limit(
                    rate_limit_key,
                    rate_limit_config,
                )

                if not allowed:
                    duration_ms = (time.time() - start_time) * 1000

                    # Record rate limit metrics
                    metrics_collector.record_tool_invocation(
                        tool=tool_name,
                        version=version_constraint or "latest",
                        status="error",
                        duration_seconds=duration_ms / 1000,
                        outcome="rate_limit",
                        user_type="user",
                    )
                    metrics_collector.record_rate_limit_exceeded(
                        tool=tool_name,
                        user_type="user",
                    )

                    return {
                        "success": False,
                        "tool": tool_name,
                        "version": version_constraint or "latest",
                        "result": None,
                        "error": {
                            "code": ErrorCode.RATE_LIMIT.value,
                            "message": f"Rate limit exceeded for tool '{tool_name}'",
                            "user_message": "Too many requests. Please try again later.",
                            "retry_after_ms": retry_after_ms,
                        },
                        "metadata": {},
                        "invocation_id": invocation_id,
                        "duration_ms": (time.time() - start_time) * 1000,
                        "cached": False,
                    }

                # Resolve version if versioned registry has this tool
                resolved_version = None
                tool_impl = None
                tools_snapshot: Optional[dict] = None

                if versioned_registry.list_versions(tool_name):
                    # Tool has versions - use versioned registry
                    try:
                        resolved_version, tool_impl = versioned_registry.resolve(
                            tool_name, version_constraint
                        )
                        logger.debug(
                            "Tool version resolved",
                            tool=tool_name,
                            constraint=version_constraint,
                            resolved=resolved_version,
                        )
                    except ValueError as e:
                        # Version resolution failed
                        return {
                            "success": False,
                            "tool": tool_name,
                            "version": version_constraint or "latest",
                            "result": None,
                            "error": {
                                "code": "TOOL_NOT_FOUND",
                                "message": str(e),
                                "details": {
                                    "available_versions": versioned_registry.list_versions(
                                        tool_name
                                    )
                                },
                            },
                            "metadata": {},
                            "invocation_id": invocation_id,
                            "duration_ms": 0.0,
                            "cached": False,
                        }
                else:
                    # Tool not versioned - use FastMCP default registry
                    tools_snapshot = await self._get_tool_map()
                    tool_impl = tools_snapshot.get(tool_name)
                    resolved_version = "1.0.0"

                if not tool_impl:
                    available_tools = (
                        list(tools_snapshot.keys())
                        if tools_snapshot is not None
                        else list((await self._get_tool_map()).keys())
                    )
                    return {
                        "success": False,
                        "tool": tool_name,
                        "version": resolved_version or "1.0.0",
                        "result": None,
                        "error": {
                            "code": "TOOL_NOT_FOUND",
                            "message": f"Tool '{tool_name}' not found",
                            "details": {"available_tools": available_tools},
                        },
                        "metadata": {},
                        "invocation_id": invocation_id,
                        "duration_ms": 0.0,
                        "cached": False,
                    }

                if (
                    tool_impl
                    and not hasattr(tool_impl, "run")
                    and self._callable_accepts_param(tool_impl, "user_id")
                    and "user_id" not in payload
                ):
                    payload = {**payload, "user_id": str(current_user.id)}

                # Execute tool
                result = await self._execute_tool_impl(
                    tool_name,
                    tool_impl,
                    payload,
                    context={"user_id": str(current_user.id)},
                )

                duration_ms = (time.time() - start_time) * 1000

                # Record success metrics
                metrics_collector.record_tool_invocation(
                    tool=tool_name,
                    version=resolved_version or "1.0.0",
                    status="success",
                    duration_seconds=duration_ms / 1000,
                    outcome="success",
                    user_type="user",
                )

                response = {
                    "success": True,
                    "tool": tool_name,
                    "version": resolved_version or "1.0.0",
                    "result": result,
                    "error": None,
                    "metadata": {
                        "user_id": str(current_user.id),
                        "idempotency_key": idempotency_key,
                        "version_constraint": version_constraint,  # NEW: Track requested constraint
                    },
                    "invocation_id": invocation_id,
                    "duration_ms": duration_ms,
                    "cached": False,
                }

                logger.info(
                    "MCP tool invocation succeeded",
                    user_id=str(current_user.id),
                    tool=tool_name,
                    duration_ms=duration_ms,
                )

                # Callback for telemetry
                if self.on_invoke:
                    try:
                        self.on_invoke(response)
                    except Exception:  # pragma: no cover
                        pass

                return response

            except ValueError as e:
                # Input validation error
                duration_ms = (time.time() - start_time) * 1000

                logger.warning(
                    "MCP tool invocation failed: invalid input",
                    user_id=str(current_user.id),
                    tool=tool_name,
                    error=str(e),
                )

                return {
                    "success": False,
                    "tool": tool_name,
                    "version": "1.0.0",
                    "result": None,
                    "error": {
                        "code": "INVALID_INPUT",
                        "message": str(e),
                        "details": {},
                    },
                    "metadata": {},
                    "invocation_id": invocation_id,
                    "duration_ms": duration_ms,
                    "cached": False,
                }

            except PermissionError as e:
                # Authorization error
                duration_ms = (time.time() - start_time) * 1000

                logger.warning(
                    "MCP tool invocation failed: permission denied",
                    user_id=str(current_user.id),
                    tool=tool_name,
                    error=str(e),
                )

                return {
                    "success": False,
                    "tool": tool_name,
                    "version": "1.0.0",
                    "result": None,
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": str(e),
                        "details": {},
                    },
                    "metadata": {},
                    "invocation_id": invocation_id,
                    "duration_ms": duration_ms,
                    "cached": False,
                }

            except Exception as e:
                # Execution error
                duration_ms = (time.time() - start_time) * 1000

                logger.error(
                    "MCP tool invocation failed: execution error",
                    user_id=str(current_user.id),
                    tool=tool_name,
                    error=str(e),
                    exc_info=True,
                )

                return {
                    "success": False,
                    "tool": tool_name,
                    "version": "1.0.0",
                    "result": None,
                    "error": {
                        "code": "EXECUTION_ERROR",
                        "message": f"Tool execution failed: {str(e)}",
                        "details": {"exc_type": type(e).__name__},
                    },
                    "metadata": {},
                    "invocation_id": invocation_id,
                    "duration_ms": duration_ms,
                    "cached": False,
                }

        @router.get("/health")
        async def mcp_health_check(
            include_tools: bool = Query(False, description="Include tool details"),
            include_metrics: bool = Query(False, description="Include metrics summary"),
            include_tasks: bool = Query(False, description="Include task queue status"),
        ):
            """
            Enhanced MCP health check endpoint with capability filtering.

            Query Parameters:
            - include_tools: Include detailed tool information
            - include_metrics: Include metrics summary (Prometheus)
            - include_tasks: Include task queue status

            Returns:
                Comprehensive health status with optional details

            Examples:
            - GET /health - Minimal health check
            - GET /health?include_tools=true - Health + tool list
            - GET /health?include_tools=true&include_metrics=true - Full status
            """
            from .metrics import get_metrics_summary
            from .tasks import task_manager

            tool_map = await self._get_tool_map()
            tools = list(tool_map.keys())

            # Base health response
            response = {
                "status": "ok",
                "mcp_version": "1.0.0",
                "fastmcp_version": "2.0.0",
                "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
                "tools_registered": len(tools),
                "capabilities": {
                    "task_management": True,  # 202 Accepted pattern
                    "versioning": True,  # Semver support
                    "security": True,  # Rate limiting, AuthZ, validation
                    "metrics": True,  # Prometheus metrics
                    "schema_discovery": True,  # Auto-generated schemas
                    "cancellation": True,  # Task cancellation
                },
            }

            # Optional: Include tool details
            if include_tools:
                tool_details = []
                for tool_name in tools:
                    tool_obj = tool_map.get(tool_name)
                    callable_ref = (
                        getattr(tool_obj, "fn", tool_obj) if tool_obj else None
                    )
                    available_versions = versioned_registry.list_versions(tool_name)
                    latest_version = (
                        versioned_registry.get_latest(tool_name)
                        if available_versions
                        else "1.0.0"
                    )

                    tool_details.append(
                        {
                            "name": tool_name,
                            "version": latest_version,
                            "available_versions": available_versions or ["1.0.0"],
                            "description": (
                                self._resolve_tool_description(tool_obj, tool_name)
                                if tool_obj
                                else f"Execute {tool_name}"
                            ),
                        }
                    )

                response["tools"] = tool_details

            # Optional: Include metrics summary
            if include_metrics:
                response["metrics"] = get_metrics_summary()

            # Optional: Include task queue status
            if include_tasks:
                pending_tasks = task_manager.list_tasks(
                    status=__import__(
                        "src.mcp_integration.tasks", fromlist=["TaskStatus"]
                    ).TaskStatus.PENDING
                )
                running_tasks = task_manager.list_tasks(
                    status=__import__(
                        "src.mcp_integration.tasks", fromlist=["TaskStatus"]
                    ).TaskStatus.RUNNING
                )

                response["tasks"] = {
                    "pending": len(pending_tasks),
                    "running": len(running_tasks),
                    "queue_healthy": len(running_tasks) < 10,  # Threshold
                }

            return response

        @router.get("/discover")
        async def discover_tools(
            category: Optional[str] = Query(None, description="Filter by category"),
            capability: Optional[str] = Query(
                None, description="Filter by capability (async, streaming, etc.)"
            ),
            tag: Optional[str] = Query(None, description="Filter by tag"),
            search: Optional[str] = Query(
                None, description="Search in name or description"
            ),
            include_schema: bool = Query(
                False, description="Include input/output schemas"
            ),
            include_versions: bool = Query(
                True, description="Include version information"
            ),
            current_user: User = Depends(self.auth_dependency),
        ):
            """
            Enhanced MCP discovery endpoint with powerful filtering.

            Query Parameters:
            - category: Filter by tool category (e.g., "document_analysis")
            - capability: Filter by capability (e.g., "async", "streaming")
            - tag: Filter by tag (e.g., "compliance", "analytics")
            - search: Full-text search in name/description
            - include_schema: Include full JSON schemas (default: false)
            - include_versions: Include version info (default: true)

            Returns:
                Filtered list of tool specifications

            Examples:
            - GET /discover - All tools
            - GET /discover?category=document_analysis - Document tools only
            - GET /discover?capability=async - Async tools only
            - GET /discover?search=audit - Search for "audit"
            - GET /discover?include_schema=true - Tools with full schemas
            """
            from .security import ScopeValidator, get_user_scopes

            logger.info(
                "MCP tool discovery requested",
                user_id=str(current_user.id),
                filters={
                    "category": category,
                    "capability": capability,
                    "tag": tag,
                    "search": search,
                },
            )

            user_scopes = get_user_scopes(current_user)
            tool_map = await self._get_tool_map()
            tools = []

            for tool_name, tool_obj in tool_map.items():
                callable_ref = getattr(tool_obj, "fn", tool_obj)
                # Check if user has access to this tool
                try:
                    ScopeValidator.validate_tool_access(user_scopes, tool_name)
                except PermissionError:
                    # Skip tools user doesn't have access to
                    continue

                # Get version information
                available_versions = versioned_registry.list_versions(tool_name)
                latest_version = (
                    versioned_registry.get_latest(tool_name)
                    if available_versions
                    else "1.0.0"
                )

                # Extract tool metadata
                tool_spec = {
                    "name": tool_name,
                    "display_name": self._resolve_tool_display_name(tool_name),
                    "description": self._resolve_tool_description(tool_obj, tool_name),
                    "category": "general",  # TODO: Extract from metadata
                    "capabilities": ["async"],  # FastMCP tools are async by default
                    "tags": [],  # TODO: Extract from metadata
                    "author": "OctaviOS",
                    "requires_auth": True,
                }

                # Add version information
                if include_versions:
                    tool_spec["version"] = latest_version
                    tool_spec["available_versions"] = available_versions or ["1.0.0"]

                # Add schemas if requested
                if include_schema:
                    tool_spec["input_schema"] = self._get_tool_input_schema(
                        tool_obj, callable_ref
                    )
                    tool_spec["output_schema"] = self._get_tool_output_schema(
                        tool_obj, callable_ref
                    )

                # Apply filters
                if category and tool_spec["category"] != category:
                    continue

                if capability and capability not in tool_spec["capabilities"]:
                    continue

                if tag and tag not in tool_spec["tags"]:
                    continue

                if search:
                    search_lower = search.lower()
                    if (
                        search_lower not in tool_spec["name"].lower()
                        and search_lower not in tool_spec["description"].lower()
                    ):
                        continue

                tools.append(tool_spec)

            logger.info(
                "MCP tool discovery completed",
                user_id=str(current_user.id),
                total_tools=len(tool_map),
                filtered_tools=len(tools),
            )

            return {
                "total": len(tools),
                "filtered": len(tools),
                "tools": tools,
                "filters_applied": {
                    "category": category,
                    "capability": capability,
                    "tag": tag,
                    "search": search,
                },
            }

        @router.get("/schema/{tool_name}")
        async def get_tool_schema(
            tool_name: str,
            version: Optional[str] = Query(
                None, description="Version constraint (e.g., ^1.0.0)"
            ),
            current_user: User = Depends(self.auth_dependency),
        ):
            """
            Get JSON Schema for a specific tool.

            Returns detailed input/output schemas with:
            - Input schema: JSON Schema for request validation
            - Output schema: JSON Schema for response structure
            - Example payload: Sample input for testing
            - Version info: Available versions and resolved version

            Useful for:
            - Frontend form generation
            - Client SDK validation
            - API documentation
            - Testing and debugging
            """
            logger.info(
                "Tool schema requested",
                user_id=str(current_user.id),
                tool=tool_name,
                version_constraint=version,
            )

            # Resolve version
            resolved_version = None
            tool_impl = None
            tools_snapshot: Optional[dict] = None

            if versioned_registry.list_versions(tool_name):
                # Tool has versions
                try:
                    resolved_version, tool_impl = versioned_registry.resolve(
                        tool_name, version
                    )
                except ValueError as e:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=str(e),
                    )
            else:
                # Tool not versioned
                tools_snapshot = await self._get_tool_map()
                tool_impl = tools_snapshot.get(tool_name)
                resolved_version = "1.0.0"

            if not tool_impl:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tool '{tool_name}' not found",
                )

            # Extract schemas
            callable_ref = getattr(tool_impl, "fn", tool_impl)
            input_schema = self._get_tool_input_schema(tool_impl, callable_ref)
            output_schema = self._get_tool_output_schema(tool_impl, callable_ref)

            # Generate example payload
            example_payload = self._generate_example_payload(input_schema)

            return {
                "tool": tool_name,
                "version": resolved_version,
                "available_versions": versioned_registry.list_versions(tool_name)
                or ["1.0.0"],
                "input_schema": input_schema,
                "output_schema": output_schema,
                "example_payload": example_payload,
                "description": self._resolve_tool_description(tool_impl, tool_name),
            }

        # Task Management Routes (202 Accepted Pattern)

        @router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
        async def create_task(
            request: dict,
            current_user: User = Depends(self.auth_dependency),
        ):
            """
            Submit a long-running tool invocation as a background task.

            Returns 202 Accepted with task_id for polling.

            Request format (same as /invoke):
            {
                "tool": "excel_analyzer",
                "payload": {...},
                "priority": "normal"  // optional: "low" | "normal" | "high"
            }

            Response:
            {
                "task_id": "uuid",
                "status": "pending",
                "poll_url": "/api/mcp/tasks/{task_id}",
                "cancel_url": "/api/mcp/tasks/{task_id}",
                "estimated_duration_ms": 10000
            }
            """
            tool_name = request.get("tool")
            payload = request.get("payload", {})
            priority_str = request.get("priority", "normal")

            if not tool_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing required field: tool",
                )

            # Validate tool exists
            tools_snapshot = await self._get_tool_map()
            if tool_name not in tools_snapshot:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tool '{tool_name}' not found",
                )

            # Map priority string to enum
            try:
                priority = TaskPriority(priority_str)
            except ValueError:
                priority = TaskPriority.NORMAL

            # Create task
            task_id = task_manager.create_task(
                tool=tool_name,
                payload=payload,
                user_id=str(current_user.id),
                priority=priority,
            )

            # Record task creation metric
            metrics_collector.record_task_created(
                tool=tool_name,
                priority=priority.value,
            )

            logger.info(
                "MCP task created",
                task_id=task_id,
                tool=tool_name,
                user_id=str(current_user.id),
                priority=priority.value,
            )

            # Start task execution in background
            import asyncio

            asyncio.create_task(
                self._execute_task(task_id, tool_name, payload, current_user)
            )

            return {
                "task_id": task_id,
                "status": "pending",
                "poll_url": f"{prefix}/tasks/{task_id}",
                "cancel_url": f"{prefix}/tasks/{task_id}",
                "estimated_duration_ms": self._estimate_duration(tool_name, payload),
            }

        @router.get("/tasks/{task_id}")
        async def get_task_status(
            task_id: str,
            current_user: User = Depends(self.auth_dependency),
        ):
            """
            Poll task status and get result when completed.

            Returns:
            {
                "task_id": "uuid",
                "tool": "excel_analyzer",
                "status": "running",  // pending | running | completed | failed | cancelled
                "progress": 0.5,  // 0.0 to 1.0
                "progress_message": "Processing rows...",
                "created_at": "2025-01-11T...",
                "started_at": "2025-01-11T...",
                "completed_at": null,
                "result": {...},  // only when status=completed
                "error": {...},  // only when status=failed
            }
            """
            task = task_manager.get_task(task_id)

            if not task:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Task '{task_id}' not found",
                )

            # Verify ownership
            if task.user_id != str(current_user.id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to access this task",
                )

            return {
                "task_id": task.task_id,
                "tool": task.tool,
                "status": task.status.value,
                "progress": task.progress,
                "progress_message": task.progress_message,
                "created_at": task.created_at.isoformat(),
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": (
                    task.completed_at.isoformat() if task.completed_at else None
                ),
                "result": task.result,
                "error": task.error,
            }

        @router.delete("/tasks/{task_id}", status_code=status.HTTP_202_ACCEPTED)
        async def cancel_task(
            task_id: str,
            current_user: User = Depends(self.auth_dependency),
        ):
            """
            Request task cancellation.

            Returns 202 Accepted. The task will be marked for cancellation,
            but actual cancellation depends on the tool checking cancellation_requested.

            Response:
            {
                "task_id": "uuid",
                "status": "cancellation_requested",
                "message": "Cancellation requested. Task will stop at next checkpoint."
            }
            """
            task = task_manager.get_task(task_id)

            if not task:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Task '{task_id}' not found",
                )

            # Verify ownership
            if task.user_id != str(current_user.id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to cancel this task",
                )

            # Request cancellation
            success = task_manager.request_cancellation(task_id)

            if not success:
                return {
                    "task_id": task_id,
                    "status": task.status.value,
                    "message": f"Task is in terminal state ({task.status.value}) and cannot be cancelled",
                }

            # Record task cancellation metric
            metrics_collector.record_task_cancelled(tool=task.tool)

            logger.info(
                "MCP task cancellation requested",
                task_id=task_id,
                tool=task.tool,
                user_id=str(current_user.id),
            )

            return {
                "task_id": task_id,
                "status": "cancellation_requested",
                "message": "Cancellation requested. Task will stop at next checkpoint.",
            }

        @router.get("/tasks")
        async def list_tasks(
            current_user: User = Depends(self.auth_dependency),
            status_filter: Optional[str] = Query(None, alias="status"),
            tool_filter: Optional[str] = Query(None, alias="tool"),
        ):
            """
            List user's tasks with optional filters.

            Query params:
            - status: Filter by status (pending | running | completed | failed | cancelled)
            - tool: Filter by tool name

            Returns list of task summaries.
            """

            # Parse status filter
            task_status = None
            if status_filter:
                try:
                    task_status = TaskStatus(status_filter)
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid status: {status_filter}",
                    )

            tasks = task_manager.list_tasks(
                user_id=str(current_user.id),
                tool=tool_filter,
                status=task_status,
            )

            return [
                {
                    "task_id": t.task_id,
                    "tool": t.tool,
                    "status": t.status.value,
                    "progress": t.progress,
                    "created_at": t.created_at.isoformat(),
                    "started_at": t.started_at.isoformat() if t.started_at else None,
                    "completed_at": (
                        t.completed_at.isoformat() if t.completed_at else None
                    ),
                }
                for t in tasks
            ]

        return router

    def _extract_input_schema(self, tool_func: Callable) -> dict:
        """
        Extract JSON Schema from tool function signature.

        FastMCP automatically generates schemas from type hints.
        This is a simplified version for REST API documentation.
        """
        from typing import get_type_hints

        sig = inspect.signature(tool_func)
        hints = get_type_hints(tool_func)

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("ctx", "self"):  # Skip context and self
                continue

            param_type = hints.get(param_name, str)
            json_type = self._python_type_to_json_type(param_type)

            properties[param_name] = {"type": json_type}

            # Check if required (no default value)
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    async def _get_tool_map(self) -> dict:
        """
        Obtain the current FastMCP tool registry, compatible with FastMCP 2.x and legacy builds.
        """
        # Preferred: public async API (FastMCP >= 2.11)
        get_tools = getattr(self.mcp_server, "get_tools", None)
        if callable(get_tools):
            tools = await get_tools()
            if isinstance(tools, dict):
                return tools

        # Fallback: legacy internal dictionary
        raw_tools = getattr(self.mcp_server, "_tools", None)
        if isinstance(raw_tools, dict):
            return raw_tools

        return {}

    # ------------------------------------------------------------------
    # API pública para consumidores externos (services), para no acoplarlos
    # a los privados `_get_tool_map` / `_execute_tool_impl` (recomendación D).
    # ------------------------------------------------------------------
    async def get_tool_map(self) -> dict:
        """Mapa de tools registradas (nombre -> tool). Delegación fina, misma semántica."""
        return await self._get_tool_map()

    async def execute_tool(
        self, tool_name: str, tool_impl, payload: dict, context: Optional[dict] = None
    ):
        """Ejecuta una tool registrada. Wrapper público de `_execute_tool_impl`."""
        return await self._execute_tool_impl(tool_name, tool_impl, payload, context)

    def _resolve_tool_description(self, tool_obj, tool_name: str) -> str:
        """Best-effort description extraction regardless of FastMCP version."""
        description = getattr(tool_obj, "description", None)
        if description:
            return description

        fn = getattr(tool_obj, "fn", None)
        if fn and getattr(fn, "__doc__", None):
            return fn.__doc__

        return getattr(tool_obj, "__doc__", None) or f"Execute {tool_name}"

    def _resolve_tool_display_name(self, tool_name: str) -> str:
        return tool_name.replace("_", " ").title()

    def _get_tool_input_schema(self, tool_obj, fallback_callable):
        schema = getattr(tool_obj, "parameters", None)
        if schema:
            return schema
        return self._extract_input_schema(fallback_callable)

    def _callable_accepts_param(self, fn: Callable, param_name: str) -> bool:
        """Check if a callable declares a given parameter."""
        try:
            signature = inspect.signature(fn)
            return param_name in signature.parameters
        except (ValueError, TypeError):
            return False

    def _get_tool_output_schema(self, tool_obj, fallback_callable):
        schema = getattr(tool_obj, "output_schema", None)
        if schema:
            return schema
        return self._extract_output_schema(fallback_callable)

    async def _execute_tool_impl(
        self, tool_name: str, tool_impl, payload: dict, context: Optional[dict] = None
    ):
        """
        Execute a tool regardless of whether FastMCP returns Tool objects or raw callables.
        """
        import structlog

        adapter_logger = structlog.get_logger()

        if tool_impl is None:
            raise ValueError(f"Tool '{tool_name}' not found")

        adapter_logger.info(
            "🔌 [ADAPTER] Attempting to invoke tool",
            tool=tool_name,
            payload_keys=list(payload.keys()),
            has_context=bool(context),
        )

        try:
            # FastMCP >= 2.x returns Tool/FunctionTool instances with .run()
            if hasattr(tool_impl, "run"):
                # ✅ Invocación estándar: payload como primer argumento (FastMCP valida con Pydantic)
                return await tool_impl.run(payload)

            # Legacy callables (aceptan payload completo como único arg)
            if callable(tool_impl):
                return await tool_impl(payload)

            raise ValueError(f"Tool {tool_name} is not executable")

        except Exception as e:
            adapter_logger.error(
                "🚨 [ADAPTER FATAL CRASH] Tool invocation failed",
                tool=tool_name,
                error=str(e),
                error_type=type(e).__name__,
                payload=payload,
            )
            raise

    def _normalize_tool_result(self, result):
        """
        Convert FastMCP ToolResult or raw return values into JSON-serializable payloads.
        """
        if hasattr(result, "structured_content") or hasattr(result, "content"):
            structured = getattr(result, "structured_content", None)
            if structured is not None:
                return jsonable_encoder(structured)

            content = getattr(result, "content", None)
            if content is not None:
                return jsonable_encoder({"content": content})

        return jsonable_encoder(result)

    def _python_type_to_json_type(self, python_type) -> str:
        """Map Python types to JSON Schema types."""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }

        # Handle Optional types
        if hasattr(python_type, "__origin__"):
            if python_type.__origin__ is list:
                return "array"
            elif python_type.__origin__ is dict:
                return "object"

        return type_map.get(python_type, "string")

    async def _execute_task(
        self, task_id: str, tool_name: str, payload: dict, user: User
    ):
        """
        Execute a task in the background.

        Handles:
        - Progress tracking
        - Cancellation checks
        - Error handling
        - Result persistence
        """
        import time

        task_start_time = time.time()

        # Ensure task exists (some tests inject tasks manually)
        existing_task = task_manager.get_task(task_id)
        if existing_task is None:
            fallback_user_id = str(getattr(user, "id", "system") if user else "system")
            task_manager.create_task(
                tool=tool_name,
                payload=payload,
                user_id=fallback_user_id,
                priority=TaskPriority.NORMAL,
                task_id=task_id,
            )

        task_manager.mark_running(task_id)

        try:
            # Get tool function or descriptor
            tools_snapshot = await self._get_tool_map()
            tool_impl = tools_snapshot.get(tool_name)
            if not tool_impl:
                task_manager.mark_failed(
                    task_id,
                    {
                        "code": "TOOL_NOT_FOUND",
                        "message": f"Tool '{tool_name}' not found",
                    },
                )
                return

            if (
                tool_impl
                and not hasattr(tool_impl, "run")
                and self._callable_accepts_param(tool_impl, "user_id")
                and "user_id" not in payload
            ):
                payload = {**payload, "user_id": str(getattr(user, "id", "system"))}

            # Execute tool with cancellation checks
            # Note: Tool implementation should check task_manager.is_cancellation_requested(task_id)
            # at checkpoints and raise asyncio.CancelledError

            result = await self._execute_tool_impl(tool_name, tool_impl, payload)

            # Check if cancelled during execution
            if task_manager.is_cancellation_requested(task_id):
                task_manager.mark_cancelled(task_id)

                # Record cancellation metric
                task_duration = time.time() - task_start_time
                metrics_collector.record_task_completed(
                    tool=tool_name,
                    status="cancelled",
                    duration_seconds=task_duration,
                )

                logger.info(
                    "Task cancelled during execution", task_id=task_id, tool=tool_name
                )
                return

            # Mark completed
            task_manager.mark_completed(task_id, result)

            # Record completion metric
            task_duration = time.time() - task_start_time
            metrics_collector.record_task_completed(
                tool=tool_name,
                status="completed",
                duration_seconds=task_duration,
            )

            logger.info("Task completed successfully", task_id=task_id, tool=tool_name)

        except asyncio.CancelledError:
            # Task was cancelled
            task_manager.mark_cancelled(task_id)

            # Record cancellation metric
            task_duration = time.time() - task_start_time
            metrics_collector.record_task_completed(
                tool=tool_name,
                status="cancelled",
                duration_seconds=task_duration,
            )

            logger.info("Task cancelled", task_id=task_id, tool=tool_name)

        except ValueError as e:
            # Validation error
            task_manager.mark_failed(
                task_id,
                {
                    "code": "VALIDATION_ERROR",
                    "message": str(e),
                },
            )

            # Record failure metric
            task_duration = time.time() - task_start_time
            metrics_collector.record_task_completed(
                tool=tool_name,
                status="failed",
                duration_seconds=task_duration,
            )

            logger.warning(
                "Task failed: validation error",
                task_id=task_id,
                tool=tool_name,
                error=str(e),
            )

        except PermissionError as e:
            # Permission error
            task_manager.mark_failed(
                task_id,
                {
                    "code": "PERMISSION_DENIED",
                    "message": str(e),
                },
            )

            # Record failure metric
            task_duration = time.time() - task_start_time
            metrics_collector.record_task_completed(
                tool=tool_name,
                status="failed",
                duration_seconds=task_duration,
            )

            logger.warning(
                "Task failed: permission denied",
                task_id=task_id,
                tool=tool_name,
                error=str(e),
            )

        except Exception as e:
            # Execution error
            task_manager.mark_failed(
                task_id,
                {
                    "code": "EXECUTION_ERROR",
                    "message": f"Tool execution failed: {str(e)}",
                    "details": {"exc_type": type(e).__name__},
                },
            )

            # Record failure metric
            task_duration = time.time() - task_start_time
            metrics_collector.record_task_completed(
                tool=tool_name,
                status="failed",
                duration_seconds=task_duration,
            )

            logger.error(
                "Task failed: execution error",
                task_id=task_id,
                tool=tool_name,
                error=str(e),
                exc_info=True,
            )

    def _estimate_duration(self, tool_name: str, payload: dict) -> int:
        """
        Estimate task duration in milliseconds.

        Heuristics:
        - audit_file: 5s base + 1s per page
        - excel_analyzer: 10s base + 0.1s per 1000 rows
        - viz_tool: 3s base
        - default: 5s
        """
        if tool_name == "audit_file":
            # Estimate based on document complexity
            return 5000  # Base 5 seconds

        elif tool_name == "excel_analyzer":
            # Estimate based on operations
            operations = payload.get("operations", [])
            base = 10000  # 10 seconds base
            per_operation = 2000  # 2 seconds per operation
            return base + (len(operations) * per_operation)

        elif tool_name == "viz_tool":
            return 3000  # 3 seconds

        else:
            return 5000  # Default 5 seconds

    def _extract_output_schema(self, tool_func: Callable) -> dict:
        """
        Extract output JSON Schema from tool function return type hint.

        For now, returns a generic object schema. In future, could use:
        - Pydantic models in return type annotations
        - TypedDict annotations
        - Custom decorators with schema metadata
        """
        from typing import get_type_hints

        try:
            hints = get_type_hints(tool_func)
            return_type = hints.get("return", dict)

            # Check if it's a Pydantic model
            if hasattr(return_type, "model_json_schema"):
                return return_type.model_json_schema()

            # Default: generic object
            return {
                "type": "object",
                "description": "Tool execution result",
                "properties": {
                    "result": {"type": "object", "description": "Tool-specific output"}
                },
            }
        except Exception:
            # Fallback
            return {"type": "object"}

    def _generate_example_payload(self, input_schema: dict) -> dict:
        """
        Generate example payload from JSON Schema.

        Creates sample values based on property types:
        - string: "example_value"
        - integer: 1
        - number: 1.0
        - boolean: true
        - array: []
        - object: {}
        """
        example = {}

        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get("type", "string")

            # Generate example based on type
            if prop_type == "string":
                # Check for format hints
                if "format" in prop_schema:
                    if prop_schema["format"] == "email":
                        example[prop_name] = "user@example.com"
                    elif prop_schema["format"] == "uri":
                        example[prop_name] = "https://example.com"
                    elif prop_schema["format"] == "date":
                        example[prop_name] = "2025-01-11"
                    else:
                        example[prop_name] = f"example_{prop_name}"
                else:
                    example[prop_name] = f"example_{prop_name}"

            elif prop_type == "integer":
                example[prop_name] = 1

            elif prop_type == "number":
                example[prop_name] = 1.0

            elif prop_type == "boolean":
                example[prop_name] = True

            elif prop_type == "array":
                example[prop_name] = []

            elif prop_type == "object":
                example[prop_name] = {}

            # Only include if required (keep example minimal)
            if prop_name not in required:
                # Optional field - skip in minimal example
                pass

        return example
