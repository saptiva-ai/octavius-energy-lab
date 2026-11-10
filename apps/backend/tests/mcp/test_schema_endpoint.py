"""
Unit tests for MCP schema discovery endpoint.

Tests GET /api/mcp/schema/{tool_name} endpoint:
- Schema retrieval for tools
- Version resolution
- Input/Output schemas
- Example payload generation
"""

import pytest

# Mark all tests in this file with mcp and mcp_tools markers
pytestmark = [pytest.mark.mcp, pytest.mark.mcp_tools, pytest.mark.integration]
from unittest.mock import Mock
from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastmcp import FastMCP

from src.mcp_integration.fastapi_adapter import MCPFastAPIAdapter
from src.mcp_integration.versioning import versioned_registry
from src.models.user import User


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
    async def test_tool(value: str, count: int = 1, enabled: bool = True) -> dict:
        """A test tool with various parameter types."""
        return {"result": f"processed: {value} x {count}"}

    @mcp.tool()
    async def simple_tool(name: str) -> dict:
        """A simple tool with one parameter."""
        return {"greeting": f"Hello, {name}!"}

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


class TestGetToolSchema:
    """Test GET /api/mcp/schema/{tool_name} endpoint."""

    def test_get_schema_success(self, client):
        """Test retrieving schema for a tool."""
        response = client.get("/mcp/schema/test_tool")
        assert response.status_code == 200

        data = response.json()

        # Check basic structure
        assert data["tool"] == "test_tool"
        assert data["version"] == "1.0.0"
        assert "input_schema" in data
        assert "output_schema" in data
        assert "example_payload" in data
        assert "description" in data

    def test_get_schema_input_schema_structure(self, client):
        """Test input schema structure."""
        response = client.get("/mcp/schema/test_tool")
        data = response.json()

        input_schema = data["input_schema"]

        # Check JSON Schema format
        assert input_schema["type"] == "object"
        assert "properties" in input_schema
        assert "required" in input_schema

        # Check properties
        properties = input_schema["properties"]
        assert "value" in properties
        assert properties["value"]["type"] == "string"

        assert "count" in properties
        assert properties["count"]["type"] == "integer"

        assert "enabled" in properties
        assert properties["enabled"]["type"] == "boolean"

        # Check required fields
        required = input_schema["required"]
        assert "value" in required  # No default
        assert "count" not in required  # Has default
        assert "enabled" not in required  # Has default

    def test_get_schema_example_payload(self, client):
        """Test example payload generation."""
        response = client.get("/mcp/schema/test_tool")
        data = response.json()

        example = data["example_payload"]

        # Should only include required fields in minimal example
        assert "value" in example
        assert isinstance(example["value"], str)

    def test_get_schema_with_description(self, client):
        """Test that tool description is included."""
        response = client.get("/mcp/schema/test_tool")
        data = response.json()

        assert "A test tool with various parameter types" in data["description"]

    def test_get_schema_nonexistent_tool(self, client):
        """Test retrieving schema for nonexistent tool."""
        response = client.get("/mcp/schema/nonexistent_tool")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_schema_simple_tool(self, client):
        """Test schema for simple tool with one parameter."""
        response = client.get("/mcp/schema/simple_tool")
        assert response.status_code == 200

        data = response.json()
        input_schema = data["input_schema"]

        # Should have only one property
        assert len(input_schema["properties"]) == 1
        assert "name" in input_schema["properties"]
        assert input_schema["required"] == ["name"]

        # Example should have name field
        example = data["example_payload"]
        assert "name" in example


class TestGetSchemaWithVersions:
    """Test schema endpoint with versioned tools."""

    def test_get_schema_with_version_constraint(self, client):
        """Test retrieving schema for specific version."""
        # Register multiple versions
        def tool_v1():
            return "v1"

        def tool_v2():
            return "v2"

        versioned_registry.register("versioned_tool", "1.0.0", tool_v1)
        versioned_registry.register("versioned_tool", "2.0.0", tool_v2)

        # Request specific version
        response = client.get("/mcp/schema/versioned_tool?version=1.0.0")
        assert response.status_code == 200

        data = response.json()
        assert data["version"] == "1.0.0"
        assert "1.0.0" in data["available_versions"]
        assert "2.0.0" in data["available_versions"]

    def test_get_schema_latest_version(self, client):
        """Test retrieving schema without version (latest)."""
        def tool_v1():
            return "v1"

        def tool_v2():
            return "v2"

        versioned_registry.register("versioned_tool", "1.0.0", tool_v1)
        versioned_registry.register("versioned_tool", "2.0.0", tool_v2)

        response = client.get("/mcp/schema/versioned_tool")
        assert response.status_code == 200

        data = response.json()
        assert data["version"] == "2.0.0"  # Latest

    def test_get_schema_with_caret_constraint(self, client):
        """Test schema retrieval with caret constraint."""
        def tool_v1_0():
            return "v1.0"

        def tool_v1_5():
            return "v1.5"

        def tool_v2():
            return "v2"

        versioned_registry.register("versioned_tool", "1.0.0", tool_v1_0)
        versioned_registry.register("versioned_tool", "1.5.0", tool_v1_5)
        versioned_registry.register("versioned_tool", "2.0.0", tool_v2)

        # ^1.0.0 should resolve to 1.5.0 (highest 1.x.x)
        response = client.get("/mcp/schema/versioned_tool?version=^1.0.0")
        assert response.status_code == 200

        data = response.json()
        assert data["version"] == "1.5.0"

    def test_get_schema_version_not_found(self, client):
        """Test schema retrieval with nonexistent version."""
        def tool_v1():
            return "v1"

        versioned_registry.register("versioned_tool", "1.0.0", tool_v1)

        response = client.get("/mcp/schema/versioned_tool?version=^2.0.0")
        assert response.status_code == 404
        assert "No version" in response.json()["detail"]


class TestExamplePayloadGeneration:
    """Test example payload generation logic."""

    def test_generate_example_string_types(self, adapter):
        """Test example generation for string types."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string", "format": "email"},
                "url": {"type": "string", "format": "uri"},
                "date": {"type": "string", "format": "date"},
            },
            "required": ["name", "email", "url", "date"]
        }

        example = adapter._generate_example_payload(schema)

        assert example["name"] == "example_name"
        assert example["email"] == "user@example.com"
        assert example["url"] == "https://example.com"
        assert example["date"] == "2025-01-11"

    def test_generate_example_numeric_types(self, adapter):
        """Test example generation for numeric types."""
        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "price": {"type": "number"},
            },
            "required": ["count", "price"]
        }

        example = adapter._generate_example_payload(schema)

        assert example["count"] == 1
        assert example["price"] == 1.0

    def test_generate_example_boolean_type(self, adapter):
        """Test example generation for boolean type."""
        schema = {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
            },
            "required": ["enabled"]
        }

        example = adapter._generate_example_payload(schema)

        assert example["enabled"] is True

    def test_generate_example_complex_types(self, adapter):
        """Test example generation for array and object types."""
        schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array"},
                "metadata": {"type": "object"},
            },
            "required": ["tags", "metadata"]
        }

        example = adapter._generate_example_payload(schema)

        assert example["tags"] == []
        assert example["metadata"] == {}

    def test_generate_example_optional_fields_excluded(self, adapter):
        """Test that optional fields are excluded from minimal example."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "optional_field": {"type": "string"},
            },
            "required": ["name"]  # optional_field is optional
        }

        example = adapter._generate_example_payload(schema)

        assert "name" in example
        # Optional fields are skipped in minimal example
