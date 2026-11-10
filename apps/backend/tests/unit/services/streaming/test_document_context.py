"""
Unit tests for document_context module.

Tests:
- DocumentContextBuilder initialization
- DocumentContextBuilder.build method
- DocumentContextBuilder.format_for_prompt static method
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.streaming.document_context import DocumentContextBuilder

pytestmark = [pytest.mark.unit]


class TestDocumentContextBuilderInit:
    """Test DocumentContextBuilder initialization."""

    def test_default_values(self):
        """Test default initialization values."""
        builder = DocumentContextBuilder()

        assert builder.max_segments == 5
        assert builder.max_text_chars == 12000

    def test_custom_values(self):
        """Test custom initialization values."""
        builder = DocumentContextBuilder(max_segments=5, max_text_chars=8000)

        assert builder.max_segments == 5
        assert builder.max_text_chars == 8000


class TestBuildBasic:
    """Test basic build method behavior."""

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_document_ids(self):
        """Test returns None when no document IDs provided."""
        builder = DocumentContextBuilder()

        context, warnings = await builder.build(
            document_ids=[],
            session_id="session_123",
            user_id="user_456",
            question="What is this about?",
        )

        assert context is None
        assert warnings == []

    @pytest.mark.asyncio
    async def test_returns_none_for_none_document_ids(self):
        """Test handles None document_ids."""
        builder = DocumentContextBuilder()

        context, warnings = await builder.build(
            document_ids=None,
            session_id="session_123",
            user_id="user_456",
            question="Test question",
        )

        assert context is None
        assert warnings == []


class TestBuildWithRAG:
    """Test build method with RAG retrieval."""

    @pytest.mark.asyncio
    @patch("src.services.streaming.document_context.DocumentContextBuilder._retrieve_via_rag")
    async def test_uses_rag_result_when_available(self, mock_rag):
        """Test uses RAG result when segments are returned."""
        mock_rag.return_value = "Document content from RAG"
        builder = DocumentContextBuilder()

        context, warnings = await builder.build(
            document_ids=["doc_123"],
            session_id="session_123",
            user_id="user_456",
            question="What is the disponibilidad?",
        )

        assert context == "Document content from RAG"
        mock_rag.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.streaming.document_context.DocumentContextBuilder._retrieve_from_cache")
    @patch("src.services.streaming.document_context.DocumentContextBuilder._retrieve_via_rag")
    async def test_falls_back_to_cache_when_rag_returns_none(
        self, mock_rag, mock_cache
    ):
        """Test falls back to cache when RAG returns None."""
        mock_rag.return_value = None
        mock_cache.return_value = "Document content from cache"
        builder = DocumentContextBuilder()

        context, warnings = await builder.build(
            document_ids=["doc_123"],
            session_id="session_123",
            user_id="user_456",
            question="What is this?",
        )

        assert context == "Document content from cache"
        mock_rag.assert_called_once()
        mock_cache.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.streaming.document_context.DocumentContextBuilder._retrieve_via_rag")
    async def test_handles_exception_gracefully(self, mock_rag):
        """Test handles exceptions and returns warning."""
        mock_rag.side_effect = Exception("RAG connection failed")
        builder = DocumentContextBuilder()

        context, warnings = await builder.build(
            document_ids=["doc_123"],
            session_id="session_123",
            user_id="user_456",
            question="Test question",
        )

        assert context is None
        assert len(warnings) == 1
        assert "No se pudieron cargar" in warnings[0]


class TestRetrieveViaRAG:
    """Test _retrieve_via_rag method."""

    @pytest.mark.asyncio
    async def test_builds_context_from_segments(self):
        """Test builds context string from retrieved segments."""
        with patch(
            "src.mcp_integration.tools.get_segments.GetRelevantSegmentsTool"
        ) as mock_tool_class:
            mock_tool = AsyncMock()
            mock_tool.execute.return_value = {
                "segments": [
                    {
                        "doc_name": "Report.pdf",
                        "score": 0.95,
                        "text": "The disponibilidad index shows improvement.",
                    },
                    {
                        "doc_name": "Analysis.docx",
                        "score": 0.88,
                        "text": "Financial metrics are stable.",
                    },
                ],
                "ready_docs": 2,
                "total_docs": 2,
            }
            mock_tool_class.return_value = mock_tool

            builder = DocumentContextBuilder()
            warnings = []

            context = await builder._retrieve_via_rag(
                session_id="session_123",
                question="What about disponibilidad?",
                warnings=warnings,
            )

            assert context is not None
            assert "Report.pdf" in context
            assert "Analysis.docx" in context
            assert "disponibilidad" in context
            assert "0.95" in context
            assert len(warnings) == 0

    @pytest.mark.asyncio
    async def test_returns_none_when_no_segments(self):
        """Test returns None when no segments found."""
        with patch(
            "src.mcp_integration.tools.get_segments.GetRelevantSegmentsTool"
        ) as mock_tool_class:
            mock_tool = AsyncMock()
            mock_tool.execute.return_value = {
                "segments": [],
                "ready_docs": 0,
                "total_docs": 1,
            }
            mock_tool_class.return_value = mock_tool

            builder = DocumentContextBuilder()
            warnings = []

            context = await builder._retrieve_via_rag(
                session_id="session_123",
                question="Test",
                warnings=warnings,
            )

            assert context is None

    @pytest.mark.asyncio
    async def test_adds_warning_when_documents_processing(self):
        """Test adds warning when documents still processing."""
        with patch(
            "src.mcp_integration.tools.get_segments.GetRelevantSegmentsTool"
        ) as mock_tool_class:
            mock_tool = AsyncMock()
            mock_tool.execute.return_value = {
                "segments": [],
                "message": "Los documentos se están procesando",
                "ready_docs": 0,
                "total_docs": 2,
            }
            mock_tool_class.return_value = mock_tool

            builder = DocumentContextBuilder()
            warnings = []

            context = await builder._retrieve_via_rag(
                session_id="session_123",
                question="Test",
                warnings=warnings,
            )

            assert context is None
            assert len(warnings) == 1
            assert "procesando" in warnings[0]

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        """Test returns None on exception without warning."""
        with patch(
            "src.mcp_integration.tools.get_segments.GetRelevantSegmentsTool"
        ) as mock_tool_class:
            mock_tool_class.side_effect = Exception("Tool failed")

            builder = DocumentContextBuilder()
            warnings = []

            context = await builder._retrieve_via_rag(
                session_id="session_123",
                question="Test",
                warnings=warnings,
            )

            assert context is None
            # No warning added - will try fallback
            assert len(warnings) == 0


class TestRetrieveFromCache:
    """Test _retrieve_from_cache method."""

    @pytest.mark.asyncio
    async def test_builds_context_from_cache(self):
        """Test builds context from cached document text."""
        with patch("src.services.document_service.DocumentService") as mock_service:
            mock_service.get_document_text_from_cache = AsyncMock(
                return_value={
                    "doc_123": {
                        "text": "This is the document content.",
                        "filename": "Report.pdf",
                    },
                    "doc_456": {
                        "text": "Another document text.",
                        "filename": "Analysis.docx",
                    },
                }
            )

            builder = DocumentContextBuilder()
            warnings = []

            context = await builder._retrieve_from_cache(
                document_ids=["doc_123", "doc_456"],
                user_id="user_789",
                session_id="session_123",
                question="test query",
                warnings=warnings,
            )

            assert context is not None
            assert "Report.pdf" in context
            assert "document content" in context
            assert "---" in context  # Separator

    @pytest.mark.asyncio
    async def test_truncates_long_text(self):
        """Test truncates text to max_text_chars."""
        with patch("src.services.document_service.DocumentService") as mock_service:
            long_text = "x" * 10000
            mock_service.get_document_text_from_cache = AsyncMock(
                return_value={
                    "doc_123": {"text": long_text, "filename": "Large.pdf"},
                }
            )

            builder = DocumentContextBuilder(max_text_chars=100)
            warnings = []

            context = await builder._retrieve_from_cache(
                document_ids=["doc_123"],
                user_id="user_789",
                session_id="session_123",
                question="test query",
                warnings=warnings,
            )

            # Context should be truncated
            assert len(context) < 500  # Filename + 100 chars + formatting

    @pytest.mark.asyncio
    async def test_returns_none_when_no_docs_found(self):
        """Test returns None when no documents in cache."""
        with patch("src.services.document_service.DocumentService") as mock_service:
            mock_service.get_document_text_from_cache = AsyncMock(return_value={})

            builder = DocumentContextBuilder()
            warnings = []

            context = await builder._retrieve_from_cache(
                document_ids=["doc_123"],
                user_id="user_789",
                session_id="session_123",
                question="test query",
                warnings=warnings,
            )

            assert context is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_text(self):
        """Test returns None when documents have no extractable text."""
        with patch("src.services.document_service.DocumentService") as mock_service:
            mock_service.get_document_text_from_cache = AsyncMock(
                return_value={
                    "doc_123": {"text": "", "filename": "Empty.pdf"},
                }
            )

            builder = DocumentContextBuilder()
            warnings = []

            context = await builder._retrieve_from_cache(
                document_ids=["doc_123"],
                user_id="user_789",
                session_id="session_123",
                question="test query",
                warnings=warnings,
            )

            assert context is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        """Test returns None on exception."""
        with patch("src.services.document_service.DocumentService") as mock_service:
            mock_service.get_document_text_from_cache = AsyncMock(
                side_effect=Exception("Cache connection failed")
            )

            builder = DocumentContextBuilder()
            warnings = []

            context = await builder._retrieve_from_cache(
                document_ids=["doc_123"],
                user_id="user_789",
                session_id="session_123",
                question="test query",
                warnings=warnings,
            )

            assert context is None


class TestFormatForPrompt:
    """Test format_for_prompt static method."""

    def test_formats_with_header(self):
        """Test formats context with structured RAG instructions header."""
        context = "Document content here"

        result = DocumentContextBuilder.format_for_prompt(context)

        assert "CONTEXTO DOCUMENTAL" in result
        assert "Document content here" in result

    def test_returns_empty_for_empty_context(self):
        """Test returns empty string for empty context."""
        assert DocumentContextBuilder.format_for_prompt("") == ""
        assert DocumentContextBuilder.format_for_prompt(None) == ""

    def test_preserves_content(self):
        """Test preserves original content."""
        context = "Line 1\nLine 2\n**Bold text**"

        result = DocumentContextBuilder.format_for_prompt(context)

        assert "Line 1" in result
        assert "Line 2" in result
        assert "**Bold text**" in result
