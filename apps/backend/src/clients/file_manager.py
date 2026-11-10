"""
HTTP client for the file-manager plugin.

This client allows the Core (backend) to delegate file operations
to the public file-manager plugin, following the Plugin-First Architecture.

Usage:
    client = await get_file_manager_client()
    metadata = await client.upload(file, filename, user_id, session_id)
    content = await client.download(file_path)
    text = await client.get_extracted_text(file_path)
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx
import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class FileMetadata(BaseModel):
    """Response model from file-manager upload."""

    file_id: str
    filename: str
    size: int
    mime_type: str
    minio_key: str
    sha256: str
    extracted_text: Optional[str] = None
    pages: Optional[int] = None


class FileManagerClient:
    """
    HTTP client for the file-manager plugin.

    Provides methods to upload, download, and extract text from files
    via the file-manager microservice.
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the file-manager client.

        Args:
            base_url: Base URL of file-manager service.
                      Defaults to FILE_MANAGER_URL env var or http://file-manager:8001
        """
        self.base_url = base_url or os.getenv(
            "FILE_MANAGER_URL", "http://file-manager:8001"
        )
        self._client: Optional[httpx.AsyncClient] = None

        logger.info("FileManagerClient initialized", base_url=self.base_url)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._client

    async def upload(
        self,
        file_content: bytes,
        filename: str,
        user_id: str,
        session_id: Optional[str] = None,
        content_type: str = "application/octet-stream",
    ) -> FileMetadata:
        """
        Upload a file to the file-manager.

        Args:
            file_content: File bytes
            filename: Original filename
            user_id: Owner user ID
            session_id: Optional chat session ID
            content_type: MIME type

        Returns:
            FileMetadata with file_id, minio_key, extracted_text, etc.
        """
        client = await self._get_client()

        files = {"file": (filename, file_content, content_type)}
        data = {"user_id": user_id}
        if session_id:
            data["session_id"] = session_id

        logger.info(
            "Uploading file to file-manager",
            filename=filename,
            user_id=user_id,
            size=len(file_content),
        )

        response = await client.post("/upload", files=files, data=data)
        response.raise_for_status()

        result = FileMetadata(**response.json())

        logger.info(
            "File uploaded via file-manager",
            file_id=result.file_id,
            minio_key=result.minio_key,
            has_text=result.extracted_text is not None,
        )

        return result

    async def download(self, file_path: str) -> bytes:
        """
        Download a file from the file-manager.

        Args:
            file_path: MinIO object path (user_id/session_id/file_id.ext)

        Returns:
            File content as bytes
        """
        client = await self._get_client()

        logger.debug("Downloading file from file-manager", file_path=file_path)

        response = await client.get(f"/download/{file_path}")
        response.raise_for_status()

        return response.content

    async def download_to_temp(self, file_path: str) -> Path:
        """
        Download a file to a temporary location.

        Useful for plugins that need to process files locally.

        Args:
            file_path: MinIO object path

        Returns:
            Path to temporary file (caller must delete)
        """
        content = await self.download(file_path)

        # Extract extension from path
        filename = file_path.split("/")[-1]
        suffix = Path(filename).suffix or ".bin"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        logger.debug(
            "File downloaded to temp",
            file_path=file_path,
            temp_path=str(tmp_path),
            size=len(content),
        )

        return tmp_path

    async def get_metadata(self, file_path: str, include_text: bool = True) -> dict:
        """
        Get file metadata from the file-manager.

        Args:
            file_path: MinIO object path
            include_text: Whether to include extracted text

        Returns:
            Dict with file_id, filename, size, content_type, extracted_text, pages
        """
        client = await self._get_client()

        params = {"include_text": str(include_text).lower()}
        response = await client.get(f"/metadata/{file_path}", params=params)
        response.raise_for_status()

        return response.json()

    async def get_extracted_text(self, file_path: str) -> str:
        """
        Get extracted text for a file.

        Args:
            file_path: MinIO object path

        Returns:
            Extracted text content
        """
        metadata = await self.get_metadata(file_path, include_text=True)
        return metadata.get("extracted_text", "")

    async def extract_text(self, file_path: str, force: bool = False) -> dict:
        """
        Extract or re-extract text from a file.

        Args:
            file_path: MinIO object path
            force: Force re-extraction even if cached

        Returns:
            Dict with text, pages, source (cache/extraction)
        """
        client = await self._get_client()

        params = {"force": str(force).lower()}
        response = await client.post(f"/extract/{file_path}", params=params)
        response.raise_for_status()

        return response.json()

    async def delete(self, file_path: str) -> None:
        """
        Delete a file from storage.

        Args:
            file_path: MinIO object path
        """
        client = await self._get_client()

        logger.info("Deleting file via file-manager", file_path=file_path)

        response = await client.delete(f"/files/{file_path}")
        response.raise_for_status()

    async def health_check(self) -> dict:
        """Check file-manager health status."""
        client = await self._get_client()

        response = await client.get("/health")
        response.raise_for_status()

        return response.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Singleton instance
_client: Optional[FileManagerClient] = None


async def get_file_manager_client() -> FileManagerClient:
    """
    Get the global FileManagerClient instance.

    Creates a new instance on first call.

    Returns:
        FileManagerClient instance
    """
    global _client
    if _client is None:
        _client = FileManagerClient()
    return _client


async def close_file_manager_client() -> None:
    """Close the global FileManagerClient."""
    global _client
    if _client:
        await _client.close()
        _client = None
