"""
Document Extraction Tool - Multi-tier text extraction.

Extracts text from PDF and image documents using a 3-tier fallback strategy:
1. pypdf (fast, for text-based PDFs)
2. Saptiva PDF SDK (complex layouts)
3. Saptiva OCR (image-based PDFs)
"""

from typing import Any, Dict, Optional

import structlog

from ...models.document import Document
from ...services.document_extraction import extract_text_from_pdf
from ...services.document_service import DocumentService
from ...services.minio_storage import get_minio_storage
from ..protocol import ToolCapability, ToolCategory, ToolSpec
from ..tool import Tool

logger = structlog.get_logger(__name__)


class DocumentExtractionTool(Tool):
    """
    Document Extraction Tool - Multi-tier text extraction.

    Extracts text from documents using intelligent fallback:
    1. Check cache (Redis)
    2. Try pypdf (fast)
    3. Fallback to Saptiva PDF SDK
    4. Final fallback to Saptiva OCR

    Supports:
    - PDF documents (text-based and image-based)
    - Image files (via OCR)
    - Automatic caching (1 hour TTL)
    - Page-level extraction
    """

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="extract_document_text",
            version="1.0.0",
            display_name="Document Text Extractor",
            description=(
                "Extracts text from PDF and image documents using a 3-tier fallback strategy. "
                "Automatically caches results for 1 hour. Supports both text-based and "
                "image-based PDFs with OCR fallback."
            ),
            category=ToolCategory.DOCUMENT_ANALYSIS,
            capabilities=[
                ToolCapability.ASYNC,
                ToolCapability.IDEMPOTENT,
                ToolCapability.CACHEABLE,
            ],
            input_schema={
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "string",
                        "description": "Document ID to extract text from",
                    },
                    "method": {
                        "type": "string",
                        "enum": ["auto", "pypdf", "saptiva_sdk", "ocr"],
                        "default": "auto",
                        "description": (
                            "Extraction method: auto (3-tier fallback), "
                            "pypdf (fast, text-only), saptiva_sdk (complex layouts), "
                            "ocr (image-based)"
                        ),
                    },
                    "page_numbers": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 1},
                        "description": "Specific page numbers to extract (1-indexed, optional)",
                    },
                    "include_metadata": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include document metadata in response",
                    },
                    "cache_ttl_seconds": {
                        "type": "integer",
                        "minimum": 60,
                        "maximum": 86400,
                        "default": 3600,
                        "description": "Cache TTL in seconds (default: 1 hour)",
                    },
                },
                "required": ["doc_id"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "text": {
                        "type": "string",
                        "description": "Extracted text content",
                    },
                    "method_used": {
                        "type": "string",
                        "enum": ["pypdf", "saptiva_sdk", "ocr", "cache"],
                        "description": "Extraction method that succeeded",
                    },
                    "pages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "page_number": {"type": "integer"},
                                "text": {"type": "string"},
                                "word_count": {"type": "integer"},
                            },
                        },
                        "description": "Per-page extraction (if requested)",
                    },
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "content_type": {"type": "string"},
                            "size_bytes": {"type": "integer"},
                            "total_pages": {"type": "integer"},
                            "char_count": {"type": "integer"},
                            "word_count": {"type": "integer"},
                            "extraction_duration_ms": {"type": "number"},
                            "cached": {"type": "boolean"},
                        },
                    },
                },
            },
            tags=["document", "pdf", "ocr", "extraction", "text", "parsing"],
            requires_auth=True,
            rate_limit={"calls_per_minute": 30},
            timeout_ms=60000,  # 60 seconds for OCR
            max_payload_size_kb=10,
        )

    async def validate_input(self, payload: Dict[str, Any]) -> None:
        """Validate input payload."""
        if "doc_id" not in payload:
            raise ValueError("Missing required field: doc_id")

        if not isinstance(payload["doc_id"], str):
            raise ValueError("doc_id must be a string")

        # Validate method enum
        if "method" in payload:
            valid_methods = ["auto", "pypdf", "saptiva_sdk", "ocr"]
            if payload["method"] not in valid_methods:
                raise ValueError(f"Invalid method. Must be one of: {valid_methods}")

        # Validate page_numbers if provided
        if "page_numbers" in payload:
            if not isinstance(payload["page_numbers"], list):
                raise ValueError("page_numbers must be an array")
            for page_num in payload["page_numbers"]:
                if not isinstance(page_num, int) or page_num < 1:
                    raise ValueError("page_numbers must contain positive integers")

    async def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute document text extraction.

        Args:
            payload: {
                "doc_id": "doc_123",
                "method": "auto",
                "page_numbers": [1, 2, 3],
                "include_metadata": True,
                "cache_ttl_seconds": 3600
            }
            context: {
                "user_id": "user_456"
            }

        Returns:
            Extracted text with metadata and method information
        """
        import time

        start_time = time.time()

        doc_id = payload["doc_id"]
        method = payload.get("method", "auto")
        page_numbers = payload.get("page_numbers")
        include_metadata = payload.get("include_metadata", True)
        cache_ttl = payload.get("cache_ttl_seconds", 3600)
        user_id = context.get("user_id") if context else None

        logger.info(
            "Document extraction tool execution started",
            doc_id=doc_id,
            method=method,
            page_numbers=page_numbers,
            user_id=user_id,
        )

        # 1. Get document
        doc = await Document.get(doc_id)
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")

        # 2. Check ownership
        if user_id and doc.user_id != user_id:
            raise PermissionError(
                f"User {user_id} not authorized to access document {doc_id}"
            )

        # 3. Check document type
        if doc.content_type not in [
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/tiff",
        ]:
            raise ValueError(
                f"Unsupported document type: {doc.content_type}. "
                "Supported types: PDF, PNG, JPEG, TIFF"
            )

        # 4. Extract text using existing service
        extracted_text = ""
        method_used: Optional[str] = None
        from_cache = False
        pages_payload: Optional[list[dict[str, Any]]] = None

        if method == "auto" and user_id:
            try:
                cache_payload = await DocumentService.get_document_text_from_cache(
                    document_ids=[doc_id],
                    user_id=user_id,
                )
                cached_entry = cache_payload.get(doc_id)
                cached_text = cached_entry.get("text") if cached_entry else None
                if cached_text:
                    extracted_text = cached_text
                    method_used = "cache"
                    from_cache = True
                    logger.info("Text retrieved from cache", doc_id=doc_id)
            except Exception as exc:
                logger.warning(
                    "Document cache retrieval failed",
                    doc_id=doc_id,
                    error=str(exc),
                )
        elif method == "auto" and not user_id:
            logger.debug(
                "Skipping cache lookup because user_id missing from context",
                doc_id=doc_id,
            )

        if not extracted_text:
            minio_storage = get_minio_storage()
            file_path, is_temp = minio_storage.materialize_document(
                doc.minio_key, filename=doc.filename
            )

            try:
                extraction_result = await extract_text_from_pdf(
                    pdf_path=file_path,
                    doc_id=doc_id,
                    cache_ttl_seconds=cache_ttl,
                )
                extracted_text = extraction_result.get("text", "") or ""
                method_used = extraction_result.get("method") or (
                    "hybrid" if method == "auto" else method
                )
                pages_payload = extraction_result.get("pages") or None
            finally:
                if is_temp and file_path.exists():
                    file_path.unlink()
        else:
            method_used = method_used or "cache"

        # 5. Build response
        duration_ms = (time.time() - start_time) * 1000

        result: Dict[str, Any] = {
            "doc_id": doc_id,
            "text": extracted_text or "",
            "method_used": method_used or "unknown",
        }

        normalized_pages = self._normalize_pages(pages_payload)
        if normalized_pages:
            if page_numbers:
                normalized_pages = [
                    page
                    for page in normalized_pages
                    if page["page_number"] in page_numbers
                ]
            result["pages"] = normalized_pages

        # Add metadata if requested
        if include_metadata:
            word_count = len(extracted_text.split()) if extracted_text else 0
            char_count = len(extracted_text) if extracted_text else 0

            result["metadata"] = {
                "filename": doc.filename,
                "content_type": doc.content_type,
                "size_bytes": doc.size_bytes,
                "char_count": char_count,
                "word_count": word_count,
                "extraction_duration_ms": duration_ms,
                "cached": from_cache,
            }

        # Add per-page extraction if page_numbers requested
        # TODO: Implement page-specific extraction
        if page_numbers:
            logger.warning(
                "Page-specific extraction not yet implemented",
                doc_id=doc_id,
                page_numbers=page_numbers,
            )

        logger.info(
            "Document extraction completed",
            doc_id=doc_id,
            method_used=method_used,
            char_count=len(extracted_text) if extracted_text else 0,
            duration_ms=duration_ms,
            cached=from_cache,
        )

        return result

    @staticmethod
    def _normalize_pages(pages: Optional[list[Dict[str, Any]]]) -> list[Dict[str, Any]]:
        """Convert extractor page payload to tool schema."""
        if not pages:
            return []

        normalized = []
        for page in pages:
            text = page.get("text") or page.get("text_md") or ""
            page_number = page.get("page_number") or page.get("page")
            normalized.append(
                {
                    "page_number": page_number,
                    "text": text,
                    "word_count": page.get("word_count") or len(text.split()),
                }
            )
        return normalized
