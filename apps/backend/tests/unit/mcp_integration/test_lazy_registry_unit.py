"""
Unit tests for LazyToolRegistry.

Tests tool discovery, loading, and caching behavior.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from pathlib import Path
import tempfile
import os


class TestToolMetadata:
    """Test ToolMetadata class."""

    def test_metadata_creation_defaults(self):
        """Test metadata with defaults."""
        from src.mcp_integration.lazy_registry import ToolMetadata

        metadata = ToolMetadata(
            name="test_tool",
            module_path="src.mcp_integration.tools.test_tool",
            class_name="TestToolTool",
        )

        assert metadata.name == "test_tool"
        assert metadata.module_path == "src.mcp_integration.tools.test_tool"
        assert metadata.class_name == "TestToolTool"
        assert metadata.category == "general"
        assert metadata.description == "Tool: test_tool"
        assert metadata._loaded is False
        assert metadata._instance is None

    def test_metadata_creation_with_custom_values(self):
        """Test metadata with custom values."""
        from src.mcp_integration.lazy_registry import ToolMetadata

        metadata = ToolMetadata(
            name="my_tool",
            module_path="my.module.path",
            class_name="MyToolClass",
            category="analytics",
            description="My custom description",
        )

        assert metadata.name == "my_tool"
        assert metadata.category == "analytics"
        assert metadata.description == "My custom description"


class TestLazyToolRegistryInit:
    """Test LazyToolRegistry initialization."""

    def test_init_with_default_directory(self):
        """Test initialization with default tools directory."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        registry = LazyToolRegistry()

        assert registry.tools_directory is not None
        assert isinstance(registry._metadata_cache, dict)
        assert isinstance(registry._loaded_tools, dict)

    def test_init_with_custom_directory(self):
        """Test initialization with custom tools directory."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = Path(tmpdir)
            registry = LazyToolRegistry(tools_directory=custom_path)

            assert registry.tools_directory == custom_path

    def test_init_scans_tools_directory(self):
        """Test that init scans tools directory."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some fake tool files
            tools_dir = Path(tmpdir)
            (tools_dir / "test_tool.py").touch()
            (tools_dir / "another_tool.py").touch()
            (tools_dir / "__init__.py").touch()  # Should be skipped
            (tools_dir / "_private.py").touch()  # Should be skipped

            registry = LazyToolRegistry(tools_directory=tools_dir)

            # Should have discovered 2 tools (not __init__ or _private)
            assert len(registry._metadata_cache) == 2
            assert "test_tool" in registry._metadata_cache
            assert "another_tool" in registry._metadata_cache


class TestInferClassName:
    """Test _infer_class_name method."""

    def test_simple_name(self):
        """Test inferring class name from simple name."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            result = registry._infer_class_name("audit")
            assert result == "AuditTool"

    def test_underscored_name(self):
        """Test inferring class name from underscored name."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            result = registry._infer_class_name("excel_analyzer")
            assert result == "ExcelAnalyzerTool"

    def test_name_already_has_tool_suffix(self):
        """Test name that already has Tool suffix."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            result = registry._infer_class_name("deep_research_tool")
            assert result == "DeepResearchTool"  # Should not add double Tool


class TestInferCategory:
    """Test _infer_category method."""

    def test_excel_category(self):
        """Test excel tools get analytics category."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            assert registry._infer_category("excel_analyzer") == "analytics"

    def test_viz_category(self):
        """Test viz tools get analytics category."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            assert registry._infer_category("viz_tool") == "analytics"

    def test_research_category(self):
        """Test research tools get research category."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            assert registry._infer_category("deep_research") == "research"

    def test_document_category(self):
        """Test document tools get document_analysis category."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            assert registry._infer_category("document_extraction") == "document_analysis"
            assert registry._infer_category("extract_text") == "document_analysis"

    def test_default_category(self):
        """Test unknown tools get general category."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            assert registry._infer_category("unknown_tool") == "general"


class TestDiscoverTools:
    """Test discover_tools method."""

    @pytest.fixture
    def registry_with_tools(self):
        """Create registry with some tools."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry, ToolMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            # Manually add metadata
            registry._metadata_cache = {
                "excel_analyzer": ToolMetadata(
                    name="excel_analyzer",
                    module_path="test.excel_analyzer",
                    class_name="ExcelAnalyzerTool",
                    category="analytics",
                    description="Analyze Excel files",
                ),
                "audit_file": ToolMetadata(
                    name="audit_file",
                    module_path="test.audit_file",
                    class_name="AuditFileTool",
                    category="compliance",
                    description="Audit compliance documents",
                ),
                "viz_tool": ToolMetadata(
                    name="viz_tool",
                    module_path="test.viz_tool",
                    class_name="VizToolTool",
                    category="analytics",
                    description="Create visualizations",
                ),
            }

            yield registry

    def test_discover_all_tools(self, registry_with_tools):
        """Test discovering all tools."""
        tools = registry_with_tools.discover_tools()

        assert len(tools) == 3
        tool_names = [t["name"] for t in tools]
        assert "excel_analyzer" in tool_names
        assert "audit_file" in tool_names
        assert "viz_tool" in tool_names

    def test_discover_by_category(self, registry_with_tools):
        """Test discovering tools by category."""
        tools = registry_with_tools.discover_tools(category="analytics")

        assert len(tools) == 2
        assert all(t["category"] == "analytics" for t in tools)

    def test_discover_with_search_query_name(self, registry_with_tools):
        """Test discovering tools with name search."""
        tools = registry_with_tools.discover_tools(search_query="excel")

        assert len(tools) == 1
        assert tools[0]["name"] == "excel_analyzer"

    def test_discover_with_search_query_description(self, registry_with_tools):
        """Test discovering tools with description search."""
        tools = registry_with_tools.discover_tools(search_query="compliance")

        assert len(tools) == 1
        assert tools[0]["name"] == "audit_file"

    def test_discover_returns_minimal_info(self, registry_with_tools):
        """Test that discovery returns minimal metadata."""
        tools = registry_with_tools.discover_tools()

        for tool in tools:
            assert "name" in tool
            assert "category" in tool
            assert "description" in tool
            assert "loaded" in tool
            # Should NOT have heavy attributes
            assert "input_schema" not in tool
            assert "output_schema" not in tool


class TestLoadTool:
    """Test load_tool method."""

    @pytest.fixture
    def registry(self):
        """Create registry for testing."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry, ToolMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            # Add metadata for a tool
            registry._metadata_cache["test_tool"] = ToolMetadata(
                name="test_tool",
                module_path="src.mcp_integration.tools.test_tool",
                class_name="TestToolTool",
            )

            yield registry

    @pytest.mark.asyncio
    async def test_load_tool_caches_result(self, registry):
        """Test that loaded tools are cached."""
        mock_tool = MagicMock()
        mock_module = MagicMock()
        mock_module.TestToolTool.return_value = mock_tool

        with patch("importlib.import_module", return_value=mock_module):
            # First load
            tool1 = await registry.load_tool("test_tool")
            # Second load (should use cache)
            tool2 = await registry.load_tool("test_tool")

            assert tool1 is tool2
            # import_module should only be called once
            assert mock_tool == tool1

    @pytest.mark.asyncio
    async def test_load_nonexistent_tool(self, registry):
        """Test loading non-existent tool returns None."""
        tool = await registry.load_tool("nonexistent_tool")

        assert tool is None

    @pytest.mark.asyncio
    async def test_load_tool_marks_as_loaded(self, registry):
        """Test that loading marks metadata as loaded."""
        mock_tool = MagicMock()
        mock_module = MagicMock()
        mock_module.TestToolTool.return_value = mock_tool

        with patch("importlib.import_module", return_value=mock_module):
            await registry.load_tool("test_tool")

            metadata = registry._metadata_cache["test_tool"]
            assert metadata._loaded is True
            assert metadata._instance is mock_tool

    @pytest.mark.asyncio
    async def test_load_tool_handles_import_error(self, registry):
        """Test loading handles import errors."""
        with patch(
            "importlib.import_module", side_effect=ImportError("Module not found")
        ):
            tool = await registry.load_tool("test_tool")

            assert tool is None


class TestGetToolSpec:
    """Test get_tool_spec method."""

    @pytest.fixture
    def registry(self):
        """Create registry for testing."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry, ToolMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))
            registry._metadata_cache["test_tool"] = ToolMetadata(
                name="test_tool",
                module_path="test.module",
                class_name="TestTool",
            )
            yield registry

    @pytest.mark.asyncio
    async def test_get_tool_spec_loads_and_returns_spec(self, registry):
        """Test getting tool spec loads tool and returns spec."""
        mock_spec = MagicMock()
        mock_tool = MagicMock()
        mock_tool.get_spec.return_value = mock_spec

        mock_module = MagicMock()
        mock_module.TestTool.return_value = mock_tool

        with patch("importlib.import_module", return_value=mock_module):
            spec = await registry.get_tool_spec("test_tool")

            assert spec == mock_spec
            mock_tool.get_spec.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tool_spec_nonexistent_returns_none(self, registry):
        """Test getting spec for non-existent tool returns None."""
        spec = await registry.get_tool_spec("nonexistent_tool")

        assert spec is None


class TestInvoke:
    """Test invoke method."""

    @pytest.fixture
    def registry(self):
        """Create registry for testing."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry, ToolMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))
            registry._metadata_cache["test_tool"] = ToolMetadata(
                name="test_tool",
                module_path="test.module",
                class_name="TestTool",
            )
            yield registry

    @pytest.mark.asyncio
    async def test_invoke_loads_and_calls_tool(self, registry):
        """Test invoke loads tool and calls invoke."""
        from src.mcp_integration.protocol import ToolInvokeRequest

        mock_response = MagicMock()
        mock_tool = MagicMock()
        mock_tool.invoke = AsyncMock(return_value=mock_response)

        mock_module = MagicMock()
        mock_module.TestTool.return_value = mock_tool

        request = ToolInvokeRequest(
            tool="test_tool",
            payload={"key": "value"},
            context={"user_id": "123"},
        )

        with patch("importlib.import_module", return_value=mock_module):
            response = await registry.invoke(request)

            assert response == mock_response
            mock_tool.invoke.assert_called_once_with({"key": "value"}, {"user_id": "123"})

    @pytest.mark.asyncio
    async def test_invoke_nonexistent_tool_returns_error(self, registry):
        """Test invoking non-existent tool returns error response."""
        from src.mcp_integration.protocol import ToolInvokeRequest

        request = ToolInvokeRequest(
            tool="nonexistent_tool",
            payload={},
        )

        response = await registry.invoke(request)

        assert response.success is False
        assert response.error is not None
        assert response.error.code == "TOOL_NOT_FOUND"
        assert "nonexistent_tool" in response.error.message


class TestRegistryStats:
    """Test get_registry_stats and count methods."""

    def test_get_loaded_tools_count(self):
        """Test get_loaded_tools_count method."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))
            registry._loaded_tools = {"tool1": MagicMock(), "tool2": MagicMock()}

            assert registry.get_loaded_tools_count() == 2

    def test_get_discovered_tools_count(self):
        """Test get_discovered_tools_count method."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry, ToolMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))
            registry._metadata_cache = {
                "tool1": MagicMock(),
                "tool2": MagicMock(),
                "tool3": MagicMock(),
            }

            assert registry.get_discovered_tools_count() == 3

    def test_get_registry_stats(self):
        """Test get_registry_stats method."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry, ToolMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))
            registry._metadata_cache = {
                "tool1": MagicMock(),
                "tool2": MagicMock(),
            }
            registry._loaded_tools = {"tool1": MagicMock()}

            stats = registry.get_registry_stats()

            assert stats["tools_discovered"] == 2
            assert stats["tools_loaded"] == 1
            assert "tool1" in stats["tools_available"]
            assert "tool2" in stats["tools_available"]
            assert stats["tools_loaded_list"] == ["tool1"]
            assert "50.0%" in stats["memory_efficiency"]


class TestUnloadTool:
    """Test unload_tool method."""

    def test_unload_loaded_tool(self):
        """Test unloading a loaded tool."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry, ToolMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            mock_tool = MagicMock()
            metadata = ToolMetadata(
                name="test_tool",
                module_path="test.module",
                class_name="TestTool",
            )
            metadata._loaded = True
            metadata._instance = mock_tool

            registry._metadata_cache["test_tool"] = metadata
            registry._loaded_tools["test_tool"] = mock_tool

            result = registry.unload_tool("test_tool")

            assert result is True
            assert "test_tool" not in registry._loaded_tools
            assert metadata._loaded is False
            assert metadata._instance is None

    def test_unload_not_loaded_tool(self):
        """Test unloading a tool that isn't loaded."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LazyToolRegistry(tools_directory=Path(tmpdir))

            result = registry.unload_tool("not_loaded_tool")

            assert result is False


class TestGetLazyRegistry:
    """Test get_lazy_registry singleton function."""

    def test_get_lazy_registry_returns_instance(self):
        """Test get_lazy_registry returns instance."""
        from src.mcp_integration.lazy_registry import get_lazy_registry

        registry = get_lazy_registry()

        assert registry is not None

    def test_get_lazy_registry_returns_same_instance(self):
        """Test get_lazy_registry returns same instance."""
        from src.mcp_integration.lazy_registry import get_lazy_registry

        registry1 = get_lazy_registry()
        registry2 = get_lazy_registry()

        assert registry1 is registry2


class TestScanToolsDirectory:
    """Test _scan_tools_directory method."""

    def test_nonexistent_directory_logs_warning(self):
        """Test scanning non-existent directory logs warning."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        # Create with non-existent directory
        registry = LazyToolRegistry(tools_directory=Path("/nonexistent/path"))

        # Should not raise, just warn
        assert len(registry._metadata_cache) == 0

    def test_skips_files_starting_with_underscore(self):
        """Test that files starting with _ are skipped."""
        from src.mcp_integration.lazy_registry import LazyToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            (tools_dir / "valid_tool.py").touch()
            (tools_dir / "_private_tool.py").touch()
            (tools_dir / "__init__.py").touch()

            registry = LazyToolRegistry(tools_directory=tools_dir)

            assert len(registry._metadata_cache) == 1
            assert "valid_tool" in registry._metadata_cache
