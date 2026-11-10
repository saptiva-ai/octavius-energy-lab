"""
Extraction delegator service.

Delegates text extraction to file-manager plugin when available,
falls back to local extraction when not.

OPTIMIZATION 2026-01: This service allows removing pymupdf, pytesseract
from backend by delegating OCR-heavy operations to file-manager.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

import structlog

from ..clients.file_manager import FileManagerClient, get_file_manager_client
from ..models.document import PageContent

logger = structlog.get_logger(__name__)

# Feature flag to enable/disable file-manager delegation
DELEGATE_EXTRACTION = (
    os.getenv("DELEGATE_EXTRACTION_TO_FILE_MANAGER", "true").lower() == "true"
)


class ExtractionDelegator:
    """
    Service that delegates extraction to file-manager or uses local fallback.

    The delegation strategy is:
    1. If file is already in MinIO: call file-manager /extract/{path} endpoint
    2. If file-manager unavailable: fall back to local pypdf extraction (no OCR)

    Benefits:
    - Reduces backend image size by ~60-80MB (no pymupdf, pytesseract)
    - Leverages file-manager's Rust acceleration (47x faster for PDFs)
    - Centralizes extraction logic in one service
    """

    def __init__(self):
        self._client: Optional[FileManagerClient] = None
        self._file_manager_available: Optional[bool] = None

    async def _get_client(self) -> FileManagerClient:
        """Get file-manager client."""
        if self._client is None:
            self._client = await get_file_manager_client()
        return self._client

    async def _check_file_manager_health(self) -> bool:
        """Check if file-manager is available."""
        if self._file_manager_available is not None:
            return self._file_manager_available

        try:
            client = await self._get_client()
            await client.health_check()
            self._file_manager_available = True
            logger.info("File-manager is available for extraction delegation")
            return True
        except Exception as e:
            self._file_manager_available = False
            logger.warning(
                "File-manager not available, using local extraction",
                error=str(e),
            )
            return False

    async def extract_from_minio(
        self,
        minio_bucket: str,
        minio_key: str,
        content_type: str,
        force: bool = False,
    ) -> Tuple[str, Optional[int]]:
        """
        Extract text from a file that's already in MinIO.

        Args:
            minio_bucket: MinIO bucket name
            minio_key: MinIO object key
            content_type: MIME type of the file
            force: Force re-extraction even if cached

        Returns:
            Tuple of (extracted_text, page_count)
        """
        if DELEGATE_EXTRACTION and await self._check_file_manager_health():
            return await self._extract_via_file_manager(minio_key, force)

        # Fallback to local extraction
        return await self._extract_locally_from_minio(
            minio_bucket, minio_key, content_type
        )

    async def _extract_via_file_manager(
        self,
        minio_key: str,
        force: bool = False,
    ) -> Tuple[str, Optional[int]]:
        """
        Extract text via file-manager HTTP API.

        Args:
            minio_key: MinIO object path
            force: Force re-extraction

        Returns:
            Tuple of (extracted_text, page_count)
        """
        try:
            client = await self._get_client()
            result = await client.extract_text(minio_key, force=force)

            text = result.get("text", "")
            pages = result.get("pages")
            source = result.get("source", "unknown")

            logger.info(
                "Text extracted via file-manager",
                minio_key=minio_key,
                text_length=len(text),
                pages=pages,
                source=source,
            )

            return text, pages

        except Exception as e:
            logger.error(
                "File-manager extraction failed",
                minio_key=minio_key,
                error=str(e),
                exc_info=True,
            )
            raise

    async def _extract_locally_from_minio(
        self,
        minio_bucket: str,
        minio_key: str,
        content_type: str,
    ) -> Tuple[str, Optional[int]]:
        """
        Extract text locally after downloading from MinIO.

        This is the fallback when file-manager is not available.
        Uses only pypdf (no OCR) to keep backend lightweight.

        Args:
            minio_bucket: MinIO bucket
            minio_key: MinIO key
            content_type: MIME type

        Returns:
            Tuple of (extracted_text, page_count)
        """
        import tempfile

        from ..services.minio_service import minio_service

        # Download to temp file
        suffix = Path(minio_key).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)

        try:
            await minio_service.download_to_path(minio_bucket, minio_key, str(tmp_path))

            # Use local extraction
            pages = await self.extract_from_file(tmp_path, content_type)

            text = "\n\n".join(p.text_md for p in pages if p.text_md)
            page_count = len(pages) if pages else None

            return text, page_count

        finally:
            tmp_path.unlink(missing_ok=True)

    async def extract_from_file(
        self,
        file_path: Path,
        content_type: str,
    ) -> List[PageContent]:
        """
        Extract text from a local file.

        For PDFs: Uses pypdf for text extraction (no OCR fallback)
        For Images: Returns placeholder (OCR requires file-manager)

        Args:
            file_path: Path to local file
            content_type: MIME type

        Returns:
            List of PageContent
        """
        pages: List[PageContent] = []

        if content_type == "application/pdf":
            pages = await self._extract_pdf_local(file_path)
        elif content_type.startswith("image/"):
            # Images require OCR - delegate to file-manager or return placeholder
            if DELEGATE_EXTRACTION and await self._check_file_manager_health():
                # For images, we need to upload to MinIO first to use file-manager
                # This path is less common, so we return a placeholder
                pages = [
                    PageContent(
                        page=1,
                        text_md="[OCR de imagen requiere file-manager. Sube el archivo para extraccion completa.]",
                        has_table=False,
                    )
                ]
            else:
                pages = [
                    PageContent(
                        page=1,
                        text_md="[OCR no disponible - file-manager no accesible]",
                        has_table=False,
                    )
                ]
        else:
            pages = [
                PageContent(
                    page=1,
                    text_md=f"[Formato no soportado: {content_type}]",
                    has_table=False,
                )
            ]

        return pages

    async def _extract_pdf_local(self, file_path: Path) -> List[PageContent]:
        """
        Extract text from PDF using pypdf (lightweight, no OCR).

        This is the fallback when file-manager is not available.
        For scanned PDFs, text may be empty or minimal.
        """
        pages: List[PageContent] = []

        try:
            from pypdf import PdfReader

            reader = PdfReader(str(file_path))
            total_pages = len(reader.pages)

            logger.info(
                "Extracting PDF locally with pypdf (no OCR)",
                file_path=str(file_path),
                total_pages=total_pages,
            )

            for i, page in enumerate(reader.pages):
                try:
                    text = page.extract_text() or ""
                    text = text.strip()

                    if not text:
                        text = f"[Pagina {i + 1} sin texto extraible - puede ser imagen escaneada]"

                    pages.append(
                        PageContent(
                            page=i + 1,
                            text_md=text,
                            has_table=False,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to extract page {i + 1}", error=str(e))
                    pages.append(
                        PageContent(
                            page=i + 1,
                            text_md=f"[Error en pagina {i + 1}: {e}]",
                            has_table=False,
                        )
                    )

            total_chars = sum(len(p.text_md) for p in pages)
            logger.info(
                "PDF extraction completed (pypdf)",
                file_path=str(file_path),
                pages=len(pages),
                total_chars=total_chars,
            )

            return pages

        except ImportError:
            logger.error("pypdf not installed")
            return [
                PageContent(
                    page=1,
                    text_md="[Error: pypdf no instalado]",
                    has_table=False,
                )
            ]
        except Exception as e:
            logger.error(
                "PDF extraction failed",
                file_path=str(file_path),
                error=str(e),
                exc_info=True,
            )
            return [
                PageContent(
                    page=1,
                    text_md=f"[Error de extraccion: {e}]",
                    has_table=False,
                )
            ]


# Singleton
_delegator: Optional[ExtractionDelegator] = None


def get_extraction_delegator() -> ExtractionDelegator:
    """Get singleton ExtractionDelegator instance."""
    global _delegator
    if _delegator is None:
        _delegator = ExtractionDelegator()
    return _delegator


async def extract_text_delegated(
    file_path: Path,
    content_type: str,
) -> List[PageContent]:
    """
    Convenience function for extracting text with delegation.

    Replacement for extract_text_from_file that uses file-manager when available.
    """
    delegator = get_extraction_delegator()
    return await delegator.extract_from_file(file_path, content_type)


async def extract_text_from_minio_delegated(
    minio_bucket: str,
    minio_key: str,
    content_type: str,
    force: bool = False,
) -> Tuple[str, Optional[int]]:
    """
    Extract text from MinIO file with delegation to file-manager.

    This is the preferred method when the file is already in MinIO.
    """
    delegator = get_extraction_delegator()
    return await delegator.extract_from_minio(
        minio_bucket, minio_key, content_type, force
    )
