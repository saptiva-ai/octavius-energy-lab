"""
Unit tests for ExcelAnalyzerTool.

Tests Excel file analysis with stats, aggregations, and validations.
"""

import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.mcp_integration.tools.excel_analyzer import ExcelAnalyzerTool
from src.mcp_integration.protocol import ToolCategory, ToolCapability


@pytest.fixture
def excel_tool():
    """Create ExcelAnalyzerTool instance."""
    return ExcelAnalyzerTool()


@pytest.fixture
def sample_df():
    """Sample DataFrame for testing."""
    return pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", None],
        "age": [25, 30, 35, 40],
        "salary": [50000.0, 60000.0, 70000.0, 80000.0],
        "department": ["Sales", "IT", "IT", "Sales"],
    })


class TestExcelAnalyzerSpec:
    """Tests for ExcelAnalyzerTool specification."""

    def test_get_spec_returns_tool_spec(self, excel_tool):
        """Test get_spec returns valid ToolSpec."""
        spec = excel_tool.get_spec()

        assert spec.name == "excel_analyzer"
        assert spec.version == "1.0.0"
        assert spec.display_name == "Excel Data Analyzer"
        assert spec.category == ToolCategory.DATA_ANALYTICS

    def test_spec_capabilities(self, excel_tool):
        """Test tool capabilities are correct."""
        spec = excel_tool.get_spec()

        assert ToolCapability.SYNC in spec.capabilities
        assert ToolCapability.IDEMPOTENT in spec.capabilities
        assert ToolCapability.CACHEABLE in spec.capabilities

    def test_spec_input_schema(self, excel_tool):
        """Test input schema structure."""
        spec = excel_tool.get_spec()
        schema = spec.input_schema

        assert schema["type"] == "object"
        assert "doc_id" in schema["properties"]
        assert "sheet_name" in schema["properties"]
        assert "operations" in schema["properties"]
        assert "doc_id" in schema["required"]

    def test_spec_operations(self, excel_tool):
        """Test supported operations."""
        spec = excel_tool.get_spec()
        operations = spec.input_schema["properties"]["operations"]["items"]["enum"]

        assert "stats" in operations
        assert "aggregate" in operations
        assert "validate" in operations
        assert "preview" in operations

    def test_spec_rate_limit(self, excel_tool):
        """Test rate limit is configured."""
        spec = excel_tool.get_spec()

        assert spec.rate_limit["calls_per_minute"] == 20

    def test_spec_timeout(self, excel_tool):
        """Test timeout is configured."""
        spec = excel_tool.get_spec()

        assert spec.timeout_ms == 30000


class TestExcelAnalyzerValidateInput:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_valid_input(self, excel_tool):
        """Test valid input passes validation."""
        payload = {"doc_id": "doc-123"}

        # Should not raise
        await excel_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_missing_doc_id(self, excel_tool):
        """Test validation fails without doc_id."""
        payload = {"sheet_name": "Sheet1"}

        with pytest.raises(ValueError, match="Missing required field: doc_id"):
            await excel_tool.validate_input(payload)


class TestExcelAnalyzerComputeStats:
    """Tests for _compute_stats method."""

    def test_compute_stats(self, excel_tool, sample_df):
        """Test computing basic statistics."""
        stats = excel_tool._compute_stats(sample_df)

        assert stats["row_count"] == 4
        assert stats["column_count"] == 4
        assert len(stats["columns"]) == 4

    def test_compute_stats_column_info(self, excel_tool, sample_df):
        """Test column info in stats."""
        stats = excel_tool._compute_stats(sample_df)

        name_col = next(c for c in stats["columns"] if c["name"] == "name")
        assert name_col["non_null_count"] == 3
        assert name_col["null_count"] == 1

        age_col = next(c for c in stats["columns"] if c["name"] == "age")
        assert age_col["non_null_count"] == 4
        assert age_col["null_count"] == 0

    def test_compute_stats_empty_df(self, excel_tool):
        """Test computing stats for empty DataFrame."""
        df = pd.DataFrame()

        stats = excel_tool._compute_stats(df)

        assert stats["row_count"] == 0
        assert stats["column_count"] == 0
        assert stats["columns"] == []


class TestExcelAnalyzerComputeAggregates:
    """Tests for _compute_aggregates method."""

    def test_compute_aggregates_numeric(self, excel_tool, sample_df):
        """Test computing aggregates for numeric columns."""
        aggregates = excel_tool._compute_aggregates(sample_df, ["age", "salary"])

        assert "age" in aggregates
        assert aggregates["age"]["sum"] == 130.0
        assert aggregates["age"]["mean"] == 32.5
        assert aggregates["age"]["min"] == 25.0
        assert aggregates["age"]["max"] == 40.0

        assert "salary" in aggregates
        assert aggregates["salary"]["sum"] == 260000.0

    def test_compute_aggregates_skips_non_numeric(self, excel_tool, sample_df):
        """Test aggregates skip non-numeric columns."""
        aggregates = excel_tool._compute_aggregates(sample_df, ["name", "department"])

        assert "name" not in aggregates
        assert "department" not in aggregates

    def test_compute_aggregates_skips_missing_columns(self, excel_tool, sample_df):
        """Test aggregates skip missing columns."""
        aggregates = excel_tool._compute_aggregates(sample_df, ["nonexistent"])

        assert "nonexistent" not in aggregates

    def test_compute_aggregates_empty_columns(self, excel_tool, sample_df):
        """Test aggregates with empty columns list."""
        aggregates = excel_tool._compute_aggregates(sample_df, [])

        assert aggregates == {}


class TestExcelAnalyzerValidateData:
    """Tests for _validate_data method."""

    def test_validate_data_with_missing(self, excel_tool, sample_df):
        """Test validation detects missing values."""
        validation = excel_tool._validate_data(sample_df)

        assert validation["total_missing_values"] == 1
        assert "name" in validation["columns_with_missing"]
        assert validation["type_mismatches"] == []

    def test_validate_data_no_missing(self, excel_tool):
        """Test validation with no missing values."""
        df = pd.DataFrame({
            "a": [1, 2, 3],
            "b": ["x", "y", "z"],
        })

        validation = excel_tool._validate_data(df)

        assert validation["total_missing_values"] == 0
        assert validation["columns_with_missing"] == []

    def test_validate_data_all_missing(self, excel_tool):
        """Test validation with many missing values."""
        df = pd.DataFrame({
            "a": [None, None, None],
            "b": [None, 1, None],
        })

        validation = excel_tool._validate_data(df)

        assert validation["total_missing_values"] == 5
        assert "a" in validation["columns_with_missing"]
        assert "b" in validation["columns_with_missing"]


class TestExcelAnalyzerExecute:
    """Tests for tool execution."""

    @pytest.mark.asyncio
    async def test_execute_document_not_found(self, excel_tool):
        """Test execution fails when document not found."""
        payload = {"doc_id": "doc-999"}

        with patch("src.mcp_integration.tools.excel_analyzer.Document") as mock_doc:
            mock_doc.get = AsyncMock(return_value=None)

            with pytest.raises(ValueError, match="Document not found: doc-999"):
                await excel_tool.execute(payload, context={"user_id": "user-123"})

    @pytest.mark.asyncio
    async def test_execute_permission_denied(self, excel_tool):
        """Test execution fails when user doesn't own document."""
        payload = {"doc_id": "doc-123"}

        mock_doc = MagicMock()
        mock_doc.user_id = "other-user"

        with patch("src.mcp_integration.tools.excel_analyzer.Document") as mock_doc_class:
            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            with pytest.raises(PermissionError, match="not authorized"):
                await excel_tool.execute(payload, context={"user_id": "user-123"})

    @pytest.mark.asyncio
    async def test_execute_wrong_content_type(self, excel_tool):
        """Test execution fails for non-Excel files."""
        payload = {"doc_id": "doc-123"}

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/pdf"

        with patch("src.mcp_integration.tools.excel_analyzer.Document") as mock_doc_class:
            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            with pytest.raises(ValueError, match="not an Excel file"):
                await excel_tool.execute(payload, context={"user_id": "user-123"})

    @pytest.mark.asyncio
    async def test_execute_success_xlsx(self, excel_tool, sample_df):
        """Test successful execution with xlsx file."""
        payload = {
            "doc_id": "doc-123",
            "operations": ["stats", "preview"],
        }

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        mock_doc.minio_key = "test/file.xlsx"
        mock_doc.filename = "file.xlsx"
        mock_doc.conversation_id = None

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch("src.mcp_integration.tools.excel_analyzer.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.excel_analyzer.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.excel_analyzer.pd.read_excel", return_value=sample_df):

            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            result = await excel_tool.execute(payload, context={"user_id": "user-123"})

            assert result["doc_id"] == "doc-123"
            assert "stats" in result
            assert "preview" in result
            assert result["stats"]["row_count"] == 4
            mock_path.unlink.assert_called_once()  # Temp file cleanup

    @pytest.mark.asyncio
    async def test_execute_success_xls(self, excel_tool, sample_df):
        """Test successful execution with xls file."""
        payload = {"doc_id": "doc-123"}

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/vnd.ms-excel"
        mock_doc.minio_key = "test/file.xls"
        mock_doc.filename = "file.xls"
        mock_doc.conversation_id = None

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch("src.mcp_integration.tools.excel_analyzer.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.excel_analyzer.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.excel_analyzer.pd.read_excel", return_value=sample_df):

            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, False)
            mock_storage_func.return_value = mock_storage

            result = await excel_tool.execute(payload, context={"user_id": "user-123"})

            assert result["doc_id"] == "doc-123"
            mock_path.unlink.assert_not_called()  # Not a temp file

    @pytest.mark.asyncio
    async def test_execute_all_operations(self, excel_tool, sample_df):
        """Test execution with all operations."""
        payload = {
            "doc_id": "doc-123",
            "operations": ["stats", "aggregate", "validate", "preview"],
            "aggregate_columns": ["age", "salary"],
        }

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        mock_doc.minio_key = "test/file.xlsx"
        mock_doc.filename = "file.xlsx"
        mock_doc.conversation_id = None

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch("src.mcp_integration.tools.excel_analyzer.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.excel_analyzer.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.excel_analyzer.pd.read_excel", return_value=sample_df):

            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            result = await excel_tool.execute(payload, context={"user_id": "user-123"})

            assert "stats" in result
            assert "aggregates" in result
            assert "validation" in result
            assert "preview" in result
            assert result["aggregates"]["age"]["mean"] == 32.5

    @pytest.mark.asyncio
    async def test_execute_user_id_from_payload(self, excel_tool, sample_df):
        """Test user_id can be read from payload."""
        payload = {
            "doc_id": "doc-123",
            "user_id": "user-123",  # user_id in payload
        }

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        mock_doc.minio_key = "test/file.xlsx"
        mock_doc.filename = "file.xlsx"
        mock_doc.conversation_id = None

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch("src.mcp_integration.tools.excel_analyzer.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.excel_analyzer.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.excel_analyzer.pd.read_excel", return_value=sample_df):

            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            # No context user_id, but payload has it
            result = await excel_tool.execute(payload, context={})

            assert result["doc_id"] == "doc-123"

    @pytest.mark.asyncio
    async def test_execute_no_user_id_dev_mode(self, excel_tool, sample_df):
        """Test execution without user_id (dev mode warning)."""
        payload = {"doc_id": "doc-123"}

        mock_doc = MagicMock()
        mock_doc.user_id = "any-user"
        mock_doc.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        mock_doc.minio_key = "test/file.xlsx"
        mock_doc.filename = "file.xlsx"
        mock_doc.conversation_id = None

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch("src.mcp_integration.tools.excel_analyzer.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.excel_analyzer.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.excel_analyzer.pd.read_excel", return_value=sample_df):

            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            # No user_id - should work but log warning
            result = await excel_tool.execute(payload, context=None)

            assert result["doc_id"] == "doc-123"

    @pytest.mark.asyncio
    async def test_execute_conversation_id_mismatch_allowed(self, excel_tool, sample_df):
        """Test conversation_id mismatch is allowed (database latency handling)."""
        payload = {"doc_id": "doc-123"}

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        mock_doc.minio_key = "test/file.xlsx"
        mock_doc.filename = "file.xlsx"
        mock_doc.conversation_id = "old-session"  # Different from context

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch("src.mcp_integration.tools.excel_analyzer.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.excel_analyzer.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.excel_analyzer.pd.read_excel", return_value=sample_df):

            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            # Mismatched session_id should still work
            result = await excel_tool.execute(
                payload,
                context={"user_id": "user-123", "session_id": "new-session"}
            )

            assert result["doc_id"] == "doc-123"
