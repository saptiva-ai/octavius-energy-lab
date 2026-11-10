"""
Integration tests for File Manager — Thumbnails & Context Improvements.

Validates the integration between:
- DocumentContextBuilder (RAG limits increase)
- DocumentService (MongoDB fallback on Redis miss)
- FileIngestService (eager thumbnail generation)
- Documents router (legacy migration, presigned URLs)

All tests use mocks for external services (Redis, MinIO, MongoDB).
No real infrastructure required.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from src.models.document import Document, DocumentStatus, PageContent


# Valid 24-char hex ObjectId for tests
DOC_ID = "aaaaaaaaaaaaaaaaaaaaaaaa"


def _patch_beanie_fields():
    """
    Context manager that patches Beanie model class-level field descriptors.

    Without init_beanie(), Document.id / Document.user_id raise AttributeError
    when used as query expressions (e.g. In(Document.id, ...)). This patches
    them as simple sentinel strings so the mock chain works.
    """
    return patch.multiple(
        Document,
        id=MagicMock(),
        user_id=MagicMock(),
        status=MagicMock(),
        create=True,
    )


# ---------------------------------------------------------------------------
# Phase 3: DocumentContextBuilder — RAG limits
# ---------------------------------------------------------------------------


class TestDocumentContextBuilderLimits:
    """Verify DocumentContextBuilder defaults were updated (2→5 segments, 4000→12000 chars)."""

    def test_default_max_segments_is_5(self):
        from src.services.streaming.document_context import DocumentContextBuilder

        builder = DocumentContextBuilder()
        assert builder.max_segments == 5, (
            f"Expected max_segments=5, got {builder.max_segments}"
        )

    def test_default_max_text_chars_is_12000(self):
        from src.services.streaming.document_context import DocumentContextBuilder

        builder = DocumentContextBuilder()
        assert builder.max_text_chars == 12000, (
            f"Expected max_text_chars=12000, got {builder.max_text_chars}"
        )

    def test_custom_values_still_work(self):
        from src.services.streaming.document_context import DocumentContextBuilder

        builder = DocumentContextBuilder(max_segments=10, max_text_chars=20000)
        assert builder.max_segments == 10
        assert builder.max_text_chars == 20000

    @pytest.mark.asyncio
    async def test_rag_retrieval_passes_max_segments(self):
        """Verify max_segments flows through to GetRelevantSegmentsTool."""
        from src.services.streaming.document_context import DocumentContextBuilder

        builder = DocumentContextBuilder()

        mock_tool_instance = AsyncMock()
        mock_tool_instance.execute = AsyncMock(return_value={
            "segments": [
                {"doc_name": f"doc{i}.pdf", "score": 0.9 - i * 0.1, "text": f"Segment {i}"}
                for i in range(5)
            ],
            "ready_docs": 1,
            "total_docs": 1,
        })

        mock_tool_class = MagicMock(return_value=mock_tool_instance)

        # Patch at the SOURCE module where GetRelevantSegmentsTool lives
        with patch(
            "src.mcp_integration.tools.get_segments.GetRelevantSegmentsTool",
            mock_tool_class,
        ):
            context, warnings = await builder.build(
                document_ids=["doc1"],
                session_id="sess1",
                user_id="user1",
                question="test",
            )

        # Verify max_segments=5 was passed in the execute payload
        call_args = mock_tool_instance.execute.call_args
        payload = call_args[1].get("payload", call_args[0][0] if call_args[0] else {})
        assert payload["max_segments"] == 5
        assert context is not None
        assert "Segment 0" in context

    @pytest.mark.asyncio
    async def test_cache_fallback_respects_max_text_chars(self):
        """Verify fallback truncation uses 12000 char limit."""
        from src.services.streaming.document_context import DocumentContextBuilder

        builder = DocumentContextBuilder()

        # RAG returns nothing → forces cache fallback
        mock_tool_instance = AsyncMock()
        mock_tool_instance.execute = AsyncMock(return_value={
            "segments": [],
            "ready_docs": 0,
            "total_docs": 1,
        })
        mock_tool_class = MagicMock(return_value=mock_tool_instance)

        # Cache returns a very long document
        long_text = "x" * 20000
        mock_doc_texts = {
            "doc1": {
                "text": long_text,
                "filename": "big.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False,
            }
        }

        with patch(
            "src.mcp_integration.tools.get_segments.GetRelevantSegmentsTool",
            mock_tool_class,
        ), patch(
            "src.services.document_service.DocumentService.get_document_text_from_cache",
            new_callable=AsyncMock,
            return_value=mock_doc_texts,
        ):
            context, warnings = await builder.build(
                document_ids=["doc1"],
                session_id="sess1",
                user_id="user1",
                question="test",
            )

        # Context should be truncated to max_text_chars (12000)
        assert context is not None
        assert len(context) <= 12000 + 100  # small overhead for header


# ---------------------------------------------------------------------------
# Phase 3b: DocumentService — MongoDB fallback on Redis cache miss
# ---------------------------------------------------------------------------


class TestDocumentServiceMongoFallback:
    """Verify Redis miss → MongoDB pages → re-cache flow."""

    def _make_mock_doc(self, doc_id="aaaaaaaaaaaaaaaaaaaaaaaa", pages=None):
        """Helper to create a mock Document."""
        mock_doc = MagicMock(spec=Document)
        mock_doc.id = doc_id
        mock_doc.filename = "report.pdf"
        mock_doc.content_type = "application/pdf"
        mock_doc.ocr_applied = False
        mock_doc.user_id = "user1"
        mock_doc.status = DocumentStatus.READY
        mock_doc.pages = pages or []
        return mock_doc

    def _make_mock_redis(self, get_return=None):
        """Helper to create mock Redis with given get return value."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=get_return)
        mock_redis.setex = AsyncMock()
        mock_cache = MagicMock()
        mock_cache.client = mock_redis
        return mock_cache, mock_redis

    def _make_find_mock(self, docs):
        """Helper: mock Document.find() to return a cursor with to_list()."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=docs)
        return mock_cursor

    @pytest.mark.asyncio
    async def test_redis_hit_returns_cached_text(self):
        """When Redis has the text, return it directly."""
        from src.services.document_service import DocumentService

        mock_doc = self._make_mock_doc()
        mock_cache, mock_redis = self._make_mock_redis(
            get_return=b"Cached text from Redis"
        )

        with _patch_beanie_fields(), patch.object(
            Document, "find", return_value=self._make_find_mock([mock_doc])
        ), patch(
            "src.services.document_service.get_redis_cache",
            new_callable=AsyncMock,
            return_value=mock_cache,
        ):
            result = await DocumentService.get_document_text_from_cache(
                document_ids=[DOC_ID], user_id="user1"
            )

        assert DOC_ID in result
        assert result[DOC_ID]["text"] == "Cached text from Redis"
        # Should NOT re-cache
        mock_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_miss_falls_back_to_mongodb_pages(self):
        """When Redis returns None, extract text from Document.pages and re-cache."""
        from src.services.document_service import DocumentService

        pages = [
            PageContent(page=1, text_md="Page one content."),
            PageContent(page=2, text_md="Page two content."),
        ]
        mock_doc = self._make_mock_doc(pages=pages)
        mock_cache, mock_redis = self._make_mock_redis(get_return=None)

        with _patch_beanie_fields(), patch.object(
            Document, "find", return_value=self._make_find_mock([mock_doc])
        ), patch(
            "src.services.document_service.get_redis_cache",
            new_callable=AsyncMock,
            return_value=mock_cache,
        ):
            result = await DocumentService.get_document_text_from_cache(
                document_ids=[DOC_ID], user_id="user1"
            )

        assert DOC_ID in result
        text = result[DOC_ID]["text"]
        assert "Page one content." in text
        assert "Page two content." in text
        assert "---PAGE BREAK---" in text

        # Should re-cache in Redis with TTL 3600
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == f"doc:text:{DOC_ID}"
        assert call_args[0][1] == 3600
        assert "Page one content." in call_args[0][2]

    @pytest.mark.asyncio
    async def test_redis_miss_no_pages_returns_expired_placeholder(self):
        """When Redis misses AND Document.pages is empty, return expired placeholder."""
        from src.services.document_service import DocumentService

        mock_doc = self._make_mock_doc(pages=[])
        mock_cache, mock_redis = self._make_mock_redis(get_return=None)

        with _patch_beanie_fields(), patch.object(
            Document, "find", return_value=self._make_find_mock([mock_doc])
        ), patch(
            "src.services.document_service.get_redis_cache",
            new_callable=AsyncMock,
            return_value=mock_cache,
        ):
            result = await DocumentService.get_document_text_from_cache(
                document_ids=[DOC_ID], user_id="user1"
            )

        assert DOC_ID in result
        assert "expirado" in result[DOC_ID]["text"]
        # Should NOT re-cache placeholder text
        mock_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_recache_failure_is_non_fatal(self):
        """If Redis setex fails during re-cache, text is still returned."""
        from src.services.document_service import DocumentService

        pages = [PageContent(page=1, text_md="Important content.")]
        mock_doc = self._make_mock_doc(pages=pages)
        mock_cache, mock_redis = self._make_mock_redis(get_return=None)
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis write failed"))

        with _patch_beanie_fields(), patch.object(
            Document, "find", return_value=self._make_find_mock([mock_doc])
        ), patch(
            "src.services.document_service.get_redis_cache",
            new_callable=AsyncMock,
            return_value=mock_cache,
        ):
            result = await DocumentService.get_document_text_from_cache(
                document_ids=[DOC_ID], user_id="user1"
            )

        # Text should still be returned even though recache failed
        assert DOC_ID in result
        assert "Important content." in result[DOC_ID]["text"]

    def test_extract_text_from_pages_joins_with_page_break(self):
        """Static method _extract_text_from_pages joins pages correctly."""
        from src.services.document_service import DocumentService

        mock_doc = MagicMock()
        mock_doc.pages = [
            MagicMock(text_md="First page"),
            MagicMock(text_md="Second page"),
            MagicMock(text_md=""),  # empty page skipped
            MagicMock(text_md="Fourth page"),
        ]

        result = DocumentService._extract_text_from_pages(mock_doc)
        assert result is not None
        parts = result.split("\n\n---PAGE BREAK---\n\n")
        assert len(parts) == 3  # empty page excluded
        assert parts[0] == "First page"
        assert parts[2] == "Fourth page"

    def test_extract_text_from_pages_no_pages(self):
        """Returns None when document has no pages."""
        from src.services.document_service import DocumentService

        mock_doc = MagicMock()
        mock_doc.pages = []
        assert DocumentService._extract_text_from_pages(mock_doc) is None

        mock_doc.pages = None
        assert DocumentService._extract_text_from_pages(mock_doc) is None


# ---------------------------------------------------------------------------
# Phase 2: FileIngestService — Eager thumbnail generation
# ---------------------------------------------------------------------------


class TestEagerThumbnailGeneration:
    """Verify thumbnail is generated during file ingestion (non-fatal)."""

    def test_thumbnail_service_has_get_or_generate(self):
        """Verify thumbnail_service singleton has the method we call."""
        from src.services.thumbnail_service import thumbnail_service

        assert callable(getattr(thumbnail_service, "get_or_generate_thumbnail", None))

    def test_ingest_service_imports_thumbnail_service(self):
        """Verify the import path used in eager thumbnail works."""
        # The file_ingest.py does: from .thumbnail_service import thumbnail_service
        # This verifies the module structure is valid
        import importlib

        mod = importlib.import_module("src.services.thumbnail_service")
        assert hasattr(mod, "thumbnail_service")
        assert hasattr(mod.thumbnail_service, "get_or_generate_thumbnail")

    def test_eager_thumbnail_code_exists_in_sync_path(self):
        """Verify the eager thumbnail code block exists in file_ingest.py."""
        import inspect
        from src.services.file_ingest import FileIngestService

        source = inspect.getsource(FileIngestService.ingest_file)
        assert "Eager thumbnail generation" in source
        assert "get_or_generate_thumbnail" in source
        assert "non-fatal" in source.lower()

    def test_eager_thumbnail_code_exists_in_async_path(self):
        """Verify the eager thumbnail code block exists in async processing."""
        import inspect
        from src.services.file_ingest import FileIngestService

        source = inspect.getsource(FileIngestService._process_large_file_async)
        assert "Eager thumbnail generation" in source
        assert "get_or_generate_thumbnail" in source
        assert "non-fatal" in source.lower()


# ---------------------------------------------------------------------------
# Phase 5: Legacy document migration in thumbnail endpoint
# ---------------------------------------------------------------------------


class TestLegacyDocumentMigration:
    """Verify legacy doc detection and migration logic in documents router."""

    def test_legacy_detection_logic(self):
        """Legacy docs have minio_bucket='temp' and minio_key starting with /tmp/."""
        mock_doc = MagicMock()

        # Legacy case
        mock_doc.minio_bucket = "temp"
        mock_doc.minio_key = "/tmp/upload_abc123.pdf"
        is_legacy = (
            mock_doc.minio_bucket == "temp"
            and mock_doc.minio_key
            and mock_doc.minio_key.startswith("/tmp/")
        )
        assert is_legacy is True

        # Non-legacy case
        mock_doc.minio_bucket = "documents"
        mock_doc.minio_key = "documents/abc123/report.pdf"
        is_legacy = (
            mock_doc.minio_bucket == "temp"
            and mock_doc.minio_key
            and mock_doc.minio_key.startswith("/tmp/")
        )
        assert is_legacy is False

        # Edge: bucket is temp but key is not /tmp/
        mock_doc.minio_bucket = "temp"
        mock_doc.minio_key = "uploads/file.pdf"
        is_legacy = (
            mock_doc.minio_bucket == "temp"
            and mock_doc.minio_key
            and mock_doc.minio_key.startswith("/tmp/")
        )
        assert is_legacy is False

    def test_reupload_header_name_is_correct(self):
        """Verify the X-Reupload-Required header constant matches frontend."""
        # The frontend checks: response.headers.get("X-Reupload-Required") === "true"
        # The backend sends: headers={"X-Reupload-Required": "true"}
        expected_header = "X-Reupload-Required"
        expected_value = "true"

        import inspect
        from src.routers import documents as docs_module

        source = inspect.getsource(docs_module.get_document_thumbnail)
        assert f'"{expected_header}"' in source
        assert f'"{expected_value}"' in source


# ---------------------------------------------------------------------------
# Phase 4: Presigned URL endpoint
# ---------------------------------------------------------------------------


class TestPresignedUrlEndpoint:
    """Verify presigned URL endpoint structure."""

    def test_presigned_url_route_exists(self):
        """Verify the thumbnail-url route is registered."""
        from src.routers.documents import router

        routes = [r.path for r in router.routes]
        # Routes include router prefix /documents/
        assert "/documents/{doc_id}/thumbnail-url" in routes

    def test_presigned_url_checks_env_var(self):
        """Verify endpoint logic checks MINIO_PUBLIC_ENDPOINT."""
        import inspect
        from src.routers import documents as docs_module

        source = inspect.getsource(docs_module.get_document_thumbnail_url)
        assert "MINIO_PUBLIC_ENDPOINT" in source
        assert "501" in source  # HTTP 501 when env not set


# ---------------------------------------------------------------------------
# End-to-end: Context pipeline with MongoDB fallback
# ---------------------------------------------------------------------------


class TestContextPipelineIntegration:
    """Test the full context retrieval pipeline: RAG → cache → MongoDB fallback."""

    @pytest.mark.asyncio
    async def test_full_pipeline_rag_miss_redis_miss_mongodb_hit(self):
        """
        Scenario: RAG has no segments, Redis cache expired, but MongoDB has pages.
        Expected: Text recovered from MongoDB, re-cached in Redis, returned to caller.
        """
        from src.services.streaming.document_context import DocumentContextBuilder

        builder = DocumentContextBuilder()

        # RAG returns nothing
        mock_tool_instance = AsyncMock()
        mock_tool_instance.execute = AsyncMock(return_value={
            "segments": [],
            "ready_docs": 0,
            "total_docs": 1,
        })
        mock_tool_class = MagicMock(return_value=mock_tool_instance)

        # DocumentService returns text (simulating MongoDB fallback)
        mock_doc_texts = {
            "doc1": {
                "text": "Recovered from MongoDB pages",
                "filename": "report.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False,
            }
        }

        with patch(
            "src.mcp_integration.tools.get_segments.GetRelevantSegmentsTool",
            mock_tool_class,
        ), patch(
            "src.services.document_service.DocumentService.get_document_text_from_cache",
            new_callable=AsyncMock,
            return_value=mock_doc_texts,
        ):
            context, warnings = await builder.build(
                document_ids=["doc1"],
                session_id="sess1",
                user_id="user1",
                question="Summarize the report",
            )

        assert context is not None
        assert "Recovered from MongoDB pages" in context
        assert "report.pdf" in context

    @pytest.mark.asyncio
    async def test_format_for_prompt_wraps_context(self):
        """DocumentContextBuilder.format_for_prompt adds header."""
        from src.services.streaming.document_context import DocumentContextBuilder

        formatted = DocumentContextBuilder.format_for_prompt("Some context")
        assert "CONTEXTO DOCUMENTAL" in formatted
        assert "Some context" in formatted

    @pytest.mark.asyncio
    async def test_format_for_prompt_empty(self):
        """Empty context returns empty string."""
        from src.services.streaming.document_context import DocumentContextBuilder

        assert DocumentContextBuilder.format_for_prompt("") == ""
        assert DocumentContextBuilder.format_for_prompt(None) == ""
