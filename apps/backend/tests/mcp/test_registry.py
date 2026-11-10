"""Unit tests for MCP ToolRegistry."""

import pytest
import os
from src.mcp_integration.registry import ToolRegistry
from src.mcp_integration.tool import Tool
from src.mcp_integration.protocol import ToolSpec, ToolCategory, ToolCapability, ToolInvokeRequest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MCP_REGISTRY", "false").lower() != "true",
    reason="MCP registry tests deshabilitados por defecto (requires full tool stack).",
)


class MockTool(Tool):
    """Mock tool for testing."""

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="mock_tool",
            version="1.0.0",
            display_name="Mock Tool",
            description="A mock tool for testing",
            category=ToolCategory.DATA_ANALYTICS,
            capabilities=[ToolCapability.SYNC, ToolCapability.IDEMPOTENT],
            input_schema={"type": "object", "properties": {"test": {"type": "string"}}, "required": ["test"]},
            output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
            tags=["test", "mock"],
        )

    async def validate_input(self, payload):
        if "test" not in payload:
            raise ValueError("Missing required field: test")

    async def execute(self, payload, context=None):
        return {"result": f"Executed with: {payload['test']}"}


@pytest.fixture
def registry():
    """Create a fresh registry for each test."""
    return ToolRegistry()


@pytest.fixture
def mock_tool():
    """Create a mock tool instance."""
    return MockTool()


class TestToolRegistry:
    """Test suite for ToolRegistry."""

    def test_register_tool(self, registry, mock_tool):
        """Test registering a tool."""
        registry.register(mock_tool)
        assert "mock_tool" in registry._tools
        assert "1.0.0" in registry._tools["mock_tool"]

    def test_register_duplicate_tool_raises_error(self, registry, mock_tool):
        """Test that registering duplicate tool raises error."""
        registry.register(mock_tool)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(mock_tool)

    def test_unregister_tool(self, registry, mock_tool):
        """Test unregistering a tool."""
        registry.register(mock_tool)
        registry.unregister("mock_tool", "1.0.0")
        assert "mock_tool" not in registry._tools

    def test_get_tool_by_name(self, registry, mock_tool):
        """Test getting tool by name."""
        registry.register(mock_tool)
        tool = registry.get_tool("mock_tool")
        assert tool is not None
        assert tool.get_spec().name == "mock_tool"

    def test_get_tool_by_name_and_version(self, registry, mock_tool):
        """Test getting tool by name and version."""
        registry.register(mock_tool)
        tool = registry.get_tool("mock_tool", "1.0.0")
        assert tool is not None
        assert tool.get_spec().version == "1.0.0"

    def test_get_nonexistent_tool_returns_none(self, registry):
        """Test getting nonexistent tool returns None."""
        tool = registry.get_tool("nonexistent")
        assert tool is None

    def test_list_tools(self, registry, mock_tool):
        """Test listing all tools."""
        registry.register(mock_tool)
        tools = registry.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "mock_tool"

    def test_list_tools_by_category(self, registry, mock_tool):
        """Test filtering tools by category."""
        registry.register(mock_tool)
        tools = registry.list_tools(category="data_analytics")
        assert len(tools) == 1

        tools = registry.list_tools(category="compliance")
        assert len(tools) == 0

    def test_search_tools_by_name(self, registry, mock_tool):
        """Test searching tools by name."""
        registry.register(mock_tool)
        tools = registry.search_tools("mock")
        assert len(tools) == 1

    def test_search_tools_by_tag(self, registry, mock_tool):
        """Test searching tools by tag."""
        registry.register(mock_tool)
        tools = registry.search_tools("test")
        assert len(tools) == 1

    @pytest.mark.asyncio
    async def test_invoke_tool_success(self, registry, mock_tool):
        """Test successful tool invocation."""
        registry.register(mock_tool)
        request = ToolInvokeRequest(
            tool="mock_tool",
            payload={"test": "hello"},
        )
        response = await registry.invoke(request)
        assert response.success is True
        assert response.result["result"] == "Executed with: hello"

    @pytest.mark.asyncio
    async def test_invoke_tool_validation_error(self, registry, mock_tool):
        """Test tool invocation with invalid input."""
        registry.register(mock_tool)
        request = ToolInvokeRequest(
            tool="mock_tool",
            payload={},  # Missing required field
        )
        response = await registry.invoke(request)
        assert response.success is False
        assert response.error is not None
        assert response.error.code == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_invoke_nonexistent_tool(self, registry):
        """Test invoking nonexistent tool."""
        request = ToolInvokeRequest(
            tool="nonexistent",
            payload={},
        )
        response = await registry.invoke(request)
        assert response.success is False
        assert response.error is not None
        assert response.error.code == "TOOL_NOT_FOUND"
