"""
Tests for LazyToolRegistry - On-demand tool loading.

Tests verify:
- Tool discovery without loading
- Lazy loading on-demand
- Caching of loaded tools
- Memory efficiency
- Tool unloading
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import importlib
import os

from src.mcp_integration.lazy_registry import LazyToolRegistry, ToolMetadata, get_lazy_registry
from src.mcp_integration.protocol import ToolInvokeRequest, ToolCategory

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MCP_LAZY_REGISTRY", "false").lower() != "true",
    reason="MCP lazy registry tests deshabilitados por defecto (requires tool metadata).",
)


class TestToolMetadata:
    """Test ToolMetadata class."""

    def test_create_metadata(self):
        """Test creating tool metadata."""
        metadata = ToolMetadata(
            name="test_tool",
            module_path="src.mcp_integration.tools.test_tool",
            class_name="TestTool",
            category="general",
            description="Test tool description"
        )

        assert metadata.name == "test_tool"
        assert metadata.module_path == "src.mcp_integration.tools.test_tool"
        assert metadata.class_name == "TestTool"
        assert metadata.category == "general"
        assert metadata.description == "Test tool description"
        assert metadata._loaded is False
        assert metadata._instance is None

    def test_metadata_defaults(self):
        """Test metadata default values."""
        metadata = ToolMetadata(
            name="test_tool",
            module_path="src.mcp_integration.tools.test_tool",
            class_name="TestTool"
        )

        assert metadata.category == "general"
        assert metadata.description == "Tool: test_tool"


class TestLazyToolRegistry:
    """Test LazyToolRegistry class."""

    @pytest.fixture
    def mock_tools_directory(self, tmp_path):
        """Create a mock tools directory with test files."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        # Create test tool files
        (tools_dir / "excel_analyzer.py").write_text("# Mock audit tool")
        (tools_dir / "excel_analyzer.py").write_text("# Mock excel tool")
        (tools_dir / "deep_research.py").write_text("# Mock research tool")
        (tools_dir / "__init__.py").write_text("# Init file")
        (tools_dir / "_private.py").write_text("# Private file")

        return tools_dir

    @pytest.fixture
    def registry(self, mock_tools_directory):
        """Create registry with mock tools directory."""
        return LazyToolRegistry(tools_directory=mock_tools_directory)

    def test_initialization(self, registry):
        """Test registry initialization."""
        assert registry.tools_directory.exists()
        assert isinstance(registry._metadata_cache, dict)
        assert isinstance(registry._loaded_tools, dict)

    def test_scan_tools_directory(self, registry):
        """Test scanning tools directory."""
        # Should discover 3 tools (ignoring __init__.py and _private.py)
        assert len(registry._metadata_cache) == 3
        assert "excel_analyzer" in registry._metadata_cache
        assert "excel_analyzer" in registry._metadata_cache
        assert "deep_research" in registry._metadata_cache

        # Should not include private or init files
        assert "__init__" not in registry._metadata_cache
        assert "_private" not in registry._metadata_cache

    def test_infer_class_name(self, registry):
        """Test class name inference."""
        assert registry._infer_class_name("excel_analyzer") == "AuditFileTool"
        assert registry._infer_class_name("excel_analyzer") == "ExcelAnalyzerTool"
        assert registry._infer_class_name("deep_research") == "DeepResearchTool"
        assert registry._infer_class_name("viz_tool") == "VizTool"

    def test_infer_category(self, registry):
        """Test category inference."""
        assert registry._infer_category("excel_analyzer") == "compliance"
        assert registry._infer_category("validate_doc") == "compliance"
        assert registry._infer_category("excel_analyzer") == "analytics"
        assert registry._infer_category("viz_tool") == "analytics"
        assert registry._infer_category("deep_research") == "research"
        assert registry._infer_category("extract_document") == "document_analysis"
        assert registry._infer_category("unknown_tool") == "general"

    def test_discover_tools_no_filters(self, registry):
        """Test discovering all tools."""
        tools = registry.discover_tools()

        assert len(tools) == 3
        assert all("name" in tool for tool in tools)
        assert all("category" in tool for tool in tools)
        assert all("description" in tool for tool in tools)
        assert all("loaded" in tool for tool in tools)
        assert all(tool["loaded"] is False for tool in tools)

    def test_discover_tools_with_category_filter(self, registry):
        """Test discovering tools by category."""
        # Compliance tools
        compliance_tools = registry.discover_tools(category="compliance")
        assert len(compliance_tools) == 1
        assert compliance_tools[0]["name"] == "excel_analyzer"

        # Analytics tools
        analytics_tools = registry.discover_tools(category="analytics")
        assert len(analytics_tools) == 1
        assert analytics_tools[0]["name"] == "excel_analyzer"

        # Research tools
        research_tools = registry.discover_tools(category="research")
        assert len(research_tools) == 1
        assert research_tools[0]["name"] == "deep_research"

    def test_discover_tools_with_search_query(self, registry):
        """Test discovering tools by search query."""
        # Search by name
        results = registry.discover_tools(search_query="audit")
        assert len(results) == 1
        assert results[0]["name"] == "excel_analyzer"

        # Search by name (partial match)
        results = registry.discover_tools(search_query="excel")
        assert len(results) == 1
        assert results[0]["name"] == "excel_analyzer"

        # No matches
        results = registry.discover_tools(search_query="nonexistent")
        assert len(results) == 0

    def test_discover_tools_minimal_metadata(self, registry):
        """Test that discover returns minimal metadata."""
        tools = registry.discover_tools()

        # Should only have 4 fields per tool
        for tool in tools:
            assert set(tool.keys()) == {"name", "category", "description", "loaded"}

        # Estimate size (should be ~50 bytes per tool)
        import json
        json_size = len(json.dumps(tools))
        avg_size_per_tool = json_size / len(tools)
        assert avg_size_per_tool < 100, "Metadata should be minimal (<100 bytes per tool)"

    @pytest.mark.asyncio
    async def test_load_tool_success(self, registry):
        """Test loading a tool successfully."""
        # Mock the tool module and class
        mock_tool_instance = Mock()
        mock_tool_class = Mock(return_value=mock_tool_instance)
        mock_module = Mock()
        mock_module.AuditFileTool = mock_tool_class

        with patch.object(importlib, "import_module", return_value=mock_module):
            tool = await registry.load_tool("excel_analyzer")

            assert tool is mock_tool_instance
            assert "excel_analyzer" in registry._loaded_tools
            assert registry._metadata_cache["excel_analyzer"]._loaded is True
            assert registry._metadata_cache["excel_analyzer"]._instance is mock_tool_instance

    @pytest.mark.asyncio
    async def test_load_tool_cache_hit(self, registry):
        """Test loading a tool that's already cached."""
        # Mock first load
        mock_tool_instance = Mock()
        mock_tool_class = Mock(return_value=mock_tool_instance)
        mock_module = Mock()
        mock_module.AuditFileTool = mock_tool_class

        with patch.object(importlib, "import_module", return_value=mock_module) as mock_import:
            # First load
            tool1 = await registry.load_tool("excel_analyzer")

            # Second load (should use cache)
            tool2 = await registry.load_tool("excel_analyzer")

            assert tool1 is tool2
            # Import should only be called once
            assert mock_import.call_count == 1

    @pytest.mark.asyncio
    async def test_load_tool_not_found(self, registry):
        """Test loading a non-existent tool."""
        tool = await registry.load_tool("nonexistent_tool")
        assert tool is None

    @pytest.mark.asyncio
    async def test_load_tool_import_error(self, registry):
        """Test handling import errors."""
        with patch.object(importlib, "import_module", side_effect=ImportError("Module not found")):
            tool = await registry.load_tool("excel_analyzer")
            assert tool is None
            assert "excel_analyzer" not in registry._loaded_tools

    @pytest.mark.asyncio
    async def test_load_tool_attribute_error(self, registry):
        """Test handling missing class in module."""
        mock_module = Mock(spec=[])  # Module without AuditFileTool attribute

        with patch.object(importlib, "import_module", return_value=mock_module):
            tool = await registry.load_tool("excel_analyzer")
            assert tool is None

    @pytest.mark.asyncio
    async def test_get_tool_spec(self, registry):
        """Test getting tool specification."""
        # Mock tool with spec
        mock_spec = Mock()
        mock_tool_instance = Mock()
        mock_tool_instance.get_spec.return_value = mock_spec
        mock_tool_class = Mock(return_value=mock_tool_instance)
        mock_module = Mock()
        mock_module.AuditFileTool = mock_tool_class

        with patch.object(importlib, "import_module", return_value=mock_module):
            spec = await registry.get_tool_spec("excel_analyzer")
            assert spec is mock_spec
            mock_tool_instance.get_spec.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tool_spec_not_found(self, registry):
        """Test getting spec for non-existent tool."""
        spec = await registry.get_tool_spec("nonexistent_tool")
        assert spec is None

    @pytest.mark.asyncio
    async def test_invoke_success(self, registry):
        """Test invoking a tool successfully."""
        # Mock tool with invoke method
        mock_response = Mock()
        mock_tool_instance = Mock()
        mock_tool_instance.invoke.return_value = mock_response
        mock_tool_class = Mock(return_value=mock_tool_instance)
        mock_module = Mock()
        mock_module.AuditFileTool = mock_tool_class

        request = ToolInvokeRequest(
            tool="excel_analyzer",
            payload={"doc_id": "123"},
            context={"user_id": "user123"}
        )

        with patch.object(importlib, "import_module", return_value=mock_module):
            response = await registry.invoke(request)

            assert response is mock_response
            mock_tool_instance.invoke.assert_called_once_with(
                request.payload,
                request.context
            )

    @pytest.mark.asyncio
    async def test_invoke_tool_not_found(self, registry):
        """Test invoking non-existent tool."""
        request = ToolInvokeRequest(
            tool="nonexistent_tool",
            payload={},
            context={}
        )

        response = await registry.invoke(request)

        assert response.success is False
        assert response.error is not None
        assert response.error.code == "TOOL_NOT_FOUND"
        assert "nonexistent_tool" in response.error.message
        assert "available_tools" in response.error.details

    def test_get_loaded_tools_count(self, registry):
        """Test getting count of loaded tools."""
        assert registry.get_loaded_tools_count() == 0

        # Simulate loading a tool
        registry._loaded_tools["excel_analyzer"] = Mock()
        assert registry.get_loaded_tools_count() == 1

        registry._loaded_tools["excel_analyzer"] = Mock()
        assert registry.get_loaded_tools_count() == 2

    def test_get_discovered_tools_count(self, registry):
        """Test getting count of discovered tools."""
        assert registry.get_discovered_tools_count() == 3

    def test_unload_tool_success(self, registry):
        """Test unloading a loaded tool."""
        # Load a tool first
        mock_tool = Mock()
        registry._loaded_tools["excel_analyzer"] = mock_tool
        registry._metadata_cache["excel_analyzer"]._loaded = True
        registry._metadata_cache["excel_analyzer"]._instance = mock_tool

        # Unload it
        result = registry.unload_tool("excel_analyzer")

        assert result is True
        assert "excel_analyzer" not in registry._loaded_tools
        assert registry._metadata_cache["excel_analyzer"]._loaded is False
        assert registry._metadata_cache["excel_analyzer"]._instance is None

    def test_unload_tool_not_loaded(self, registry):
        """Test unloading a tool that's not loaded."""
        result = registry.unload_tool("excel_analyzer")
        assert result is False

    def test_unload_tool_unknown(self, registry):
        """Test unloading unknown tool."""
        result = registry.unload_tool("nonexistent_tool")
        assert result is False

    def test_get_registry_stats(self, registry):
        """Test getting registry statistics."""
        # Load one tool
        registry._loaded_tools["excel_analyzer"] = Mock()

        stats = registry.get_registry_stats()

        assert stats["tools_discovered"] == 3
        assert stats["tools_loaded"] == 1
        assert len(stats["tools_available"]) == 3
        assert len(stats["tools_loaded_list"]) == 1
        assert "excel_analyzer" in stats["tools_loaded_list"]
        assert "memory_efficiency" in stats
        # Should be ~66.7% efficient (1/3 loaded)
        assert "66" in stats["memory_efficiency"]

    def test_memory_efficiency_calculation(self, registry):
        """Test memory efficiency calculation."""
        # No tools loaded = 100% efficient
        stats = registry.get_registry_stats()
        assert stats["memory_efficiency"] == "100.0%"

        # 1 tool loaded = 66.7% efficient
        registry._loaded_tools["excel_analyzer"] = Mock()
        stats = registry.get_registry_stats()
        assert "66" in stats["memory_efficiency"]

        # All tools loaded = 0% efficient
        registry._loaded_tools["excel_analyzer"] = Mock()
        registry._loaded_tools["deep_research"] = Mock()
        stats = registry.get_registry_stats()
        assert stats["memory_efficiency"] == "0.0%"


class TestGlobalRegistry:
    """Test global registry singleton."""

    def test_get_lazy_registry_singleton(self):
        """Test that get_lazy_registry returns singleton."""
        # Reset global registry
        import src.mcp_integration.lazy_registry as registry_module
        registry_module._lazy_registry = None

        # Get registry twice
        registry1 = get_lazy_registry()
        registry2 = get_lazy_registry()

        assert registry1 is registry2

    def test_get_lazy_registry_creates_default(self):
        """Test that get_lazy_registry creates default registry."""
        import src.mcp_integration.lazy_registry as registry_module
        registry_module._lazy_registry = None

        registry = get_lazy_registry()

        assert isinstance(registry, LazyToolRegistry)
        assert registry.tools_directory.name == "tools"


class TestLazyLoadingOptimization:
    """Test optimization benefits of lazy loading."""

    @pytest.fixture
    def registry(self, tmp_path):
        """Create registry with multiple tools."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        # Create 20 mock tools
        for i in range(20):
            (tools_dir / f"tool_{i:02d}.py").write_text(f"# Mock tool {i}")

        return LazyToolRegistry(tools_directory=tools_dir)

    def test_discovery_is_lightweight(self, registry):
        """Test that discovery doesn't load tools."""
        tools = registry.discover_tools()

        # All 20 tools discovered
        assert len(tools) == 20

        # But none are loaded
        assert all(tool["loaded"] is False for tool in tools)
        assert registry.get_loaded_tools_count() == 0

        # Metadata is minimal
        import json
        json_size = len(json.dumps(tools))
        # Should be ~1KB for 20 tools (vs ~100KB if all loaded)
        assert json_size < 2000, f"Metadata too large: {json_size} bytes"

    @pytest.mark.asyncio
    async def test_on_demand_loading(self, registry):
        """Test that tools are only loaded when invoked."""
        # Mock tool
        mock_tool_instance = Mock()
        mock_tool_class = Mock(return_value=mock_tool_instance)
        mock_module = Mock()
        setattr(mock_module, "Tool_00Tool", mock_tool_class)

        with patch.object(importlib, "import_module", return_value=mock_module):
            # Discover tools (lightweight)
            tools = registry.discover_tools()
            assert registry.get_loaded_tools_count() == 0

            # Load specific tool
            await registry.load_tool("tool_00")
            assert registry.get_loaded_tools_count() == 1

            # Other tools still not loaded
            assert registry.get_loaded_tools_count() == 1

    def test_memory_efficiency_with_many_tools(self, registry):
        """Test memory efficiency with many tools."""
        # Load only 2 out of 20 tools
        registry._loaded_tools["tool_00"] = Mock()
        registry._loaded_tools["tool_01"] = Mock()

        stats = registry.get_registry_stats()

        assert stats["tools_discovered"] == 20
        assert stats["tools_loaded"] == 2
        # Should be 90% efficient (18/20 not loaded)
        assert "90" in stats["memory_efficiency"]
