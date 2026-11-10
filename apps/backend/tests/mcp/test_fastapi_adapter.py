"""
Unit tests for MCPFastAPIAdapter.

Tests the bridge between FastMCP and FastAPI:
- Tool listing
- Tool invocation
- Auth integration
- Error handling
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastmcp import FastMCP
import os

from src.mcp_integration.fastapi_adapter import MCPFastAPIAdapter
from src.models.user import User

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MCP_FASTAPI_ADAPTER", "false").lower() != "true",
    reason="MCP fastapi adapter tests deshabilitados por defecto (requires Redis/stack).",
)


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    user = Mock(spec=User)
    user.id = "user_123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_auth_dependency(mock_user):
    """Mock auth dependency that returns test user."""
    async def _auth():
        return mock_user
    return _auth


@pytest.fixture
def mcp_server():
    """Create a FastMCP server with test tools."""
    mcp = FastMCP("Test MCP")

    @mcp.tool()
    async def test_tool(value: str) -> dict:
        """A simple test tool."""
        return {"result": f"processed: {value}"}

    @mcp.tool()
    async def failing_tool(should_fail: bool = True) -> dict:
        """A tool that can fail."""
        if should_fail:
            raise ValueError("Tool failed as requested")
        return {"result": "success"}

    return mcp


@pytest.fixture
def adapter(mcp_server, mock_auth_dependency):
    """Create adapter with test MCP server."""
    return MCPFastAPIAdapter(
        mcp_server=mcp_server,
        auth_dependency=mock_auth_dependency,
    )


@pytest.fixture
def test_app(adapter):
    """Create test FastAPI app with MCP router."""
    app = FastAPI()
    app.include_router(adapter.create_router())
    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


class TestListTools:
    """Test GET /mcp/tools endpoint."""

    def test_list_tools_success(self, client):
        """Test listing tools returns correct format."""
        response = client.get("/mcp/tools")
        assert response.status_code == 200

        tools = response.json()
        assert isinstance(tools, list)
        assert len(tools) >= 2  # test_tool and failing_tool

        # Check tool structure
        tool = tools[0]
        assert "name" in tool
        assert "version" in tool
        assert "display_name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert "output_schema" in tool

    def test_list_tools_includes_test_tool(self, client):
        """Test that test_tool is in the list."""
        response = client.get("/mcp/tools")
        tools = response.json()

        tool_names = [t["name"] for t in tools]
        assert "test_tool" in tool_names

    def test_list_tools_without_auth_fails(self, test_app):
        """Test that listing tools without auth fails."""
        # Create app without auth dependency
        app = FastAPI()

        from src.core.auth import get_current_user
        mcp = FastMCP("Test")
        adapter = MCPFastAPIAdapter(
            mcp_server=mcp,
            auth_dependency=get_current_user,  # Real auth
        )
        app.include_router(adapter.create_router())

        client = TestClient(app)
        response = client.get("/mcp/tools")

        # Should fail without token
        assert response.status_code in [401, 403]


class TestInvokeTool:
    """Test POST /mcp/invoke endpoint."""

    def test_invoke_tool_success(self, client):
        """Test successful tool invocation."""
        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "test_tool",
                "payload": {"value": "hello"},
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["tool"] == "test_tool"
        assert data["result"]["result"] == "processed: hello"
        assert "invocation_id" in data
        assert "duration_ms" in data
        assert data["duration_ms"] > 0

    def test_invoke_tool_with_invalid_input(self, client):
        """Test tool invocation with invalid input."""
        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "test_tool",
                "payload": {},  # Missing required 'value' field
            },
        )

        assert response.status_code == 200  # Errors returned in response body
        data = response.json()

        assert data["success"] is False
        assert data["error"] is not None
        assert data["error"]["code"] in ["INVALID_INPUT", "EXECUTION_ERROR"]

    def test_invoke_nonexistent_tool(self, client):
        """Test invoking a tool that doesn't exist."""
        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "nonexistent_tool",
                "payload": {},
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert data["error"]["code"] == "TOOL_NOT_FOUND"
        assert "available_tools" in data["error"]["details"]

    def test_invoke_tool_that_raises_error(self, client):
        """Test invoking a tool that raises an exception."""
        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "failing_tool",
                "payload": {"should_fail": True},
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_INPUT"  # ValueError
        assert "Tool failed as requested" in data["error"]["message"]

    def test_invoke_tool_without_tool_field(self, client):
        """Test invocation without 'tool' field."""
        response = client.post(
            "/mcp/invoke",
            json={"payload": {}},
        )

        assert response.status_code == 400
        assert "tool" in response.json()["detail"].lower()

    def test_invoke_tool_with_idempotency_key(self, client):
        """Test tool invocation with idempotency key."""
        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "test_tool",
                "payload": {"value": "test"},
                "idempotency_key": "test-key-123",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["metadata"]["idempotency_key"] == "test-key-123"

    def test_invoke_tool_metadata_includes_user_id(self, client, mock_user):
        """Test that user_id is included in metadata."""
        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "test_tool",
                "payload": {"value": "test"},
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["metadata"]["user_id"] == str(mock_user.id)

    def test_invoke_tool_telemetry_callback(self, mcp_server, mock_auth_dependency):
        """Test that telemetry callback is invoked."""
        callback_called = False
        callback_response = None

        def telemetry_callback(response):
            nonlocal callback_called, callback_response
            callback_called = True
            callback_response = response

        adapter = MCPFastAPIAdapter(
            mcp_server=mcp_server,
            auth_dependency=mock_auth_dependency,
            on_invoke=telemetry_callback,
        )

        app = FastAPI()
        app.include_router(adapter.create_router())
        client = TestClient(app)

        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "test_tool",
                "payload": {"value": "test"},
            },
        )

        assert response.status_code == 200
        assert callback_called is True
        assert callback_response is not None
        assert callback_response["tool"] == "test_tool"


class TestHealthCheck:
    """Test GET /mcp/health endpoint."""

    def test_health_check_returns_ok(self, client):
        """Test health check returns status ok."""
        response = client.get("/mcp/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert "mcp_version" in data
        assert "tools_registered" in data
        assert "tools" in data

    def test_health_check_includes_tool_count(self, client):
        """Test health check includes correct tool count."""
        response = client.get("/mcp/health")
        data = response.json()

        assert data["tools_registered"] >= 2
        assert len(data["tools"]) == data["tools_registered"]

    def test_health_check_no_auth_required(self, mcp_server):
        """Test health check doesn't require authentication."""
        from src.core.auth import get_current_user

        adapter = MCPFastAPIAdapter(
            mcp_server=mcp_server,
            auth_dependency=get_current_user,  # Real auth
        )

        app = FastAPI()
        app.include_router(adapter.create_router())
        client = TestClient(app)

        # Health should work without token
        response = client.get("/mcp/health")
        assert response.status_code == 200


class TestSchemaExtraction:
    """Test schema extraction from tool function signatures."""

    def test_extract_input_schema_simple_types(self, adapter):
        """Test schema extraction with simple types."""
        async def sample_tool(name: str, age: int, active: bool = True):
            pass

        schema = adapter._extract_input_schema(sample_tool)

        assert schema["type"] == "object"
        assert "properties" in schema
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["age"]["type"] == "integer"
        assert schema["properties"]["active"]["type"] == "boolean"

        # Required fields (no default)
        assert "name" in schema["required"]
        assert "age" in schema["required"]
        assert "active" not in schema["required"]  # Has default

    def test_extract_input_schema_skips_context(self, adapter):
        """Test that 'ctx' parameter is skipped."""
        from fastmcp import Context

        async def sample_tool(value: str, ctx: Context = None):
            pass

        schema = adapter._extract_input_schema(sample_tool)

        assert "value" in schema["properties"]
        assert "ctx" not in schema["properties"]

    def test_python_type_to_json_type_mapping(self, adapter):
        """Test Python to JSON type mapping."""
        assert adapter._python_type_to_json_type(str) == "string"
        assert adapter._python_type_to_json_type(int) == "integer"
        assert adapter._python_type_to_json_type(float) == "number"
        assert adapter._python_type_to_json_type(bool) == "boolean"
        assert adapter._python_type_to_json_type(list) == "array"
        assert adapter._python_type_to_json_type(dict) == "object"


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_permission_error_handling(self, mcp_server, mock_auth_dependency):
        """Test that PermissionError is handled correctly."""
        @mcp_server.tool()
        async def protected_tool(value: str) -> dict:
            """Tool that checks permissions."""
            raise PermissionError("User not authorized")

        adapter = MCPFastAPIAdapter(
            mcp_server=mcp_server,
            auth_dependency=mock_auth_dependency,
        )

        app = FastAPI()
        app.include_router(adapter.create_router())
        client = TestClient(app)

        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "protected_tool",
                "payload": {"value": "test"},
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert data["error"]["code"] == "PERMISSION_DENIED"
        assert "not authorized" in data["error"]["message"].lower()

    def test_generic_exception_handling(self, mcp_server, mock_auth_dependency):
        """Test that generic exceptions are handled."""
        @mcp_server.tool()
        async def crash_tool(value: str) -> dict:
            """Tool that crashes."""
            raise RuntimeError("Unexpected error")

        adapter = MCPFastAPIAdapter(
            mcp_server=mcp_server,
            auth_dependency=mock_auth_dependency,
        )

        app = FastAPI()
        app.include_router(adapter.create_router())
        client = TestClient(app)

        response = client.post(
            "/mcp/invoke",
            json={
                "tool": "crash_tool",
                "payload": {"value": "test"},
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert data["error"]["code"] == "EXECUTION_ERROR"
        assert "RuntimeError" in data["error"]["details"]["exc_type"]
