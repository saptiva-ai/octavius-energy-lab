"""
Unit tests for MCP ToolRegistry module.

Tests tool registration, discovery, and invocation routing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.mcp_integration.registry import ToolRegistry
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
def registry():
    """Create a fresh registry instance."""
    return ToolRegistry()


def make_tool_spec(
    name: str,
    version: str = "1.0.0",
    description: str = "Test tool",
    category: ToolCategory = ToolCategory.DOCUMENT_ANALYSIS,
    tags: list = None,
) -> ToolSpec:
    """Helper to create ToolSpec with all required fields."""
    return ToolSpec(
        name=name,
        version=version,
        display_name=f"{name.replace('_', ' ').title()}",
        description=description,
        category=category,
        capabilities=[ToolCapability.SYNC],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        tags=tags or [],
    )


@pytest.fixture
def sample_tool_spec():
    """Create a sample tool spec."""
    return make_tool_spec(
        name="test_tool",
        version="1.0.0",
        description="A test tool for testing",
        category=ToolCategory.DOCUMENT_ANALYSIS,
        tags=["test", "sample", "analysis"],
    )


@pytest.fixture
def mock_tool(sample_tool_spec):
    """Create a mock tool."""
    tool = MagicMock()
    tool.get_spec.return_value = sample_tool_spec
    return tool


class TestToolRegistryInit:
    """Tests for ToolRegistry initialization."""

    def test_init_creates_empty_tools_dict(self, registry):
        """Test that registry starts with empty tools dict."""
        assert registry._tools == {}

    def test_init_multiple_instances_are_independent(self):
        """Test that multiple registry instances are independent."""
        registry1 = ToolRegistry()
        registry2 = ToolRegistry()

        mock_tool = MagicMock()
        mock_tool.get_spec.return_value = make_tool_spec("tool1")

        registry1.register(mock_tool)

        assert "tool1" in registry1._tools
        assert "tool1" not in registry2._tools


class TestRegister:
    """Tests for register method."""

    def test_register_new_tool(self, registry, mock_tool, sample_tool_spec):
        """Test registering a new tool."""
        registry.register(mock_tool)

        assert "test_tool" in registry._tools
        assert "1.0.0" in registry._tools["test_tool"]
        assert registry._tools["test_tool"]["1.0.0"] == mock_tool

    def test_register_multiple_versions(self, registry):
        """Test registering multiple versions of same tool."""
        tool_v1 = MagicMock()
        tool_v1.get_spec.return_value = make_tool_spec("multi_tool", "1.0.0")

        tool_v2 = MagicMock()
        tool_v2.get_spec.return_value = make_tool_spec("multi_tool", "2.0.0")

        registry.register(tool_v1)
        registry.register(tool_v2)

        assert "1.0.0" in registry._tools["multi_tool"]
        assert "2.0.0" in registry._tools["multi_tool"]

    def test_register_duplicate_raises_error(self, registry, mock_tool):
        """Test that registering duplicate tool+version raises ValueError."""
        registry.register(mock_tool)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(mock_tool)

    def test_register_multiple_different_tools(self, registry):
        """Test registering multiple different tools."""
        tool1 = MagicMock()
        tool1.get_spec.return_value = make_tool_spec("tool_a")

        tool2 = MagicMock()
        tool2.get_spec.return_value = make_tool_spec(
            "tool_b", category=ToolCategory.DATA_ANALYTICS
        )

        registry.register(tool1)
        registry.register(tool2)

        assert "tool_a" in registry._tools
        assert "tool_b" in registry._tools


class TestUnregister:
    """Tests for unregister method."""

    def test_unregister_specific_version(self, registry, mock_tool):
        """Test unregistering a specific version."""
        registry.register(mock_tool)
        assert "test_tool" in registry._tools

        registry.unregister("test_tool", "1.0.0")

        assert "test_tool" not in registry._tools

    def test_unregister_all_versions(self, registry):
        """Test unregistering all versions of a tool."""
        tool_v1 = MagicMock()
        tool_v1.get_spec.return_value = make_tool_spec("multi_tool", "1.0.0")

        tool_v2 = MagicMock()
        tool_v2.get_spec.return_value = make_tool_spec("multi_tool", "2.0.0")

        registry.register(tool_v1)
        registry.register(tool_v2)

        registry.unregister("multi_tool")

        assert "multi_tool" not in registry._tools

    def test_unregister_nonexistent_tool(self, registry):
        """Test unregistering a nonexistent tool doesn't raise error."""
        # Should not raise
        registry.unregister("nonexistent")

    def test_unregister_nonexistent_version(self, registry, mock_tool):
        """Test unregistering a nonexistent version doesn't raise error."""
        registry.register(mock_tool)

        # Should not raise
        registry.unregister("test_tool", "9.9.9")

        # Original version should still exist
        assert "1.0.0" in registry._tools["test_tool"]

    def test_unregister_one_version_keeps_others(self, registry):
        """Test unregistering one version keeps other versions."""
        tool_v1 = MagicMock()
        tool_v1.get_spec.return_value = make_tool_spec("multi_tool", "1.0.0")

        tool_v2 = MagicMock()
        tool_v2.get_spec.return_value = make_tool_spec("multi_tool", "2.0.0")

        registry.register(tool_v1)
        registry.register(tool_v2)

        registry.unregister("multi_tool", "1.0.0")

        assert "multi_tool" in registry._tools
        assert "1.0.0" not in registry._tools["multi_tool"]
        assert "2.0.0" in registry._tools["multi_tool"]


class TestGetTool:
    """Tests for get_tool method."""

    def test_get_tool_by_name(self, registry, mock_tool):
        """Test getting tool by name (returns latest version)."""
        registry.register(mock_tool)

        result = registry.get_tool("test_tool")

        assert result == mock_tool

    def test_get_tool_by_name_and_version(self, registry, mock_tool):
        """Test getting tool by name and specific version."""
        registry.register(mock_tool)

        result = registry.get_tool("test_tool", "1.0.0")

        assert result == mock_tool

    def test_get_tool_nonexistent(self, registry):
        """Test getting nonexistent tool returns None."""
        result = registry.get_tool("nonexistent")
        assert result is None

    def test_get_tool_nonexistent_version(self, registry, mock_tool):
        """Test getting nonexistent version returns None."""
        registry.register(mock_tool)

        result = registry.get_tool("test_tool", "9.9.9")

        assert result is None

    def test_get_tool_returns_latest_version(self, registry):
        """Test that get_tool without version returns latest."""
        tool_v1 = MagicMock()
        tool_v1.get_spec.return_value = make_tool_spec("versioned_tool", "1.0.0")

        tool_v2 = MagicMock()
        tool_v2.get_spec.return_value = make_tool_spec("versioned_tool", "2.0.0")

        registry.register(tool_v1)
        registry.register(tool_v2)

        result = registry.get_tool("versioned_tool")

        assert result == tool_v2


class TestListTools:
    """Tests for list_tools method."""

    def test_list_tools_empty(self, registry):
        """Test listing tools when registry is empty."""
        result = registry.list_tools()
        assert result == []

    def test_list_tools_all(self, registry, mock_tool, sample_tool_spec):
        """Test listing all tools."""
        registry.register(mock_tool)

        result = registry.list_tools()

        assert len(result) == 1
        assert result[0] == sample_tool_spec

    def test_list_tools_with_category_filter(self, registry):
        """Test listing tools filtered by category."""
        tool_analysis = MagicMock()
        tool_analysis.get_spec.return_value = make_tool_spec(
            "analysis_tool", category=ToolCategory.DOCUMENT_ANALYSIS
        )

        tool_data = MagicMock()
        tool_data.get_spec.return_value = make_tool_spec(
            "data_tool", category=ToolCategory.DATA_ANALYTICS
        )

        registry.register(tool_analysis)
        registry.register(tool_data)

        result = registry.list_tools(category="document_analysis")

        assert len(result) == 1
        assert result[0].name == "analysis_tool"

    def test_list_tools_multiple_versions(self, registry):
        """Test listing includes all versions."""
        tool_v1 = MagicMock()
        tool_v1.get_spec.return_value = make_tool_spec("versioned_tool", "1.0.0")

        tool_v2 = MagicMock()
        tool_v2.get_spec.return_value = make_tool_spec("versioned_tool", "2.0.0")

        registry.register(tool_v1)
        registry.register(tool_v2)

        result = registry.list_tools()

        assert len(result) == 2


class TestSearchTools:
    """Tests for search_tools method."""

    def test_search_by_name(self, registry, mock_tool):
        """Test searching tools by name."""
        registry.register(mock_tool)

        result = registry.search_tools("test")

        assert len(result) == 1
        assert result[0].name == "test_tool"

    def test_search_by_description(self, registry, mock_tool):
        """Test searching tools by description."""
        registry.register(mock_tool)

        result = registry.search_tools("testing")

        assert len(result) == 1

    def test_search_by_tag(self, registry, mock_tool, sample_tool_spec):
        """Test searching tools by tag."""
        registry.register(mock_tool)

        result = registry.search_tools("analysis")

        assert len(result) == 1

    def test_search_case_insensitive(self, registry, mock_tool):
        """Test that search is case-insensitive."""
        registry.register(mock_tool)

        result = registry.search_tools("TEST")

        assert len(result) == 1

    def test_search_no_matches(self, registry, mock_tool):
        """Test search with no matches."""
        registry.register(mock_tool)

        result = registry.search_tools("nonexistent")

        assert result == []

    def test_search_empty_registry(self, registry):
        """Test search on empty registry."""
        result = registry.search_tools("anything")
        assert result == []

    def test_search_multiple_matches(self, registry):
        """Test search returning multiple matches."""
        tool1 = MagicMock()
        tool1.get_spec.return_value = make_tool_spec(
            "data_analysis",
            description="Data analysis tool",
            tags=["data"],
        )

        tool2 = MagicMock()
        tool2.get_spec.return_value = make_tool_spec(
            "data_export",
            description="Data export tool",
            category=ToolCategory.DATA_ANALYTICS,
            tags=["data"],
        )

        registry.register(tool1)
        registry.register(tool2)

        result = registry.search_tools("data")

        assert len(result) == 2


class TestInvoke:
    """Tests for invoke method."""

    @pytest.mark.asyncio
    async def test_invoke_success(self, registry, mock_tool):
        """Test successful tool invocation."""
        expected_response = ToolInvokeResponse(
            success=True,
            tool="test_tool",
            version="1.0.0",
            result={"output": "result"},
            error=None,
            metadata={},
            invocation_id="inv-123",
            duration_ms=50.0,
            cached=False,
        )
        mock_tool.invoke = AsyncMock(return_value=expected_response)
        registry.register(mock_tool)

        request = ToolInvokeRequest(
            tool="test_tool",
            payload={"input": "test"},
            context={"user_id": "user-123"},
        )

        result = await registry.invoke(request)

        assert result == expected_response
        mock_tool.invoke.assert_awaited_once_with(
            {"input": "test"},
            {"user_id": "user-123"},
        )

    @pytest.mark.asyncio
    async def test_invoke_tool_not_found(self, registry):
        """Test invoking nonexistent tool."""
        request = ToolInvokeRequest(
            tool="nonexistent",
            payload={},
        )

        result = await registry.invoke(request)

        assert result.success is False
        assert result.error.code == ErrorCode.TOOL_NOT_FOUND
        assert "nonexistent" in result.error.message

    @pytest.mark.asyncio
    async def test_invoke_with_version(self, registry):
        """Test invoking specific tool version."""
        tool_v1 = MagicMock()
        tool_v1.get_spec.return_value = make_tool_spec("versioned_tool", "1.0.0")
        tool_v1.invoke = AsyncMock(
            return_value=ToolInvokeResponse(
                success=True,
                tool="versioned_tool",
                version="1.0.0",
                result={"version": "1"},
                error=None,
                metadata={},
                invocation_id="inv-1",
                duration_ms=10.0,
                cached=False,
            )
        )

        tool_v2 = MagicMock()
        tool_v2.get_spec.return_value = make_tool_spec("versioned_tool", "2.0.0")
        tool_v2.invoke = AsyncMock(
            return_value=ToolInvokeResponse(
                success=True,
                tool="versioned_tool",
                version="2.0.0",
                result={"version": "2"},
                error=None,
                metadata={},
                invocation_id="inv-2",
                duration_ms=10.0,
                cached=False,
            )
        )

        registry.register(tool_v1)
        registry.register(tool_v2)

        request = ToolInvokeRequest(
            tool="versioned_tool",
            version="1.0.0",
            payload={},
        )

        result = await registry.invoke(request)

        assert result.result["version"] == "1"
        tool_v1.invoke.assert_awaited_once()
        tool_v2.invoke.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invoke_returns_available_tools_on_error(self, registry, mock_tool):
        """Test that error response includes available tools."""
        registry.register(mock_tool)

        request = ToolInvokeRequest(
            tool="nonexistent",
            payload={},
        )

        result = await registry.invoke(request)

        assert "available_tools" in result.error.details
        assert "test_tool" in result.error.details["available_tools"]
