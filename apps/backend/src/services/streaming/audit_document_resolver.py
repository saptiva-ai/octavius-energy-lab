"""
Audit Document Resolver Service - Resolves and materializes documents for audit.

REFACTOR-001 Phase 7: Extracted from streaming_handler.py _stream_audit_response method.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import structlog

from ...models.document import Document
from ...services.minio_storage import get_minio_storage

logger = structlog.get_logger(__name__)


@dataclass
class ResolvedDocument:
    """Result of document resolution."""

    document: Document
    pdf_path: Path
    is_temp: bool


@dataclass
class ResolutionError:
    """Error during document resolution."""

    error_code: str
    error_message: str


class AuditDocumentResolver:
    """
    Resolves and materializes documents for audit operations.

    This service handles:
    1. Extracting filename from audit command
    2. Finding document by filename in document_ids
    3. Materializing PDF from MinIO storage
    """

    @classmethod
    def extract_filename_from_command(cls, message: str) -> str:
        """Extract filename from audit command string."""
        return message.strip().replace("Auditar archivo:", "").strip()

    @classmethod
    async def find_document_by_filename(
        cls,
        filename: str,
        document_ids: Optional[List[str]],
    ) -> Optional[Document]:
        """
        Find document by filename in the provided document IDs.

        Args:
            filename: The filename to search for
            document_ids: List of document IDs to search within

        Returns:
            Document if found, None otherwise
        """
        if not document_ids:
            return None

        for file_id in document_ids:
            try:
                doc = await Document.get(file_id)
                if doc and doc.filename == filename:
                    return doc
            except Exception as e:
                logger.warning(f"Could not load document {file_id}: {e}")

        return None

    @classmethod
    def materialize_pdf(
        cls,
        document: Document,
    ) -> Tuple[Optional[Path], bool, Optional[ResolutionError]]:
        """
        Materialize PDF from MinIO storage if needed.

        Args:
            document: The document to materialize

        Returns:
            Tuple of (pdf_path, is_temp, error)
        """
        pdf_path = Path(document.minio_key)
        is_temp = False

        # If file exists locally, no need to materialize
        if pdf_path.exists():
            return pdf_path, is_temp, None

        minio_storage = get_minio_storage()
        if not minio_storage:
            return (
                None,
                False,
                ResolutionError(
                    error_code="storage_unavailable",
                    error_message="Sistema de almacenamiento no disponible",
                ),
            )

        try:
            pdf_path, is_temp = minio_storage.materialize_document(
                document.minio_key,
                filename=document.filename,
                bucket=document.minio_bucket,
            )
            return pdf_path, is_temp, None
        except Exception as storage_exc:
            logger.error(
                "Failed to materialize PDF from MinIO",
                doc_id=str(document.id),
                error=str(storage_exc),
            )
            return (
                None,
                False,
                ResolutionError(
                    error_code="pdf_materialization_failed",
                    error_message=f"Error al cargar el archivo: {str(storage_exc)}",
                ),
            )

    @classmethod
    async def resolve(
        cls,
        message: str,
        document_ids: Optional[List[str]],
    ) -> Tuple[Optional[ResolvedDocument], Optional[ResolutionError]]:
        """
        Resolve and materialize a document for audit.

        Args:
            message: The audit command message
            document_ids: List of document IDs to search

        Returns:
            Tuple of (ResolvedDocument, ResolutionError) - one will be None
        """
        # Extract filename from command
        filename = cls.extract_filename_from_command(message)

        # Find document by filename
        document = await cls.find_document_by_filename(filename, document_ids)
        if not document:
            return None, ResolutionError(
                error_code="document_not_found",
                error_message=f"No se encontró el archivo: {filename}",
            )

        # Materialize PDF
        pdf_path, is_temp, error = cls.materialize_pdf(document)
        if error:
            return None, error

        return (
            ResolvedDocument(
                document=document,
                pdf_path=pdf_path,
                is_temp=is_temp,
            ),
            None,
        )
