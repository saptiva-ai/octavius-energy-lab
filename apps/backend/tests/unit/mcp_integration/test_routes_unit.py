"""
Unit tests for MCP routes module.

Tests the FastAPI router creation and endpoint functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_integration.routes import create_mcp_router
from src.mcp_integration.protocol import (
    ToolSpec,
    ToolCapability,
    ToolCategory,
    ToolInvokeRequest,
    ToolInvokeResponse,
    ToolError,
    ErrorCode,
)


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock()
    user.id = "user-123"
    return user


@pytest.fixture
def mock_registry():
    """Create a mock tool registry."""
    registry = MagicMock()
    return registry


@pytest.fixture
def mock_auth_dependency(mock_user):
    """Create a mock auth dependency."""

    def get_current_user():
        return mock_user

    return get_current_user


@pytest.fixture
def sample_tool_spec():
    """Create a sample tool spec."""
    return ToolSpec(
        name="test_tool",
        version="1.0.0",
        display_name="Test Tool",
        description="A test tool",
        category=ToolCategory.DOCUMENT_ANALYSIS,
        capabilities=[ToolCapability.SYNC],
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object"},
        tags=["test", "sample"],
    )


@pytest.fixture
def app(mock_registry, mock_auth_dependency):
    """Create a FastAPI app with MCP router."""
    app = FastAPI()
    router = create_mcp_router(mock_registry, mock_auth_dependency)
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestCreateMcpRouter:
    """Tests for create_mcp_router function."""

    def test_creates_router_with_correct_prefix(self, mock_registry, mock_auth_dependency):
        """Test that router is created with /mcp prefix."""
        router = create_mcp_router(mock_registry, mock_auth_dependency)
        assert router.prefix == "/mcp"

    def test_creates_router_with_correct_tags(self, mock_registry, mock_auth_dependency):
        """Test that router has correct tags."""
        router = create_mcp_router(mock_registry, mock_auth_dependency)
        assert "mcp" in router.tags

    def test_creates_router_with_all_routes(self, mock_registry, mock_auth_dependency):
        """Test that router has all expected routes."""
        router = create_mcp_router(mock_registry, mock_auth_dependency)
        route_paths = [route.path for route in router.routes]

        # Routes include the /mcp prefix
        assert any("/tools" in path for path in route_paths)
        assert any("tool_name" in path for path in route_paths)
        assert any("/invoke" in path for path in route_paths)
        assert any("/health" in path for path in route_paths)


class TestListToolsEndpoint:
    """Tests for GET /mcp/tools endpoint."""

    def test_list_tools_success(self, client, mock_registry, sample_tool_spec):
        """Test successful tool listing."""
        mock_registry.list_tools.return_value = [sample_tool_spec]

        response = client.get("/mcp/tools")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "test_tool"

    def test_list_tools_with_category_filter(self, client, mock_registry, sample_tool_spec):
        """Test tool listing with category filter."""
        mock_registry.list_tools.return_value = [sample_tool_spec]

        response = client.get("/mcp/tools?category=analysis")

        assert response.status_code == 200
        mock_registry.list_tools.assert_called_once_with(category="analysis")

    def test_list_tools_with_search(self, client, mock_registry, sample_tool_spec):
        """Test tool listing with search query."""
        mock_registry.search_tools.return_value = [sample_tool_spec]

        response = client.get("/mcp/tools?search=test")

        assert response.status_code == 200
        mock_registry.search_tools.assert_called_once_with("test")

    def test_list_tools_empty(self, client, mock_registry):
        """Test listing when no tools registered."""
        mock_registry.list_tools.return_value = []

        response = client.get("/mcp/tools")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_tools_multiple(self, client, mock_registry, sample_tool_spec):
        """Test listing multiple tools."""
        tool2 = ToolSpec(
            name="another_tool",
            version="2.0.0",
            display_name="Another Tool",
            description="Another tool",
            category=ToolCategory.DATA_ANALYTICS,
            capabilities=[ToolCapability.ASYNC],
            input_schema={},
            output_schema={},
            tags=["data"],
        )
        mock_registry.list_tools.return_value = [sample_tool_spec, tool2]

        response = client.get("/mcp/tools")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


class TestGetToolSpecEndpoint:
    """Tests for GET /mcp/tools/{tool_name} endpoint."""

    def test_get_tool_spec_success(self, client, mock_registry, sample_tool_spec):
        """Test successful tool spec retrieval."""
        mock_tool = MagicMock()
        mock_tool.get_spec.return_value = sample_tool_spec
        mock_registry.get_tool.return_value = mock_tool

        response = client.get("/mcp/tools/test_tool")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test_tool"
        assert data["version"] == "1.0.0"

    def test_get_tool_spec_with_version(self, client, mock_registry, sample_tool_spec):
        """Test tool spec retrieval with specific version."""
        mock_tool = MagicMock()
        mock_tool.get_spec.return_value = sample_tool_spec
        mock_registry.get_tool.return_value = mock_tool

        response = client.get("/mcp/tools/test_tool?version=1.0.0")

        assert response.status_code == 200
        mock_registry.get_tool.assert_called_once_with("test_tool", "1.0.0")

    def test_get_tool_spec_not_found(self, client, mock_registry):
        """Test tool spec retrieval when tool not found."""
        mock_registry.get_tool.return_value = None

        response = client.get("/mcp/tools/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestInvokeToolEndpoint:
    """Tests for POST /mcp/invoke endpoint."""

    def test_invoke_tool_success(self, client, mock_registry):
        """Test successful tool invocation."""
        mock_response = ToolInvokeResponse(
            success=True,
            tool="test_tool",
            version="1.0.0",
            result={"output": "test result"},
            error=None,
            metadata={},
            invocation_id="inv-123",
            duration_ms=50.0,
            cached=False,
        )

        # Make invoke an async mock
        async def mock_invoke(request):
            return mock_response

        mock_registry.invoke = mock_invoke

        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "test_tool",
                "payload": {"input": "test"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["tool"] == "test_tool"

    def test_invoke_tool_with_context(self, client, mock_registry):
        """Test tool invocation with context."""
        mock_response = ToolInvokeResponse(
            success=True,
            tool="test_tool",
            version="1.0.0",
            result={},
            error=None,
            metadata={},
            invocation_id="inv-123",
            duration_ms=10.0,
            cached=False,
        )

        captured_request = None

        async def mock_invoke(request):
            nonlocal captured_request
            captured_request = request
            return mock_response

        mock_registry.invoke = mock_invoke

        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "test_tool",
                "payload": {},
                "context": {"custom_key": "value"},
            },
        )

        assert response.status_code == 200
        # User ID should be injected into context
        assert captured_request.context["user_id"] == "user-123"
        assert captured_request.context["custom_key"] == "value"

    def test_invoke_tool_failure(self, client, mock_registry):
        """Test tool invocation failure."""
        mock_response = ToolInvokeResponse(
            success=False,
            tool="test_tool",
            version="1.0.0",
            result=None,
            error=ToolError(
                code=ErrorCode.EXECUTION_ERROR,
                message="Something went wrong",
                details={},
            ),
            metadata={},
            invocation_id="inv-123",
            duration_ms=5.0,
            cached=False,
        )

        async def mock_invoke(request):
            return mock_response

        mock_registry.invoke = mock_invoke

        response = client.post(
            "/mcp/invoke",
            json={"tool": "test_tool", "payload": {}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "EXECUTION_ERROR"

    def test_invoke_tool_with_version(self, client, mock_registry):
        """Test tool invocation with specific version."""
        mock_response = ToolInvokeResponse(
            success=True,
            tool="test_tool",
            version="2.0.0",
            result={},
            error=None,
            metadata={},
            invocation_id="inv-123",
            duration_ms=10.0,
            cached=False,
        )

        captured_request = None

        async def mock_invoke(request):
            nonlocal captured_request
            captured_request = request
            return mock_response

        mock_registry.invoke = mock_invoke

        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "test_tool",
                "version": "2.0.0",
                "payload": {},
            },
        )

        assert response.status_code == 200
        assert captured_request.version == "2.0.0"

    def test_invoke_tool_with_idempotency_key(self, client, mock_registry):
        """Test tool invocation with idempotency key."""
        mock_response = ToolInvokeResponse(
            success=True,
            tool="test_tool",
            version="1.0.0",
            result={},
            error=None,
            metadata={},
            invocation_id="inv-123",
            duration_ms=10.0,
            cached=False,
        )

        captured_request = None

        async def mock_invoke(request):
            nonlocal captured_request
            captured_request = request
            return mock_response

        mock_registry.invoke = mock_invoke

        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "test_tool",
                "payload": {},
                "idempotency_key": "unique-key-123",
            },
        )

        assert response.status_code == 200
        assert captured_request.idempotency_key == "unique-key-123"


class TestInvokeToolWithCallback:
    """Tests for tool invocation with on_invoke callback."""

    def test_invoke_calls_callback_on_success(self, mock_registry, mock_auth_dependency):
        """Test that callback is called on successful invocation."""
        callback_called = False
        callback_response = None

        def on_invoke(response):
            nonlocal callback_called, callback_response
            callback_called = True
            callback_response = response

        app = FastAPI()
        router = create_mcp_router(mock_registry, mock_auth_dependency, on_invoke)
        app.include_router(router)
        client = TestClient(app)

        mock_response = ToolInvokeResponse(
            success=True,
            tool="test_tool",
            version="1.0.0",
            result={},
            error=None,
            metadata={},
            invocation_id="inv-123",
            duration_ms=10.0,
            cached=False,
        )

        async def mock_invoke(request):
            return mock_response

        mock_registry.invoke = mock_invoke

        response = client.post(
            "/mcp/invoke",
            json={"tool": "test_tool", "payload": {}},
        )

        assert response.status_code == 200
        assert callback_called is True
        assert callback_response == mock_response

    def test_invoke_handles_callback_error(self, mock_registry, mock_auth_dependency):
        """Test that callback errors don't affect response."""

        def on_invoke(response):
            raise Exception("Callback error")

        app = FastAPI()
        router = create_mcp_router(mock_registry, mock_auth_dependency, on_invoke)
        app.include_router(router)
        client = TestClient(app)

        mock_response = ToolInvokeResponse(
            success=True,
            tool="test_tool",
            version="1.0.0",
            result={},
            error=None,
            metadata={},
            invocation_id="inv-123",
            duration_ms=10.0,
            cached=False,
        )

        async def mock_invoke(request):
            return mock_response

        mock_registry.invoke = mock_invoke

        # Should not raise despite callback error
        response = client.post(
            "/mcp/invoke",
            json={"tool": "test_tool", "payload": {}},
        )

        assert response.status_code == 200


class TestHealthEndpoint:
    """Tests for GET /mcp/health endpoint."""

    def test_health_check_success(self, client, mock_registry, sample_tool_spec):
        """Test successful health check."""
        mock_registry.list_tools.return_value = [sample_tool_spec]

        response = client.get("/mcp/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["mcp_version"] == "1.0.0"
        assert data["tools_registered"] == 1
        assert len(data["tools"]) == 1
        assert data["tools"][0]["name"] == "test_tool"

    def test_health_check_no_tools(self, client, mock_registry):
        """Test health check with no tools registered."""
        mock_registry.list_tools.return_value = []

        response = client.get("/mcp/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["tools_registered"] == 0
        assert data["tools"] == []

    def test_health_check_multiple_tools(self, client, mock_registry, sample_tool_spec):
        """Test health check with multiple tools."""
        tool2 = ToolSpec(
            name="tool2",
            version="2.0.0",
            display_name="Tool 2",
            description="Another tool",
            category=ToolCategory.DATA_ANALYTICS,
            capabilities=[],
            input_schema={},
            output_schema={},
            tags=[],
        )
        mock_registry.list_tools.return_value = [sample_tool_spec, tool2]

        response = client.get("/mcp/health")

        assert response.status_code == 200
        data = response.json()
        assert data["tools_registered"] == 2
        tool_names = [t["name"] for t in data["tools"]]
        assert "test_tool" in tool_names
        assert "tool2" in tool_names
