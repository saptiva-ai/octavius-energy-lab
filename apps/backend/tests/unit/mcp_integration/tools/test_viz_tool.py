"""
Unit tests for VizTool - Data Visualization Generator.

Tests chart specification generation for Plotly and ECharts.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.mcp_integration.tools.viz_tool import VizTool
from src.mcp_integration.protocol import ToolCategory, ToolCapability


@pytest.fixture
def viz_tool():
    """Create VizTool instance."""
    return VizTool()


@pytest.fixture
def sample_data():
    """Sample data for chart generation."""
    return [
        {"month": "Jan", "sales": 100, "profit": 20},
        {"month": "Feb", "sales": 150, "profit": 35},
        {"month": "Mar", "sales": 200, "profit": 50},
        {"month": "Apr", "sales": 180, "profit": 40},
    ]


class TestVizToolSpec:
    """Tests for VizTool specification."""

    def test_get_spec_returns_tool_spec(self, viz_tool):
        """Test get_spec returns valid ToolSpec."""
        spec = viz_tool.get_spec()

        assert spec.name == "viz_tool"
        assert spec.version == "1.0.0"
        assert spec.display_name == "Data Visualization Generator"
        assert spec.category == ToolCategory.VISUALIZATION

    def test_spec_capabilities(self, viz_tool):
        """Test tool capabilities are correct."""
        spec = viz_tool.get_spec()

        assert ToolCapability.SYNC in spec.capabilities
        assert ToolCapability.IDEMPOTENT in spec.capabilities
        assert ToolCapability.CACHEABLE in spec.capabilities

    def test_spec_input_schema(self, viz_tool):
        """Test input schema structure."""
        spec = viz_tool.get_spec()
        schema = spec.input_schema

        assert schema["type"] == "object"
        assert "chart_type" in schema["properties"]
        assert "data_source" in schema["properties"]
        assert "chart_type" in schema["required"]
        assert "data_source" in schema["required"]

    def test_spec_chart_types(self, viz_tool):
        """Test supported chart types."""
        spec = viz_tool.get_spec()
        chart_types = spec.input_schema["properties"]["chart_type"]["enum"]

        assert "bar" in chart_types
        assert "line" in chart_types
        assert "pie" in chart_types
        assert "scatter" in chart_types
        assert "heatmap" in chart_types
        assert "histogram" in chart_types

    def test_spec_libraries(self, viz_tool):
        """Test supported libraries."""
        spec = viz_tool.get_spec()
        libraries = spec.input_schema["properties"]["library"]["enum"]

        assert "plotly" in libraries
        assert "echarts" in libraries

    def test_spec_rate_limit(self, viz_tool):
        """Test rate limit is configured."""
        spec = viz_tool.get_spec()

        assert spec.rate_limit["calls_per_minute"] == 30

    def test_spec_timeout(self, viz_tool):
        """Test timeout is configured."""
        spec = viz_tool.get_spec()

        assert spec.timeout_ms == 15000


class TestVizToolValidateInput:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_valid_input(self, viz_tool):
        """Test valid input passes validation."""
        payload = {
            "chart_type": "bar",
            "data_source": {"type": "inline", "data": []},
        }

        # Should not raise
        await viz_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_missing_chart_type(self, viz_tool):
        """Test validation fails without chart_type."""
        payload = {"data_source": {"type": "inline", "data": []}}

        with pytest.raises(ValueError, match="Missing required field: chart_type"):
            await viz_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_missing_data_source(self, viz_tool):
        """Test validation fails without data_source."""
        payload = {"chart_type": "bar"}

        with pytest.raises(ValueError, match="Missing required field: data_source"):
            await viz_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_missing_data_source_type(self, viz_tool):
        """Test validation fails without data_source.type."""
        payload = {
            "chart_type": "bar",
            "data_source": {"data": []},
        }

        with pytest.raises(ValueError, match="Missing required field: data_source.type"):
            await viz_tool.validate_input(payload)


class TestVizToolExecute:
    """Tests for tool execution."""

    @pytest.mark.asyncio
    async def test_execute_with_inline_data_plotly(self, viz_tool, sample_data):
        """Test execution with inline data and Plotly library."""
        payload = {
            "chart_type": "bar",
            "data_source": {"type": "inline", "data": sample_data},
            "x_column": "month",
            "y_column": "sales",
            "title": "Monthly Sales",
            "library": "plotly",
        }

        result = await viz_tool.execute(payload, context={"user_id": "user-123"})

        assert result["library"] == "plotly"
        assert "spec" in result
        assert result["spec"]["data"][0]["type"] == "bar"
        assert result["preview_data"] == sample_data[:10]
        assert result["metadata"]["data_points"] == 4
        assert "month" in result["metadata"]["columns"]

    @pytest.mark.asyncio
    async def test_execute_with_inline_data_echarts(self, viz_tool, sample_data):
        """Test execution with inline data and ECharts library."""
        payload = {
            "chart_type": "bar",
            "data_source": {"type": "inline", "data": sample_data},
            "x_column": "month",
            "y_column": "sales",
            "title": "Monthly Sales",
            "library": "echarts",
        }

        result = await viz_tool.execute(payload, context={"user_id": "user-123"})

        assert result["library"] == "echarts"
        assert "spec" in result
        assert result["spec"]["title"]["text"] == "Monthly Sales"
        assert result["spec"]["series"][0]["type"] == "bar"

    @pytest.mark.asyncio
    async def test_execute_default_library(self, viz_tool, sample_data):
        """Test default library is Plotly."""
        payload = {
            "chart_type": "line",
            "data_source": {"type": "inline", "data": sample_data},
            "x_column": "month",
            "y_column": "sales",
        }

        result = await viz_tool.execute(payload, context={})

        assert result["library"] == "plotly"

    @pytest.mark.asyncio
    async def test_execute_no_data_raises_error(self, viz_tool):
        """Test execution fails with empty data."""
        payload = {
            "chart_type": "bar",
            "data_source": {"type": "inline", "data": []},
        }

        with pytest.raises(ValueError, match="No data loaded from source"):
            await viz_tool.execute(payload, context={})

    @pytest.mark.asyncio
    async def test_execute_unsupported_library(self, viz_tool, sample_data):
        """Test execution fails with unsupported library."""
        payload = {
            "chart_type": "bar",
            "data_source": {"type": "inline", "data": sample_data},
            "library": "d3",
        }

        with pytest.raises(ValueError, match="Unsupported library: d3"):
            await viz_tool.execute(payload, context={})


class TestVizToolLoadData:
    """Tests for data loading."""

    @pytest.mark.asyncio
    async def test_load_inline_data(self, viz_tool, sample_data):
        """Test loading inline data."""
        data_source = {"type": "inline", "data": sample_data}

        result = await viz_tool._load_data(data_source, user_id="user-123")

        assert result == sample_data

    @pytest.mark.asyncio
    async def test_load_excel_document_not_found(self, viz_tool):
        """Test loading Excel data with missing document."""
        data_source = {"type": "excel", "doc_id": "doc-999"}

        with patch("src.mcp_integration.tools.viz_tool.Document") as mock_doc:
            mock_doc.get = AsyncMock(return_value=None)

            with pytest.raises(ValueError, match="Document not found: doc-999"):
                await viz_tool._load_data(data_source, user_id="user-123")

    @pytest.mark.asyncio
    async def test_load_excel_permission_denied(self, viz_tool):
        """Test loading Excel data with wrong user."""
        data_source = {"type": "excel", "doc_id": "doc-123"}

        mock_doc = MagicMock()
        mock_doc.user_id = "other-user"

        with patch("src.mcp_integration.tools.viz_tool.Document") as mock_doc_class:
            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            with pytest.raises(PermissionError, match="not authorized"):
                await viz_tool._load_data(data_source, user_id="user-123")

    @pytest.mark.asyncio
    async def test_load_sql_not_implemented(self, viz_tool):
        """Test SQL data source raises NotImplementedError."""
        data_source = {"type": "sql", "sql_query": "SELECT * FROM table"}

        with pytest.raises(NotImplementedError, match="SQL data source not yet implemented"):
            await viz_tool._load_data(data_source, user_id="user-123")

    @pytest.mark.asyncio
    async def test_load_unknown_source_type(self, viz_tool):
        """Test unknown data source type raises error."""
        data_source = {"type": "unknown"}

        with pytest.raises(ValueError, match="Unknown data source type: unknown"):
            await viz_tool._load_data(data_source, user_id="user-123")


class TestVizToolPlotlySpec:
    """Tests for Plotly spec generation."""

    def test_generate_bar_chart(self, viz_tool, sample_data):
        """Test generating bar chart spec."""
        spec = viz_tool._generate_plotly_spec(
            chart_type="bar",
            data=sample_data,
            x_column="month",
            y_column="sales",
            title="Sales Chart",
        )

        assert spec["data"][0]["type"] == "bar"
        assert spec["data"][0]["x"] == ["Jan", "Feb", "Mar", "Apr"]
        assert spec["data"][0]["y"] == [100, 150, 200, 180]
        assert spec["layout"]["title"] == "Sales Chart"
        assert spec["layout"]["xaxis"]["title"] == "month"
        assert spec["layout"]["yaxis"]["title"] == "sales"

    def test_generate_line_chart(self, viz_tool, sample_data):
        """Test generating line chart spec."""
        spec = viz_tool._generate_plotly_spec(
            chart_type="line",
            data=sample_data,
            x_column="month",
            y_column="sales",
            title="Trend",
        )

        assert spec["data"][0]["type"] == "scatter"
        assert spec["data"][0]["mode"] == "lines+markers"
        assert spec["layout"]["title"] == "Trend"

    def test_generate_pie_chart(self, viz_tool, sample_data):
        """Test generating pie chart spec."""
        spec = viz_tool._generate_plotly_spec(
            chart_type="pie",
            data=sample_data,
            x_column="month",
            y_column="sales",
            title="Distribution",
        )

        assert spec["data"][0]["type"] == "pie"
        assert spec["data"][0]["labels"] == ["Jan", "Feb", "Mar", "Apr"]
        assert spec["data"][0]["values"] == [100, 150, 200, 180]
        assert spec["layout"]["title"] == "Distribution"

    def test_generate_scatter_chart(self, viz_tool, sample_data):
        """Test generating scatter chart (default for unknown types)."""
        spec = viz_tool._generate_plotly_spec(
            chart_type="scatter",
            data=sample_data,
            x_column="month",
            y_column="sales",
            title="Scatter",
        )

        assert spec["data"][0]["type"] == "scatter"
        assert spec["data"][0]["mode"] == "markers"

    def test_generate_chart_without_columns(self, viz_tool, sample_data):
        """Test generating chart without x/y columns specified."""
        spec = viz_tool._generate_plotly_spec(
            chart_type="bar",
            data=sample_data,
            x_column=None,
            y_column=None,
            title="No Columns",
        )

        assert spec["data"][0]["x"] == [0, 1, 2, 3]
        assert spec["data"][0]["y"] == [0, 0, 0, 0]
        assert spec["layout"]["xaxis"]["title"] == "X"
        assert spec["layout"]["yaxis"]["title"] == "Y"


class TestVizToolEChartsSpec:
    """Tests for ECharts spec generation."""

    def test_generate_echarts_bar_chart(self, viz_tool, sample_data):
        """Test generating ECharts bar chart spec."""
        spec = viz_tool._generate_echarts_spec(
            chart_type="bar",
            data=sample_data,
            x_column="month",
            y_column="sales",
            title="Sales",
        )

        assert spec["title"]["text"] == "Sales"
        assert spec["xAxis"]["data"] == ["Jan", "Feb", "Mar", "Apr"]
        assert spec["series"][0]["type"] == "bar"
        assert spec["series"][0]["data"] == [100, 150, 200, 180]
        assert spec["series"][0]["name"] == "sales"

    def test_generate_echarts_line_chart(self, viz_tool, sample_data):
        """Test generating ECharts line chart spec."""
        spec = viz_tool._generate_echarts_spec(
            chart_type="line",
            data=sample_data,
            x_column="month",
            y_column="profit",
            title="Profit Trend",
        )

        assert spec["series"][0]["type"] == "line"
        assert spec["series"][0]["data"] == [20, 35, 50, 40]
        assert spec["series"][0]["name"] == "profit"

    def test_generate_echarts_without_columns(self, viz_tool, sample_data):
        """Test generating ECharts without x/y columns."""
        spec = viz_tool._generate_echarts_spec(
            chart_type="bar",
            data=sample_data,
            x_column=None,
            y_column=None,
            title="Default",
        )

        assert spec["xAxis"]["data"] == [0, 1, 2, 3]
        assert spec["series"][0]["name"] == "Y"
        assert spec["series"][0]["data"] == [0, 0, 0, 0]


class TestVizToolExcelLoading:
    """Tests for Excel data loading with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_load_excel_success(self, viz_tool):
        """Test successful Excel loading."""
        from pathlib import Path
        import tempfile

        data_source = {"type": "excel", "doc_id": "doc-123", "sheet_name": "Sheet1"}

        # Create mock document
        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.minio_key = "test/file.xlsx"
        mock_doc.filename = "file.xlsx"

        # Create mock path
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        # Mock pandas read_excel
        import pandas as pd

        mock_df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})

        with patch("src.mcp_integration.tools.viz_tool.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.viz_tool.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.viz_tool.pd.read_excel", return_value=mock_df):

            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            result = await viz_tool._load_data(data_source, user_id="user-123")

            assert result == [{"A": 1, "B": 3}, {"A": 2, "B": 4}]
            mock_path.unlink.assert_called_once()  # Temp file cleanup
