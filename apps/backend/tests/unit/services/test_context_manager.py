"""
Unit tests for ContextManager service.

Tests cover:
- Context source management
- Document context addition
- Tool result aggregation
- Size limits and truncation
- Context string building
"""

import pytest
from datetime import datetime
from unittest.mock import patch

from src.services.context_manager import (
    ContextManager,
    ContextSource,
    MAX_DOCUMENT_CONTEXT_CHARS,
    MAX_TOOL_CONTEXT_CHARS,
    MAX_TOTAL_CONTEXT_CHARS,
)


@pytest.mark.unit
class TestContextSource:
    """Tests for ContextSource dataclass."""

    def test_context_source_initialization(self):
        """Should initialize with correct attributes."""
        source = ContextSource(
            source_type="document",
            source_id="doc-123",
            content="Test content",
            metadata={"filename": "test.pdf"},
        )

        assert source.source_type == "document"
        assert source.source_id == "doc-123"
        assert source.content == "Test content"
        assert source.metadata == {"filename": "test.pdf"}
        assert source.char_count == 12
        assert isinstance(source.timestamp, datetime)

    def test_context_source_default_metadata(self):
        """Should default metadata to empty dict."""
        source = ContextSource(
            source_type="tool_result",
            source_id="excel",
            content="Result data",
        )

        assert source.metadata == {}

    def test_context_source_char_count(self):
        """Should correctly count characters."""
        long_content = "x" * 1000
        source = ContextSource(
            source_type="document",
            source_id="doc",
            content=long_content,
        )

        assert source.char_count == 1000


@pytest.mark.unit
class TestContextManager:
    """Tests for ContextManager service."""

    def test_initialization_default_limits(self):
        """Should initialize with default size limits."""
        manager = ContextManager()

        assert manager.max_document_chars == MAX_DOCUMENT_CONTEXT_CHARS
        assert manager.max_tool_chars == MAX_TOOL_CONTEXT_CHARS
        assert manager.max_total_chars == MAX_TOTAL_CONTEXT_CHARS
        assert manager.sources == []

    def test_initialization_custom_limits(self):
        """Should accept custom size limits."""
        manager = ContextManager(
            max_document_chars=5000,
            max_tool_chars=3000,
            max_total_chars=10000,
        )

        assert manager.max_document_chars == 5000
        assert manager.max_tool_chars == 3000
        assert manager.max_total_chars == 10000

    def test_add_document_context_basic(self):
        """Should add document context to sources."""
        manager = ContextManager()
        manager.add_document_context(
            doc_id="doc-123",
            text="Document content here",
        )

        assert len(manager.sources) == 1
        source = manager.sources[0]
        assert source.source_type == "document"
        assert source.source_id == "doc-123"
        assert source.content == "Document content here"

    def test_add_document_context_with_filename(self):
        """Should prepend filename to content."""
        manager = ContextManager()
        manager.add_document_context(
            doc_id="doc-123",
            text="Document content",
            filename="report.pdf",
        )

        source = manager.sources[0]
        assert "report.pdf" in source.content
        assert "Document content" in source.content
        assert source.metadata == {"filename": "report.pdf"}

    def test_add_multiple_documents(self):
        """Should handle multiple document additions."""
        manager = ContextManager()

        manager.add_document_context("doc-1", "First document")
        manager.add_document_context("doc-2", "Second document")
        manager.add_document_context("doc-3", "Third document")

        assert len(manager.sources) == 3

    def test_add_tool_result_with_summary(self):
        """Should add tool result with provided summary."""
        manager = ContextManager()

        manager.add_tool_result(
            tool_name="excel_analyzer",
            result={"rows": 100, "columns": 5},
            summary="Excel file with 100 rows and 5 columns",
        )

        assert len(manager.sources) == 1
        source = manager.sources[0]
        assert source.source_type == "tool_result"
        assert source.source_id == "excel_analyzer"
        assert source.content == "Excel file with 100 rows and 5 columns"

    def test_add_tool_result_auto_summary(self):
        """Should auto-generate summary when not provided."""
        manager = ContextManager()

        manager.add_tool_result(
            tool_name="unknown_tool",
            result={"data": "value"},
        )

        source = manager.sources[0]
        assert "Tool result:" in source.content

    def test_summarize_audit_result_with_findings(self):
        """Should format audit findings correctly."""
        manager = ContextManager()
        result = {
            "findings": [
                {"severity": "error", "message": "Missing disclaimer"},
                {"severity": "warning", "message": "Logo too small"},
                {"severity": "info", "message": "Consider font size"},
            ]
        }

        summary = manager._summarize_audit_result(result)

        assert "Document Audit Findings" in summary
        assert "Missing disclaimer" in summary
        assert "Logo too small" in summary

    def test_summarize_audit_result_no_findings(self):
        """Should return success message when no findings."""
        manager = ContextManager()
        result = {"findings": []}

        summary = manager._summarize_audit_result(result)

        assert "passed" in summary.lower() or "no issues" in summary.lower()

    def test_summarize_audit_result_limits_to_five(self):
        """Should limit displayed findings to 5."""
        manager = ContextManager()
        result = {
            "findings": [
                {"severity": "warning", "message": f"Finding {i}"}
                for i in range(10)
            ]
        }

        summary = manager._summarize_audit_result(result)

        assert "5 more" in summary

    def test_summarize_excel_result_with_stats(self):
        """Should format Excel stats correctly."""
        manager = ContextManager()
        result = {
            "operations": {
                "stats": {"row_count": 100, "column_count": 5},
            }
        }

        summary = manager._summarize_excel_result(result)

        assert "Excel Analysis" in summary
        assert "100" in summary
        assert "5" in summary

    def test_summarize_excel_result_with_aggregate(self):
        """Should format Excel aggregates correctly."""
        manager = ContextManager()
        result = {
            "operations": {
                "aggregate": {
                    "revenue": {"mean": 1000.55, "sum": 50000.0},
                }
            }
        }

        summary = manager._summarize_excel_result(result)

        assert "revenue" in summary
        assert "1000.55" in summary

    def test_summarize_excel_result_handles_non_numeric(self):
        """Should handle non-numeric aggregate values."""
        manager = ContextManager()
        result = {
            "operations": {
                "aggregate": {
                    "category": {"mean": "N/A", "sum": "N/A"},
                }
            }
        }

        summary = manager._summarize_excel_result(result)

        assert "N/A" in summary

    def test_summarize_research_result(self):
        """Should format research results correctly."""
        manager = ContextManager()
        result = {
            "summary": "Key findings from research",
            "sources": [{"url": "http://a"}, {"url": "http://b"}],
        }

        summary = manager._summarize_research_result(result)

        assert "Research Findings" in summary
        assert "Key findings" in summary
        assert "2" in summary  # source count

    def test_default_summary(self):
        """Should provide fallback summary for unknown tools."""
        manager = ContextManager()
        result = {"complex": {"nested": "data"}}

        summary = manager._default_summary(result)

        assert "Tool result:" in summary
        assert len(summary) <= 520  # 500 content + 20 for prefix/suffix

    def test_build_context_string_empty(self):
        """Should return empty context when no sources."""
        manager = ContextManager()

        context, metadata = manager.build_context_string()

        assert context == ""
        assert metadata["total_sources"] == 0

    def test_build_context_string_documents_only(self):
        """Should build context with documents only."""
        manager = ContextManager()
        manager.add_document_context("doc-1", "First document content")

        context, metadata = manager.build_context_string()

        assert "Document Content" in context
        assert "First document content" in context
        assert metadata["document_sources"] == 1

    def test_build_context_string_tools_only(self):
        """Should build context with tools only."""
        manager = ContextManager()
        manager.add_tool_result("excel", {"data": "test"}, "Excel summary")

        context, metadata = manager.build_context_string()

        assert "Analysis Results" in context
        assert "Excel summary" in context
        assert metadata["tool_sources"] == 1

    def test_build_context_string_mixed_sources(self):
        """Should combine documents and tools with separator."""
        manager = ContextManager()
        manager.add_document_context("doc-1", "Document text")
        manager.add_tool_result("excel", {"data": "test"}, "Tool output")

        context, metadata = manager.build_context_string()

        assert "Document Content" in context
        assert "Analysis Results" in context
        assert "---" in context
        assert metadata["document_sources"] == 1
        assert metadata["tool_sources"] == 1

    def test_build_context_string_respects_document_limit(self):
        """Should truncate documents at size limit."""
        manager = ContextManager(max_document_chars=100)

        # Add content exceeding limit
        manager.add_document_context("doc-1", "x" * 80)
        manager.add_document_context("doc-2", "y" * 80)

        context, metadata = manager.build_context_string()

        # Second document should be truncated or not fully included
        assert metadata["document_chars"] <= 100

    def test_build_context_string_respects_tool_limit(self):
        """Should truncate tools at size limit."""
        manager = ContextManager(max_tool_chars=100)

        manager.add_tool_result("tool-1", {}, "a" * 80)
        manager.add_tool_result("tool-2", {}, "b" * 80)

        context, metadata = manager.build_context_string()

        assert metadata["tool_chars"] <= 100

    def test_build_context_string_respects_total_limit(self):
        """Should truncate total context at size limit."""
        manager = ContextManager(max_total_chars=200)

        manager.add_document_context("doc", "x" * 150)
        manager.add_tool_result("tool", {}, "y" * 150)

        context, metadata = manager.build_context_string()

        assert len(context) <= 200
        assert metadata["truncated"] is True
        assert "[Context truncated]" in context

    def test_build_context_string_no_truncation_when_under_limit(self):
        """Should not truncate when under limit."""
        manager = ContextManager(max_total_chars=10000)

        manager.add_document_context("doc", "Small content")

        context, metadata = manager.build_context_string()

        assert metadata["truncated"] is False
        assert "[Context truncated]" not in context

    def test_build_context_string_minimum_space_threshold(self):
        """Should not add content if remaining space < 50 chars."""
        manager = ContextManager(max_document_chars=100)

        manager.add_document_context("doc-1", "x" * 90)
        manager.add_document_context("doc-2", "y" * 50)  # Only 10 chars remaining

        context, metadata = manager.build_context_string()

        # Second doc should not be partially added (< 50 threshold)
        assert "y" * 10 not in context or "..." not in context

    def test_clear_removes_all_sources(self):
        """Should clear all context sources."""
        manager = ContextManager()
        manager.add_document_context("doc-1", "Content 1")
        manager.add_tool_result("tool-1", {}, "Result 1")

        assert len(manager.sources) == 2

        manager.clear()

        assert len(manager.sources) == 0

    def test_metadata_accuracy(self):
        """Should return accurate metadata."""
        manager = ContextManager()
        manager.add_document_context("doc-1", "Doc content here")
        manager.add_document_context("doc-2", "Another doc")
        manager.add_tool_result("tool-1", {}, "Tool result")

        context, metadata = manager.build_context_string()

        assert metadata["total_sources"] == 3
        assert metadata["document_sources"] == 2
        assert metadata["tool_sources"] == 1
        assert metadata["total_chars"] == len(context)


@pytest.mark.unit
class TestContextManagerToolSummarizers:
    """Tests for specific tool summarizers."""

    def test_audit_severity_emojis(self):
        """Should use correct emojis for severity levels."""
        manager = ContextManager()

        # Test error emoji
        error_result = {"findings": [{"severity": "error", "message": "Error msg"}]}
        summary = manager._summarize_audit_result(error_result)
        assert "🔴" in summary

        # Test warning emoji
        warning_result = {"findings": [{"severity": "warning", "message": "Warn msg"}]}
        summary = manager._summarize_audit_result(warning_result)
        assert "🟡" in summary

        # Test info emoji
        info_result = {"findings": [{"severity": "info", "message": "Info msg"}]}
        summary = manager._summarize_audit_result(info_result)
        assert "ℹ️" in summary

    def test_excel_empty_operations(self):
        """Should handle empty Excel operations."""
        manager = ContextManager()
        result = {"operations": {}}

        summary = manager._summarize_excel_result(result)

        assert "Excel Analysis" in summary

    def test_research_empty_sources(self):
        """Should handle empty research sources."""
        manager = ContextManager()
        result = {"summary": "No sources found", "sources": []}

        summary = manager._summarize_research_result(result)

        assert "0 verified sources" in summary
