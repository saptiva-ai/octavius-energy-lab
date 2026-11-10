"""
Tests for Lazy MCP Routes - On-demand tool loading endpoints.

Tests verify:
- Discovery endpoint returns minimal metadata
- Tool spec endpoint loads on-demand
- Invoke endpoint loads and executes tools
- Stats endpoint shows efficiency metrics
- Unload endpoint frees memory
"""

import sys
from types import SimpleNamespace

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

# Provide a lightweight stub for prometheus_client during unit tests
if "prometheus_client" not in sys.modules:
    class _DummyMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            return None

        def observe(self, *args, **kwargs):
            return None

        def set(self, *args, **kwargs):
            return None

    sys.modules["prometheus_client"] = SimpleNamespace(
        Counter=lambda *args, **kwargs: _DummyMetric(),
        Histogram=lambda *args, **kwargs: _DummyMetric(),
        Gauge=lambda *args, **kwargs: _DummyMetric(),
    )

if "beanie" not in sys.modules:
    class _DummyDocument:
        pass

    class _DummyIndexed:
        def __init__(self, *args, **kwargs):
            pass
        def __class_getitem__(cls, item):
            return cls

    class _DummyLink:
        def __init__(self, *args, **kwargs):
            pass
        def __class_getitem__(cls, item):
            return cls

    sys.modules["beanie"] = SimpleNamespace(
        Document=_DummyDocument,
        Indexed=_DummyIndexed,
        Link=_DummyLink,
    )

if "pymongo" not in sys.modules:
    class _DummyIndexModel:
        def __init__(self, *args, **kwargs):
            pass

    sys.modules["pymongo"] = SimpleNamespace(
        IndexModel=_DummyIndexModel,
        ASCENDING=1,
    )

if "beanie.operators" not in sys.modules:
    class _DummyOperator:
        def __init__(self, *args, **kwargs):
            pass

    sys.modules["beanie.operators"] = SimpleNamespace(In=_DummyOperator)

if "redis" not in sys.modules:
    class _DummyRedisClient:
        async def zcount(self, *args, **kwargs):
            return 0
        async def zrange(self, *args, **kwargs):
            return []
        async def zadd(self, *args, **kwargs):
            return None
        async def expire(self, *args, **kwargs):
            return None
        async def ping(self):
            return True

    async def _from_url(*args, **kwargs):
        return _DummyRedisClient()

    sys.modules["redis"] = SimpleNamespace(asyncio=SimpleNamespace(Redis=_DummyRedisClient, from_url=_from_url))
    sys.modules["redis.asyncio"] = SimpleNamespace(Redis=_DummyRedisClient, from_url=_from_url)

from src.mcp_integration.lazy_routes import create_lazy_mcp_router
from src.mcp_integration.lazy_registry import LazyToolRegistry
from src.mcp_integration.protocol import ToolSpec, ToolInvokeResponse, ToolCategory


@pytest.fixture
def mock_registry():
    """Mock LazyToolRegistry."""
    registry = Mock(spec=LazyToolRegistry)
    return registry


@pytest.fixture(autouse=True)
def clear_admin_env(monkeypatch):
    """Ensure MCP_ADMIN_USERS is unset unless a test overrides it."""
    monkeypatch.delenv("MCP_ADMIN_USERS", raising=False)


@pytest.fixture
def mock_auth_dependency():
    """Mock authentication dependency."""
    async def get_current_user():
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.username = "regular-user"
        mock_user.email = "regular@example.com"
        return mock_user
    return get_current_user


@pytest.fixture
def mock_admin_auth_dependency():
    """Mock authentication dependency returning admin user."""
    async def get_admin_user():
        mock_user = Mock()
        mock_user.id = "admin123"
        mock_user.username = "mcp-admin"
        mock_user.email = "admin@example.com"
        return mock_user
    return get_admin_user


@pytest.fixture
def app_with_lazy_routes(mock_registry, mock_auth_dependency):
    """Create FastAPI app with lazy routes."""
    app = FastAPI()

    # Patch the global registry
    with patch("src.mcp_integration.lazy_routes.get_lazy_registry", return_value=mock_registry):
        router = create_lazy_mcp_router(
            auth_dependency=mock_auth_dependency,
            on_invoke=None
        )
        app.include_router(router)

    return app, mock_registry


@pytest.fixture
def app_with_lazy_routes_admin(mock_registry, mock_admin_auth_dependency, monkeypatch):
    """Create FastAPI app with lazy routes and admin auth."""
    app = FastAPI()
    monkeypatch.setenv("MCP_ADMIN_USERS", "mcp-admin,admin@example.com")

    with patch("src.mcp_integration.lazy_routes.get_lazy_registry", return_value=mock_registry):
        router = create_lazy_mcp_router(
            auth_dependency=mock_admin_auth_dependency,
            on_invoke=None
        )
        app.include_router(router)

    return app, mock_registry


@pytest.mark.asyncio
class TestDiscoverEndpoint:
    """Test GET /mcp/lazy/discover endpoint."""

    async def test_discover_all_tools(self, app_with_lazy_routes):
        """Test discovering all tools without filters."""
        app, mock_registry = app_with_lazy_routes

        # Mock registry response
        mock_registry.discover_tools.return_value = [
            {
                "name": "excel_analyzer",
                "category": "compliance",
                "description": "Tool: excel_analyzer",
                "loaded": False
            },
            {
                "name": "excel_analyzer",
                "category": "analytics",
                "description": "Tool: excel_analyzer",
                "loaded": False
            }
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/discover")

        assert response.status_code == 200, response.json()
        data = response.json()

        assert "tools" in data
        assert "total" in data
        assert "loaded" in data
        assert "optimization" in data

        assert data["total"] == 2
        assert data["loaded"] == 0
        assert len(data["tools"]) == 2

        # Verify registry was called without filters
        mock_registry.discover_tools.assert_called_once_with(
            category=None,
            search_query=None
        )

    async def test_discover_with_category_filter(self, app_with_lazy_routes):
        """Test discovering tools by category."""
        app, mock_registry = app_with_lazy_routes

        mock_registry.discover_tools.return_value = [
            {
                "name": "excel_analyzer",
                "category": "compliance",
                "description": "Tool: excel_analyzer",
                "loaded": False
            }
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/discover?category=compliance")

        assert response.status_code == 200, response.json()
        data = response.json()

        assert data["total"] == 1
        assert data["tools"][0]["name"] == "excel_analyzer"

        # Verify category filter was passed
        mock_registry.discover_tools.assert_called_once_with(
            category="compliance",
            search_query=None
        )

    async def test_discover_with_search_query(self, app_with_lazy_routes):
        """Test discovering tools by search query."""
        app, mock_registry = app_with_lazy_routes

        mock_registry.discover_tools.return_value = [
            {
                "name": "excel_analyzer",
                "category": "compliance",
                "description": "Tool: excel_analyzer",
                "loaded": False
            }
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/discover?search=audit")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1

        # Verify search query was passed
        mock_registry.discover_tools.assert_called_once_with(
            category=None,
            search_query="audit"
        )

    async def test_discover_shows_loaded_count(self, app_with_lazy_routes):
        """Test that discover shows how many tools are loaded."""
        app, mock_registry = app_with_lazy_routes

        mock_registry.discover_tools.return_value = [
            {"name": "tool1", "category": "general", "description": "Tool 1", "loaded": True},
            {"name": "tool2", "category": "general", "description": "Tool 2", "loaded": False},
            {"name": "tool3", "category": "general", "description": "Tool 3", "loaded": False}
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/discover")

        data = response.json()
        assert data["total"] == 3
        assert data["loaded"] == 1  # Only tool1 is loaded

    async def test_discover_returns_minimal_metadata(self, app_with_lazy_routes):
        """Test that discover returns minimal metadata."""
        app, mock_registry = app_with_lazy_routes

        mock_registry.discover_tools.return_value = [
            {
                "name": "excel_analyzer",
                "category": "compliance",
                "description": "Tool: excel_analyzer",
                "loaded": False
            }
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/discover")

        data = response.json()
        tool = data["tools"][0]

        # Should only have 4 fields
        assert set(tool.keys()) == {"name", "category", "description", "loaded"}


@pytest.mark.asyncio
class TestGetToolSpecEndpoint:
    """Test GET /mcp/lazy/tools/{tool_name} endpoint."""

    async def test_get_tool_spec_success(self, app_with_lazy_routes):
        """Test getting tool specification."""
        app, mock_registry = app_with_lazy_routes

        # Mock tool spec
        mock_spec = ToolSpec(
            name="excel_analyzer",
            version="1.0.0",
            display_name="Audit File",
            description="Validates document compliance",
            category=ToolCategory.COMPLIANCE,
            capabilities=[],
            input_schema={"type": "object", "properties": {"doc_id": {"type": "string"}}},
            output_schema={"type": "object"},
            tags=["compliance", "validation"],
            requires_auth=True,
            rate_limit=None,
            timeout_ms=30000
        )

        mock_registry.get_tool_spec = AsyncMock(return_value=mock_spec)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/tools/excel_analyzer")

        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "excel_analyzer"
        assert data["version"] == "1.0.0"
        assert data["display_name"] == "Audit File"
        assert data["description"] == "Validates document compliance"
        assert data["category"] == "compliance"
        assert data["loaded_on_demand"] is True

        # Verify registry was called
        mock_registry.get_tool_spec.assert_called_once_with("excel_analyzer")

    async def test_get_tool_spec_not_found(self, app_with_lazy_routes):
        """Test getting spec for non-existent tool."""
        app, mock_registry = app_with_lazy_routes

        mock_registry.get_tool_spec = AsyncMock(return_value=None)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/tools/nonexistent")

        assert response.status_code == 404
        data = response.json()
        assert "nonexistent" in data["detail"]

    async def test_get_tool_spec_loads_on_demand(self, app_with_lazy_routes):
        """Test that getting spec loads tool on-demand."""
        app, mock_registry = app_with_lazy_routes

        mock_spec = ToolSpec(
            name="excel_analyzer",
            version="1.0.0",
            display_name="Audit File",
            description="Test",
            category=ToolCategory.COMPLIANCE,
            capabilities=[],
            input_schema={},
            output_schema={}
        )

        mock_registry.get_tool_spec = AsyncMock(return_value=mock_spec)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/tools/excel_analyzer")

        assert response.status_code == 200
        data = response.json()

        # Should indicate it was loaded on-demand
        assert data["loaded_on_demand"] is True


@pytest.mark.asyncio
class TestInvokeEndpoint:
    """Test POST /mcp/lazy/invoke endpoint."""

    async def test_invoke_tool_success(self, app_with_lazy_routes):
        """Test invoking a tool successfully."""
        app, mock_registry = app_with_lazy_routes

        # Mock successful response
        mock_response = ToolInvokeResponse(
            success=True,
            tool="excel_analyzer",
            version="1.0.0",
            result={"findings": []},
            error=None,
            metadata={},
            invocation_id="inv123",
            duration_ms=123.45,
            cached=False
        )

        mock_registry.invoke = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/mcp/lazy/invoke",
                json={
                    "tool": "excel_analyzer",
                    "payload": {"doc_id": "doc123"},
                    "context": {}
                }
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["tool"] == "excel_analyzer"
        assert data["duration_ms"] == 123.45

        # Verify registry invoke was called
        assert mock_registry.invoke.called
        call_args = mock_registry.invoke.call_args[0][0]
        assert call_args.tool == "excel_analyzer"
        assert call_args.payload == {"doc_id": "doc123"}

    async def test_invoke_tool_payload_validation_error(self, app_with_lazy_routes):
        """Payload validation failures should return structured error."""
        app, mock_registry = app_with_lazy_routes
        mock_registry.invoke = AsyncMock()

        with patch(
            "src.mcp_integration.lazy_routes.PayloadValidator.validate_size",
            side_effect=ValueError("payload too large"),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/mcp/lazy/invoke",
                    json={"tool": "excel_analyzer", "payload": {"doc_id": "doc123"}},
                )

        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert mock_registry.invoke.call_count == 0

    async def test_invoke_tool_permission_denied(self, app_with_lazy_routes):
        """Missing scope should return permission denied."""
        app, mock_registry = app_with_lazy_routes
        mock_registry.invoke = AsyncMock()

        with patch(
            "src.mcp_integration.lazy_routes.ScopeValidator.validate_tool_access",
            side_effect=PermissionError("no scope"),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/mcp/lazy/invoke",
                    json={"tool": "excel_analyzer", "payload": {"doc_id": "doc123"}},
                )

        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "PERMISSION_DENIED"
        assert mock_registry.invoke.call_count == 0

    async def test_invoke_tool_rate_limited(self, app_with_lazy_routes):
        """Rate limit exhaustion should be surfaced with retry info."""
        app, mock_registry = app_with_lazy_routes
        mock_registry.invoke = AsyncMock()

        with patch(
            "src.mcp_integration.lazy_routes.rate_limiter.check_rate_limit",
            AsyncMock(return_value=(False, 2500)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/mcp/lazy/invoke",
                    json={"tool": "excel_analyzer", "payload": {"doc_id": "doc123"}},
                )

        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "RATE_LIMIT"
        assert data["error"]["retry_after_ms"] == 2500
        assert mock_registry.invoke.call_count == 0

    async def test_invoke_injects_user_id(self, app_with_lazy_routes):
        """Test that invoke injects user_id into context."""
        app, mock_registry = app_with_lazy_routes

        mock_response = ToolInvokeResponse(
            success=True,
            tool="excel_analyzer",
            version="1.0.0",
            result={},
            error=None,
            metadata={},
            invocation_id="inv123",
            duration_ms=100.0,
            cached=False
        )

        mock_registry.invoke = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/mcp/lazy/invoke",
                json={
                    "tool": "excel_analyzer",
                    "payload": {"doc_id": "doc123"},
                    "context": {"extra": "data"}
                }
            )

        assert response.status_code == 200

        # Verify user_id was injected into context
        call_args = mock_registry.invoke.call_args[0][0]
        assert call_args.context["user_id"] == "user123"
        assert call_args.context["extra"] == "data"

    async def test_invoke_calls_on_invoke_callback(self):
        """Test that invoke calls on_invoke callback for telemetry."""
        mock_registry = Mock(spec=LazyToolRegistry)
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.username = "regular-user"
        mock_user.email = "regular@example.com"

        async def mock_auth():
            return mock_user

        # Track callback calls
        callback_called = []
        def on_invoke_callback(response):
            callback_called.append(response)

        app = FastAPI()
        with patch("src.mcp_integration.lazy_routes.get_lazy_registry", return_value=mock_registry):
            router = create_lazy_mcp_router(
                auth_dependency=mock_auth,
                on_invoke=on_invoke_callback
            )
            app.include_router(router)

        mock_response = ToolInvokeResponse(
            success=True,
            tool="excel_analyzer",
            version="1.0.0",
            result={},
            error=None,
            metadata={},
            invocation_id="inv123",
            duration_ms=100.0,
            cached=False
        )

        mock_registry.invoke = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/mcp/lazy/invoke",
                json={
                    "tool": "excel_analyzer",
                    "payload": {"doc_id": "doc123"},
                    "context": {}
                }
            )

        assert response.status_code == 200
        assert len(callback_called) == 1
        assert callback_called[0] is mock_response

    async def test_invoke_handles_callback_errors(self):
        """Test that invoke handles callback errors gracefully."""
        mock_registry = Mock(spec=LazyToolRegistry)
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.username = "regular-user"
        mock_user.email = "regular@example.com"

        async def mock_auth():
            return mock_user

        # Callback that raises error
        def on_invoke_callback(response):
            raise Exception("Telemetry failed")

        app = FastAPI()
        with patch("src.mcp_integration.lazy_routes.get_lazy_registry", return_value=mock_registry):
            router = create_lazy_mcp_router(
                auth_dependency=mock_auth,
                on_invoke=on_invoke_callback
            )
            app.include_router(router)

        mock_response = ToolInvokeResponse(
            success=True,
            tool="excel_analyzer",
            version="1.0.0",
            result={},
            error=None,
            metadata={},
            invocation_id="inv123",
            duration_ms=100.0,
            cached=False
        )

        mock_registry.invoke = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/mcp/lazy/invoke",
                json={
                    "tool": "excel_analyzer",
                    "payload": {"doc_id": "doc123"},
                    "context": {}
                }
            )

        # Should still succeed even if callback fails
        assert response.status_code == 200


@pytest.mark.asyncio
class TestStatsEndpoint:
    """Test GET /mcp/lazy/stats endpoint."""

    async def test_get_stats_requires_admin(self, app_with_lazy_routes):
        """Regular users cannot access stats."""
        app, _ = app_with_lazy_routes

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/stats")

        assert response.status_code == 403

    async def test_get_stats(self, app_with_lazy_routes_admin):
        """Admins can fetch registry stats."""
        app, mock_registry = app_with_lazy_routes_admin

        mock_registry.get_registry_stats.return_value = {
            "tools_discovered": 5,
            "tools_loaded": 2,
            "tools_available": ["tool1", "tool2", "tool3", "tool4", "tool5"],
            "tools_loaded_list": ["tool1", "tool2"],
            "memory_efficiency": "60.0%"
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/stats")

        assert response.status_code == 200
        data = response.json()

        assert data["tools_discovered"] == 5
        assert data["tools_loaded"] == 2
        assert len(data["tools_available"]) == 5
        assert len(data["tools_loaded_list"]) == 2
        assert data["memory_efficiency"] == "60.0%"
        assert "optimization_note" in data

    async def test_stats_shows_memory_efficiency(self, app_with_lazy_routes_admin):
        """Test that stats shows memory efficiency."""
        app, mock_registry = app_with_lazy_routes_admin

        mock_registry.get_registry_stats.return_value = {
            "tools_discovered": 10,
            "tools_loaded": 1,
            "tools_available": [f"tool{i}" for i in range(10)],
            "tools_loaded_list": ["tool0"],
            "memory_efficiency": "90.0%"
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/stats")

        data = response.json()

        # Should show high efficiency (90%)
        assert "90.0%" in data["optimization_note"]
        assert "1/10" in data["optimization_note"]


@pytest.mark.asyncio
class TestUnloadEndpoint:
    """Test DELETE /mcp/lazy/tools/{tool_name}/unload endpoint."""

    async def test_unload_requires_admin(self, app_with_lazy_routes):
        """Regular users cannot unload tools."""
        app, _ = app_with_lazy_routes

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete("/mcp/lazy/tools/excel_analyzer/unload")

        assert response.status_code == 403

    async def test_unload_tool_success(self, app_with_lazy_routes_admin):
        """Test unloading a loaded tool with admin scope."""
        app, mock_registry = app_with_lazy_routes_admin

        mock_registry.unload_tool.return_value = True

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete("/mcp/lazy/tools/excel_analyzer/unload")

        assert response.status_code == 200
        data = response.json()

        assert data["unloaded"] is True
        assert data["tool"] == "excel_analyzer"
        assert "successfully" in data["message"]

        # Verify registry was called
        mock_registry.unload_tool.assert_called_once_with("excel_analyzer")

    async def test_unload_tool_not_loaded(self, app_with_lazy_routes_admin):
        """Test unloading a tool that's not loaded."""
        app, mock_registry = app_with_lazy_routes_admin

        mock_registry.unload_tool.return_value = False

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete("/mcp/lazy/tools/excel_analyzer/unload")

        assert response.status_code == 200
        data = response.json()

        assert data["unloaded"] is False
        assert data["tool"] == "excel_analyzer"
        assert "was not loaded" in data["message"]


@pytest.mark.asyncio
class TestAuthenticationRequired:
    """Test that all endpoints require authentication."""

    async def test_discover_requires_auth(self):
        """Test that discover endpoint requires auth."""
        # Create router without mock (will use real auth)
        app = FastAPI()

        # Use a real auth dependency that will fail
        async def failing_auth():
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Unauthorized")

        mock_registry = Mock(spec=LazyToolRegistry)
        with patch("src.mcp_integration.lazy_routes.get_lazy_registry", return_value=mock_registry):
            router = create_lazy_mcp_router(
                auth_dependency=failing_auth,
                on_invoke=None
            )
            app.include_router(router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/discover")

        assert response.status_code == 401

    async def test_get_tool_spec_requires_auth(self):
        """Test that get tool spec requires auth."""
        app = FastAPI()

        async def failing_auth():
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Unauthorized")

        mock_registry = Mock(spec=LazyToolRegistry)
        with patch("src.mcp_integration.lazy_routes.get_lazy_registry", return_value=mock_registry):
            router = create_lazy_mcp_router(
                auth_dependency=failing_auth,
                on_invoke=None
            )
            app.include_router(router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/mcp/lazy/tools/excel_analyzer")

        assert response.status_code == 401

    async def test_invoke_requires_auth(self):
        """Test that invoke requires auth."""
        app = FastAPI()

        async def failing_auth():
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Unauthorized")

        mock_registry = Mock(spec=LazyToolRegistry)
        with patch("src.mcp_integration.lazy_routes.get_lazy_registry", return_value=mock_registry):
            router = create_lazy_mcp_router(
                auth_dependency=failing_auth,
                on_invoke=None
            )
            app.include_router(router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/mcp/lazy/invoke",
                json={"tool": "excel_analyzer", "payload": {"doc_id": "doc123"}}
            )

        assert response.status_code == 401
