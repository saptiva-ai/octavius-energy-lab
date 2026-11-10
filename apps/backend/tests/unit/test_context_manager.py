"""
Unit tests for Context Manager

Tests:
- Context aggregation from documents and tools
- Size limit enforcement (document, tool, and total)
- Formatting and truncation
- Tool result summarization
"""

import pytest
from src.services.context_manager import ContextManager, MAX_DOCUMENT_CONTEXT_CHARS, MAX_TOOL_CONTEXT_CHARS, MAX_TOTAL_CONTEXT_CHARS


@pytest.fixture
def context_manager():
    """Create a fresh ContextManager instance for each test."""
    return ContextManager()


@pytest.mark.unit
class TestContextManager:
    """Test suite for ContextManager."""

    def test_add_document_context(self, context_manager):
        """Should add document content correctly."""
        context_manager.add_document_context("doc-1", "Content of doc 1", filename="doc1.txt")
        
        assert len(context_manager.sources) == 1
        source = context_manager.sources[0]
        assert source.source_type == "document"
        assert source.source_id == "doc-1"
        assert "Content of doc 1" in source.content
        assert "doc1.txt" in source.content

    def test_add_tool_result_with_auto_summary(self, context_manager):
        """Should automatically summarize tool results."""
        audit_result = {
            "findings": [
                {"severity": "error", "message": "Critical issue"},
                {"severity": "warning", "message": "Minor issue"}
            ]
        }

        # Use audit_file tool which handles findings format
        context_manager.add_tool_result("audit_file", audit_result)

        assert len(context_manager.sources) == 1
        source = context_manager.sources[0]
        assert source.source_type == "tool_result"
        assert "🔴 Critical issue" in source.content
        assert "🟡 Minor issue" in source.content

    def test_add_tool_result_with_explicit_summary(self, context_manager):
        """Should use provided summary if available."""
        context_manager.add_tool_result("custom_tool", {}, summary="My custom summary")
        
        source = context_manager.sources[0]
        assert source.content == "My custom summary"

    def test_enforces_document_limit(self):
        """Should truncate documents if they exceed limit."""
        # Create manager with small limit for testing
        limit = 100
        manager = ContextManager(max_document_chars=limit)
        
        # Add content larger than limit
        long_content = "x" * (limit + 50)
        manager.add_document_context("doc-1", long_content)
        
        context_str, metadata = manager.build_context_string()
        
        # Should be truncated (limit + overhead for formatting)
        # The context string includes "📄 Document Content:\n" header
        assert "..." in context_str
        assert metadata["document_chars"] == limit
        assert metadata["truncated"] is False # Only doc section truncated, not total

    def test_enforces_total_limit(self):
        """Should truncate entire context if it exceeds total limit."""
        limit = 50
        manager = ContextManager(max_total_chars=limit)
        
        manager.add_document_context("doc-1", "A" * 40)
        manager.add_tool_result("tool-1", {}, summary="B" * 40)
        
        context_str, metadata = manager.build_context_string()
        
        assert len(context_str) <= limit
        assert "[Context truncated]" in context_str
        assert metadata["truncated"] is True

    def test_summarize_audit_result(self, context_manager):
        """Test audit result formatting."""
        result = {"findings": []}
        assert "passed" in context_manager._summarize_audit_result(result)
        
        result = {"findings": [{"message": "Test"}]}
        assert "Findings" in context_manager._summarize_audit_result(result)

    def test_summarize_excel_result(self, context_manager):
        """Test excel result formatting."""
        result = {
            "operations": {
                "stats": {"row_count": 10, "column_count": 5},
                "aggregate": {"Sales": {"sum": 100.50}}
            }
        }
        summary = context_manager._summarize_excel_result(result)
        assert "Rows: 10" in summary
        assert "Sales: mean=N/A, sum=100.50" in summary

    def test_build_context_string_structure(self, context_manager):
        """Should format final string with sections."""
        context_manager.add_document_context("d1", "Doc content")
        context_manager.add_tool_result("t1", {}, summary="Tool content")
        
        context_str, _ = context_manager.build_context_string()
        
        assert "📄 Document Content:" in context_str
        assert "Doc content" in context_str
        assert "🔧 Analysis Results:" in context_str
        assert "Tool content" in context_str
        assert "---" in context_str

    def test_clear(self, context_manager):
        """Should clear all sources."""
        context_manager.add_document_context("d1", "text")
        assert len(context_manager.sources) == 1
        
        context_manager.clear()
        assert len(context_manager.sources) == 0
