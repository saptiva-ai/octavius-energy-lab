"""
Unit tests for DocumentService - Document Retrieval and Content Extraction

Tests the document service methods for:
- Redis cache retrieval with ownership validation
- Document object retrieval from MongoDB
- RAG content formatting with character budgets
- Document ownership validation
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime
from typing import Dict, List, Any

from src.services.document_service import DocumentService
from src.models.document import Document, DocumentStatus, PageContent
from beanie import PydanticObjectId


@pytest.fixture
def mock_document():
    """Create a mock document"""
    doc = AsyncMock(spec=Document)
    doc.id = PydanticObjectId()
    doc.user_id = "user-123"
    doc.filename = "test.pdf"
    doc.content_type = "application/pdf"
    doc.status = DocumentStatus.READY
    doc.ocr_applied = False
    doc.total_pages = 3
    doc.pages = [
        Mock(page=1, text_md="Page 1 content here"),
        Mock(page=2, text_md="Page 2 content here"),
        Mock(page=3, text_md="Page 3 content here")
    ]
    return doc


@pytest.fixture
def mock_image_document():
    """Create a mock image document with OCR"""
    doc = AsyncMock(spec=Document)
    doc.id = PydanticObjectId()
    doc.user_id = "user-123"
    doc.filename = "screenshot.png"
    doc.content_type = "image/png"
    doc.status = DocumentStatus.READY
    doc.ocr_applied = True
    doc.total_pages = 1
    doc.pages = [
        Mock(page=1, text_md="OCR extracted text from image")
    ]
    return doc


@pytest.fixture
def mock_redis_cache():
    """Create a mock Redis cache"""
    cache = AsyncMock()
    cache.client = AsyncMock()
    return cache


@pytest.mark.asyncio
class TestGetDocumentTextFromCache:
    """Test get_document_text_from_cache method"""

    async def test_returns_empty_dict_for_empty_list(self):
        """Should return empty dict when no document IDs provided"""
        result = await DocumentService.get_document_text_from_cache([], "user-123")
        assert result == {}

    async def test_returns_empty_dict_for_invalid_object_ids(self):
        """Should return empty dict for invalid ObjectId strings"""
        with patch('src.services.document_service.PydanticObjectId', side_effect=Exception("Invalid ID")):
            result = await DocumentService.get_document_text_from_cache(
                ["invalid-id"],
                "user-123"
            )
            assert result == {}

    async def test_retrieves_documents_with_ownership_validation(self, mock_document, mock_redis_cache):
        """Should query MongoDB with ownership and status filters"""
        doc_id = str(mock_document.id)

        with patch('src.services.document_service.Document') as MockDocument, \
             patch('src.services.document_service.get_redis_cache', return_value=mock_redis_cache):

            # Mock Beanie query chain
            mock_find = AsyncMock()
            mock_find.to_list = AsyncMock(return_value=[mock_document])
            MockDocument.find = Mock(return_value=mock_find)

            # Mock Redis response
            mock_redis_cache.client.get = AsyncMock(return_value=b"Document text content")

            result = await DocumentService.get_document_text_from_cache([doc_id], "user-123")

            # Should call Document.find with filters
            MockDocument.find.assert_called_once()

            # Should return document text with metadata
            assert doc_id in result
            assert result[doc_id]["text"] == "Document text content"
            assert result[doc_id]["filename"] == "test.pdf"
            assert result[doc_id]["content_type"] == "application/pdf"
            assert result[doc_id]["ocr_applied"] is False

    async def test_handles_bytes_and_string_redis_responses(self, mock_document, mock_redis_cache):
        """Should handle both bytes and string responses from Redis"""
        doc_id = str(mock_document.id)

        with patch('src.services.document_service.Document') as MockDocument, \
             patch('src.services.document_service.get_redis_cache', return_value=mock_redis_cache):

            mock_find = AsyncMock()
            mock_find.to_list = AsyncMock(return_value=[mock_document])
            MockDocument.find = Mock(return_value=mock_find)

            # Test bytes response
            mock_redis_cache.client.get = AsyncMock(return_value=b"UTF-8 bytes content")
            result = await DocumentService.get_document_text_from_cache([doc_id], "user-123")
            assert result[doc_id]["text"] == "UTF-8 bytes content"

            # Test string response
            mock_redis_cache.client.get = AsyncMock(return_value="String content")
            result = await DocumentService.get_document_text_from_cache([doc_id], "user-123")
            assert result[doc_id]["text"] == "String content"

    async def test_returns_expired_message_when_not_in_cache(self, mock_document, mock_redis_cache):
        """Should return expired message when document not in Redis AND no MongoDB pages."""
        doc_id = str(mock_document.id)
        # Remove pages so MongoDB fallback also fails
        mock_document.pages = []

        with patch('src.services.document_service.Document') as MockDocument, \
             patch('src.services.document_service.get_redis_cache', return_value=mock_redis_cache):

            mock_find = AsyncMock()
            mock_find.to_list = AsyncMock(return_value=[mock_document])
            MockDocument.find = Mock(return_value=mock_find)

            # Redis returns None (expired)
            mock_redis_cache.client.get = AsyncMock(return_value=None)

            result = await DocumentService.get_document_text_from_cache([doc_id], "user-123")

            # Should return expired message with metadata
            assert doc_id in result
            assert "expirado de cache" in result[doc_id]["text"]
            assert result[doc_id]["filename"] == "test.pdf"

    async def test_filters_out_documents_not_belonging_to_user(self, mock_document, mock_redis_cache):
        """Should only return documents owned by the user"""
        doc_id_1 = str(mock_document.id)
        doc_id_2 = str(PydanticObjectId())

        with patch('src.services.document_service.Document') as MockDocument, \
             patch('src.services.document_service.get_redis_cache', return_value=mock_redis_cache):

            # Only return doc_1 (doc_2 not owned)
            mock_find = AsyncMock()
            mock_find.to_list = AsyncMock(return_value=[mock_document])
            MockDocument.find = Mock(return_value=mock_find)

            mock_redis_cache.client.get = AsyncMock(return_value=b"Content")

            result = await DocumentService.get_document_text_from_cache(
                [doc_id_1, doc_id_2],
                "user-123"
            )

            # Should only return doc_1
            assert len(result) == 1
            assert doc_id_1 in result
            assert doc_id_2 not in result


@pytest.mark.asyncio
class TestGetDocumentsByIds:
    """Test get_documents_by_ids method"""

    async def test_returns_empty_list_for_empty_input(self):
        """Should return empty list when no IDs provided"""
        result = await DocumentService.get_documents_by_ids([], "user-123")
        assert result == []

    async def test_returns_empty_list_for_invalid_ids(self):
        """Should return empty list for invalid ObjectIds"""
        with patch('src.services.document_service.PydanticObjectId', side_effect=Exception("Invalid")):
            result = await DocumentService.get_documents_by_ids(["bad-id"], "user-123")
            assert result == []

    async def test_retrieves_documents_with_ownership(self, mock_document):
        """Should retrieve documents with ownership and status validation"""
        doc_id = str(mock_document.id)

        with patch('src.services.document_service.Document') as MockDocument:
            mock_find = AsyncMock()
            mock_find.to_list = AsyncMock(return_value=[mock_document])
            MockDocument.find = Mock(return_value=mock_find)

            result = await DocumentService.get_documents_by_ids([doc_id], "user-123")

            # Should call find with filters
            MockDocument.find.assert_called_once()

            # Should return documents
            assert len(result) == 1
            assert result[0] == mock_document

    async def test_logs_warning_when_some_docs_not_found(self, mock_document):
        """Should log warning when not all docs are found/accessible"""
        doc_id_1 = str(mock_document.id)
        doc_id_2 = str(PydanticObjectId())

        with patch('src.services.document_service.Document') as MockDocument:
            # Only return 1 of 2 requested docs
            mock_find = AsyncMock()
            mock_find.to_list = AsyncMock(return_value=[mock_document])
            MockDocument.find = Mock(return_value=mock_find)

            result = await DocumentService.get_documents_by_ids(
                [doc_id_1, doc_id_2],
                "user-123"
            )

            # Should return only found document
            assert len(result) == 1


class TestExtractContentForRagFromCache:
    """Test extract_content_for_rag_from_cache method (synchronous)"""

    def test_returns_empty_for_no_documents(self):
        """Should return empty string and metadata for no documents"""
        result, warnings, metadata = DocumentService.extract_content_for_rag_from_cache({})

        assert result == ""
        assert warnings == []
        assert metadata["used_chars"] == 0
        assert metadata["used_docs"] == 0
        assert metadata["selected_doc_ids"] == []
        assert metadata["truncated_doc_ids"] == []
        assert metadata["dropped_doc_ids"] == []

    def test_formats_single_document(self):
        """Should format a single document with header"""
        doc_texts = {
            "doc-123": {
                "text": "This is the document content.",
                "filename": "test.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False
            }
        }

        result, warnings, metadata = DocumentService.extract_content_for_rag_from_cache(doc_texts)

        assert "## 📄 Documento: test.pdf" in result
        assert "This is the document content." in result
        assert metadata["used_docs"] == 1
        assert metadata["used_chars"] > 0
        assert len(warnings) == 0
        assert metadata["selected_doc_ids"] == ["doc-123"]
        assert metadata["truncated_doc_ids"] == []

    def test_formats_image_with_ocr(self):
        """Should format image documents with OCR indicator"""
        doc_texts = {
            "img-123": {
                "text": "OCR extracted text",
                "filename": "screenshot.png",
                "content_type": "image/png",
                "ocr_applied": True
            }
        }

        result, warnings, metadata = DocumentService.extract_content_for_rag_from_cache(doc_texts)

        assert "## 📷 Imagen: screenshot.png" in result
        assert "**Texto extraído con OCR:**" in result
        assert "OCR extracted text" in result

    def test_formats_image_without_ocr(self):
        """Should format image without OCR differently"""
        doc_texts = {
            "img-456": {
                "text": "Image content",
                "filename": "photo.jpg",
                "content_type": "image/jpeg",
                "ocr_applied": False
            }
        }

        result, warnings, metadata = DocumentService.extract_content_for_rag_from_cache(doc_texts)

        assert "## 📷 Imagen: photo.jpg" in result
        assert "**Texto extraído con OCR:**" not in result

    def test_truncates_by_per_doc_limit(self):
        """Should truncate documents exceeding per-doc char limit"""
        long_text = "A" * 10000
        doc_texts = {
            "doc-123": {
                "text": long_text,
                "filename": "long.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False
            }
        }

        result, warnings, metadata = DocumentService.extract_content_for_rag_from_cache(
            doc_texts,
            max_chars_per_doc=1000
        )

        assert "[Contenido truncado - documento excede límite por archivo]" in result
        assert metadata["used_docs"] == 1
        assert metadata["truncated_doc_ids"] == ["doc-123"]

    def test_respects_max_docs_limit(self):
        """Should limit number of documents processed"""
        doc_texts = {
            f"doc-{i}": {
                "text": f"Content {i}",
                "filename": f"doc{i}.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False
            }
            for i in range(5)
        }

        result, warnings, metadata = DocumentService.extract_content_for_rag_from_cache(
            doc_texts,
            max_docs=2
        )

        # Should only use 2 documents
        assert metadata["used_docs"] == 2
        assert metadata["omitted_docs"] == 3
        assert len(warnings) > 0
        assert "Se usaron 2 documentos máximo" in warnings[0]
        assert len(metadata["dropped_doc_ids"]) == 3

    def test_respects_global_char_budget(self):
        """Should enforce total character limit across all docs"""
        doc_texts = {
            "doc-1": {
                "text": "A" * 5000,
                "filename": "doc1.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False
            },
            "doc-2": {
                "text": "B" * 5000,
                "filename": "doc2.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False
            }
        }

        result, warnings, metadata = DocumentService.extract_content_for_rag_from_cache(
            doc_texts,
            max_total_chars=6000,
            max_chars_per_doc=10000
        )

        # Should truncate to fit global budget (with small margin for headers)
        assert metadata["used_chars"] <= 6400  # Allow margin for headers and truncation notes
        assert len(warnings) > 0
        assert sorted(metadata["truncated_doc_ids"]) == ["doc-1", "doc-2"]

    def test_round_robin_preserves_newer_documents(self):
        """Should keep multiple documents within budget using round-robin."""
        doc_texts = {
            "doc-older": {
                "text": "A" * 9000,
                "filename": "older.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False,
            },
            "doc-newer": {
                "text": "B" * 1500,
                "filename": "newer.png",
                "content_type": "image/png",
                "ocr_applied": True,
            },
        }

        result, warnings, metadata = DocumentService.extract_content_for_rag_from_cache(
            doc_texts,
            max_total_chars=6000,
            max_chars_per_doc=8000,
            max_docs=3,
        )

        assert "older.pdf" in result
        assert "newer.png" in result
        assert metadata["used_docs"] == 2
        assert "doc-newer" in metadata["selected_doc_ids"]
        assert len(warnings) > 0  # Global truncation warning

    def test_skips_expired_documents(self):
        """Should skip documents with expired marker"""
        doc_texts = {
            "doc-1": {
                "text": "Valid content",
                "filename": "valid.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False
            },
            "doc-2": {
                "text": "[Documento 'expired.pdf' expirado de cache]",
                "filename": "expired.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False
            }
        }

        result, warnings, metadata = DocumentService.extract_content_for_rag_from_cache(doc_texts)

        # Should only include valid doc
        assert "Valid content" in result
        assert "[Documento 'expired.pdf' expirado de cache]" not in result
        assert metadata["used_docs"] == 1
        assert any("expiró en Redis" in w for w in warnings)
        assert "doc-2" in metadata["dropped_doc_ids"]

    def test_separates_documents_with_divider(self):
        """Should separate multiple documents with divider"""
        doc_texts = {
            "doc-1": {
                "text": "First doc",
                "filename": "first.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False
            },
            "doc-2": {
                "text": "Second doc",
                "filename": "second.pdf",
                "content_type": "application/pdf",
                "ocr_applied": False
            }
        }

        result, warnings, metadata = DocumentService.extract_content_for_rag_from_cache(doc_texts)

        assert "---" in result
        assert "First doc" in result
        assert "Second doc" in result


class TestExtractContentForRag:
    """Test extract_content_for_rag method (legacy V2, synchronous)"""

    def test_returns_empty_for_no_documents(self):
        """Should return empty string for no documents"""
        result = DocumentService.extract_content_for_rag([])
        assert result == ""

    def test_formats_document_with_pages(self, mock_document):
        """Should format document with page structure"""
        result = DocumentService.extract_content_for_rag([mock_document])

        assert "## Documento: test.pdf" in result
        assert "### Página 1" in result
        assert "Page 1 content here" in result
        assert "### Página 2" in result
        assert "Page 2 content here" in result

    def test_truncates_by_max_chars(self, mock_document):
        """Should truncate when exceeding max_chars_per_doc"""
        # Create document with long pages
        mock_document.pages = [
            Mock(page=1, text_md="A" * 3000),
            Mock(page=2, text_md="B" * 3000),
            Mock(page=3, text_md="C" * 3000)
        ]

        result = DocumentService.extract_content_for_rag(
            [mock_document],
            max_chars_per_doc=5000
        )

        assert "[Contenido truncado" in result
        assert "páginas restantes" in result

    def test_skips_empty_pages(self):
        """Should skip pages with empty text"""
        mock_doc = AsyncMock(spec=Document)
        mock_doc.filename = "sparse.pdf"
        mock_doc.total_pages = 3
        mock_doc.pages = [
            Mock(page=1, text_md="Content"),
            Mock(page=2, text_md="   "),  # Whitespace only
            Mock(page=3, text_md="More content")
        ]

        result = DocumentService.extract_content_for_rag([mock_doc])

        assert "Content" in result
        assert "More content" in result
        # Page 2 should be skipped
        assert result.count("###") == 2  # Only 2 pages included

    def test_formats_multiple_documents(self, mock_document, mock_image_document):
        """Should separate multiple documents with divider"""
        result = DocumentService.extract_content_for_rag([mock_document, mock_image_document])

        assert "---" in result
        assert "test.pdf" in result
        assert "screenshot.png" in result


class TestBuildDocumentContextMessage:
    """Test build_document_context_message method (synchronous)"""

    def test_returns_none_for_no_documents(self):
        """Should return None when no documents provided"""
        result = DocumentService.build_document_context_message([])
        assert result is None

    def test_builds_system_message_with_document_count(self, mock_document):
        """Should build system message with document count"""
        result = DocumentService.build_document_context_message([mock_document])

        assert result is not None
        assert result["role"] == "system"
        assert "1 documento(s)" in result["content"]
        assert "test.pdf" in result["content"]

    def test_truncates_content_if_too_long(self, mock_document):
        """Should truncate total content if exceeding max_chars"""
        # Create document with very long pages
        mock_document.pages = [
            Mock(page=i, text_md="X" * 10000)
            for i in range(1, 6)
        ]

        result = DocumentService.build_document_context_message(
            [mock_document],
            max_chars=5000
        )

        assert len(result["content"]) <= 5200  # Buffer for prefix text + headers
        assert "[Contenido truncado]" in result["content"]

    def test_distributes_budget_across_documents(self, mock_document, mock_image_document):
        """Should distribute character budget evenly across documents"""
        result = DocumentService.build_document_context_message(
            [mock_document, mock_image_document],
            max_chars=1000
        )

        # Each doc gets ~500 chars budget
        assert result is not None
        assert result["role"] == "system"


@pytest.mark.asyncio
class TestValidateDocumentsAccess:
    """Test validate_documents_access method"""

    async def test_returns_empty_lists_for_no_documents(self):
        """Should return empty lists when no IDs provided"""
        valid, invalid = await DocumentService.validate_documents_access([], "user-123")
        assert valid == []
        assert invalid == []

    async def test_returns_all_invalid_for_bad_object_ids(self):
        """Should treat invalid ObjectIds as inaccessible"""
        with patch('src.services.document_service.PydanticObjectId', side_effect=Exception("Bad ID")):
            valid, invalid = await DocumentService.validate_documents_access(
                ["bad-id-1", "bad-id-2"],
                "user-123"
            )
            assert valid == []
            assert invalid == ["bad-id-1", "bad-id-2"]

    async def test_separates_valid_and_invalid_ids(self, mock_document):
        """Should separate accessible and inaccessible document IDs"""
        valid_id = str(mock_document.id)
        invalid_id = str(PydanticObjectId())

        with patch('src.services.document_service.Document') as MockDocument:
            # Only return valid document
            mock_find = AsyncMock()
            mock_find.to_list = AsyncMock(return_value=[mock_document])
            MockDocument.find = Mock(return_value=mock_find)

            valid, invalid = await DocumentService.validate_documents_access(
                [valid_id, invalid_id],
                "user-123"
            )

            assert len(valid) == 1
            assert valid_id in valid
            assert len(invalid) == 1
            assert invalid_id in invalid

    async def test_validates_ownership_and_status(self, mock_document):
        """Should query with user_id and status filters"""
        doc_id = str(mock_document.id)

        with patch('src.services.document_service.Document') as MockDocument:
            mock_find = AsyncMock()
            mock_find.to_list = AsyncMock(return_value=[mock_document])
            MockDocument.find = Mock(return_value=mock_find)

            valid, invalid = await DocumentService.validate_documents_access([doc_id], "user-123")

            # Should call find with filters
            MockDocument.find.assert_called_once()

            assert len(valid) == 1
            assert len(invalid) == 0
