"""
Integration tests for excel_analyzer tool.

Tests Excel file analysis via MCP.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from pathlib import Path
import pandas as pd
import io
import os

from src.mcp_integration.server import excel_analyzer
from src.models.document import Document, DocumentStatus

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MCP_EXCEL_ANALYZER", "false").lower() != "true",
    reason="MCP excel analyzer tests deshabilitados por defecto (requires full stack)",
)


@pytest.fixture
def sample_excel_data():
    """Create sample Excel data as DataFrame."""
    return pd.DataFrame({
        "month": ["Jan", "Feb", "Mar", "Apr", "May"],
        "revenue": [10000, 15000, 12000, 18000, 16000],
        "cost": [6000, 8000, 7000, 9000, 8500],
        "profit": [4000, 7000, 5000, 9000, 7500],
    })


@pytest.fixture
def sample_excel_file(sample_excel_data, tmp_path):
    """Create a temporary Excel file."""
    excel_path = tmp_path / "test_data.xlsx"
    sample_excel_data.to_excel(excel_path, index=False)
    return excel_path


@pytest.fixture
def mock_excel_document(sample_excel_file):
    """Create a mock Excel document."""
    doc = Mock(spec=Document)
    doc.id = "doc_456"
    doc.user_id = "user_789"
    doc.filename = "data.xlsx"
    doc.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    doc.status = DocumentStatus.READY
    doc.minio_key = str(sample_excel_file)
    return doc


class TestExcelAnalyzerTool:
    """Test suite for excel_analyzer tool."""

    @pytest.mark.asyncio
    async def test_excel_analyzer_stats_only(
        self, mock_excel_document, sample_excel_file
    ):
        """Test Excel analysis with stats operation."""
        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)), \
             patch("src.mcp_integration.server.get_minio_storage") as mock_minio:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (sample_excel_file, False)
            mock_minio.return_value = mock_storage

            result = await excel_analyzer(
                doc_id="doc_456",
                operations=["stats"],
            )

            # Check structure
            assert result["doc_id"] == "doc_456"
            assert result["sheet_name"] == "Sheet1"
            assert "stats" in result

            # Check stats content
            stats = result["stats"]
            assert stats["row_count"] == 5
            assert stats["column_count"] == 4
            assert len(stats["columns"]) == 4

            # Check column info
            month_col = next(c for c in stats["columns"] if c["name"] == "month")
            assert month_col["dtype"] == "object"
            assert month_col["non_null_count"] == 5
            assert month_col["null_count"] == 0

    @pytest.mark.asyncio
    async def test_excel_analyzer_aggregate_operation(
        self, mock_excel_document, sample_excel_file
    ):
        """Test Excel analysis with aggregate operation."""
        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)), \
             patch("src.mcp_integration.server.get_minio_storage") as mock_minio:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (sample_excel_file, False)
            mock_minio.return_value = mock_storage

            result = await excel_analyzer(
                doc_id="doc_456",
                operations=["aggregate"],
                aggregate_columns=["revenue", "cost"],
            )

            assert "aggregates" in result
            aggregates = result["aggregates"]

            # Check revenue aggregates
            assert "revenue" in aggregates
            rev = aggregates["revenue"]
            assert rev["sum"] == 71000.0
            assert rev["mean"] == 14200.0
            assert rev["min"] == 10000.0
            assert rev["max"] == 18000.0
            assert "median" in rev
            assert "std" in rev

            # Check cost aggregates
            assert "cost" in aggregates

    @pytest.mark.asyncio
    async def test_excel_analyzer_validate_operation(
        self, mock_excel_document, sample_excel_file
    ):
        """Test Excel analysis with validate operation."""
        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)), \
             patch("src.mcp_integration.server.get_minio_storage") as mock_minio:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (sample_excel_file, False)
            mock_minio.return_value = mock_storage

            result = await excel_analyzer(
                doc_id="doc_456",
                operations=["validate"],
            )

            assert "validation" in result
            validation = result["validation"]

            assert "total_missing_values" in validation
            assert "columns_with_missing" in validation
            assert "type_mismatches" in validation

            # No missing values in sample data
            assert validation["total_missing_values"] == 0
            assert len(validation["columns_with_missing"]) == 0

    @pytest.mark.asyncio
    async def test_excel_analyzer_preview_operation(
        self, mock_excel_document, sample_excel_file
    ):
        """Test Excel analysis with preview operation."""
        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)), \
             patch("src.mcp_integration.server.get_minio_storage") as mock_minio:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (sample_excel_file, False)
            mock_minio.return_value = mock_storage

            result = await excel_analyzer(
                doc_id="doc_456",
                operations=["preview"],
            )

            assert "preview" in result
            preview = result["preview"]

            # Check preview format
            assert isinstance(preview, list)
            assert len(preview) <= 10  # Max 10 rows
            assert len(preview) == 5  # Our sample has 5 rows

            # Check first row
            assert preview[0]["month"] == "Jan"
            assert preview[0]["revenue"] == 10000

    @pytest.mark.asyncio
    async def test_excel_analyzer_all_operations(
        self, mock_excel_document, sample_excel_file
    ):
        """Test Excel analysis with all operations."""
        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)), \
             patch("src.mcp_integration.server.get_minio_storage") as mock_minio:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (sample_excel_file, False)
            mock_minio.return_value = mock_storage

            result = await excel_analyzer(
                doc_id="doc_456",
                operations=["stats", "aggregate", "validate", "preview"],
                aggregate_columns=["revenue"],
            )

            # All keys should be present
            assert "stats" in result
            assert "aggregates" in result
            assert "validation" in result
            assert "preview" in result

    @pytest.mark.asyncio
    async def test_excel_analyzer_document_not_found(self):
        """Test Excel analysis with non-existent document."""
        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="Document not found"):
                await excel_analyzer(doc_id="nonexistent")

    @pytest.mark.asyncio
    async def test_excel_analyzer_permission_denied(self, mock_excel_document):
        """Test Excel analysis with wrong user."""
        mock_excel_document.user_id = "other_user"

        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)):
            with pytest.raises(PermissionError, match="not authorized"):
                await excel_analyzer(
                    doc_id="doc_456",
                    user_id="current_user",
                )

    @pytest.mark.asyncio
    async def test_excel_analyzer_wrong_file_type(self):
        """Test Excel analysis with non-Excel document."""
        mock_doc = Mock(spec=Document)
        mock_doc.id = "doc_456"
        mock_doc.user_id = "user_789"
        mock_doc.content_type = "application/pdf"  # Not Excel

        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_doc)):
            with pytest.raises(ValueError, match="not an Excel file"):
                await excel_analyzer(doc_id="doc_456")

    @pytest.mark.asyncio
    async def test_excel_analyzer_with_sheet_name(
        self, mock_excel_document, tmp_path
    ):
        """Test Excel analysis with specific sheet name."""
        # Create Excel with multiple sheets
        excel_path = tmp_path / "multi_sheet.xlsx"
        with pd.ExcelWriter(excel_path) as writer:
            pd.DataFrame({"A": [1, 2]}).to_excel(writer, sheet_name="Sheet1", index=False)
            pd.DataFrame({"B": [3, 4]}).to_excel(writer, sheet_name="Data", index=False)

        mock_excel_document.minio_key = str(excel_path)

        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)), \
             patch("src.mcp_integration.server.get_minio_storage") as mock_minio:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (excel_path, False)
            mock_minio.return_value = mock_storage

            result = await excel_analyzer(
                doc_id="doc_456",
                sheet_name="Data",
                operations=["stats"],
            )

            assert result["sheet_name"] == "Data"
            assert result["stats"]["column_count"] == 1

    @pytest.mark.asyncio
    async def test_excel_analyzer_cleans_up_temp_file(
        self, mock_excel_document, sample_excel_file
    ):
        """Test that temporary files are cleaned up."""
        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)), \
             patch("src.mcp_integration.server.get_minio_storage") as mock_minio:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (sample_excel_file, True)  # is_temp=True
            mock_minio.return_value = mock_storage

            with patch.object(Path, "exists", return_value=True), \
                 patch.object(Path, "unlink") as mock_unlink:

                await excel_analyzer(
                    doc_id="doc_456",
                    operations=["stats"],
                )

                # Verify cleanup was called
                mock_unlink.assert_called_once()

    @pytest.mark.asyncio
    async def test_excel_analyzer_with_context_logging(
        self, mock_excel_document, sample_excel_file
    ):
        """Test that context logging is used when available."""
        from fastmcp import Context

        mock_ctx = AsyncMock(spec=Context)

        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)), \
             patch("src.mcp_integration.server.get_minio_storage") as mock_minio:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (sample_excel_file, False)
            mock_minio.return_value = mock_storage

            await excel_analyzer(
                doc_id="doc_456",
                operations=["stats"],
                ctx=mock_ctx,
            )

            # Verify context methods were called
            assert mock_ctx.info.called
            assert mock_ctx.report_progress.called

    @pytest.mark.asyncio
    async def test_excel_analyzer_aggregate_non_numeric_column(
        self, mock_excel_document, sample_excel_file
    ):
        """Test aggregation skips non-numeric columns."""
        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)), \
             patch("src.mcp_integration.server.get_minio_storage") as mock_minio:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (sample_excel_file, False)
            mock_minio.return_value = mock_storage

            result = await excel_analyzer(
                doc_id="doc_456",
                operations=["aggregate"],
                aggregate_columns=["month", "revenue"],  # month is string
            )

            aggregates = result["aggregates"]

            # month should be skipped (non-numeric)
            assert "month" not in aggregates
            # revenue should be present (numeric)
            assert "revenue" in aggregates

    @pytest.mark.asyncio
    async def test_excel_analyzer_default_operations(
        self, mock_excel_document, sample_excel_file
    ):
        """Test default operations (stats and preview)."""
        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)), \
             patch("src.mcp_integration.server.get_minio_storage") as mock_minio:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (sample_excel_file, False)
            mock_minio.return_value = mock_storage

            # Don't specify operations - should default to stats and preview
            result = await excel_analyzer(doc_id="doc_456")

            assert "stats" in result
            assert "preview" in result
            assert "aggregates" not in result
            assert "validation" not in result


class TestExcelAnalyzerWithMissingData:
    """Test Excel analyzer with missing/null data."""

    @pytest.mark.asyncio
    async def test_excel_analyzer_with_null_values(
        self, mock_excel_document, tmp_path
    ):
        """Test Excel analysis with null values."""
        # Create Excel with null values
        df = pd.DataFrame({
            "name": ["Alice", "Bob", None, "David"],
            "score": [85, None, 92, 88],
        })
        excel_path = tmp_path / "with_nulls.xlsx"
        df.to_excel(excel_path, index=False)

        mock_excel_document.minio_key = str(excel_path)

        with patch("src.mcp_integration.server.Document.get", new=AsyncMock(return_value=mock_excel_document)), \
             patch("src.mcp_integration.server.get_minio_storage") as mock_minio:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (excel_path, False)
            mock_minio.return_value = mock_storage

            result = await excel_analyzer(
                doc_id="doc_456",
                operations=["validate"],
            )

            validation = result["validation"]
            assert validation["total_missing_values"] == 2
            assert "name" in validation["columns_with_missing"]
            assert "score" in validation["columns_with_missing"]
