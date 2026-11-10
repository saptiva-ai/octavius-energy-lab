"""
Storage management for uploaded documents.

V2: Uses MinIO for persistent storage with lifecycle policies.
Files are stored in 'temp-files' bucket with 1-day TTL.
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import structlog
from fastapi import UploadFile

from .minio_service import minio_service

logger = structlog.get_logger(__name__)


class FileTooLargeError(Exception):
    """Raised when an upload exceeds the configured size limit."""

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(f"File too large: {size_bytes} > {max_bytes}")
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


@dataclass(frozen=True)
class StorageConfig:
    root: Path
    ttl_seconds: int
    reap_interval_seconds: int
    max_disk_usage_percent: int


def _default_storage_root() -> Path:
    # V1: Use FILES_ROOT from settings (unified config)
    root_env = os.getenv("FILES_ROOT") or os.getenv(
        "DOCUMENTS_STORAGE_ROOT"
    )  # fallback for compat
    if root_env:
        return Path(root_env).expanduser().resolve()
    return Path(tempfile.gettempdir()) / "octavios_documents"


def _default_ttl_seconds() -> int:
    # V1: Prefer FILES_TTL_DAYS (new), fallback to DOCUMENTS_TTL_HOURS (legacy)
    if "FILES_TTL_DAYS" in os.environ:
        return int(os.getenv("FILES_TTL_DAYS", "7")) * 86400  # days to seconds
    return (
        int(os.getenv("DOCUMENTS_TTL_HOURS", "168")) * 3600
    )  # hours to seconds (168h = 7d default)


DEFAULT_STORAGE_CONFIG = StorageConfig(
    root=_default_storage_root(),
    ttl_seconds=_default_ttl_seconds(),
    reap_interval_seconds=int(os.getenv("DOCUMENTS_REAPER_INTERVAL_SECONDS", "900")),
    max_disk_usage_percent=int(os.getenv("DOCUMENTS_MAX_DISK_USAGE_PERCENT", "85")),
)


class Storage:
    """Simple filesystem-based storage backend."""

    def __init__(self, config: StorageConfig = DEFAULT_STORAGE_CONFIG) -> None:
        self.config = config
        self.config.root.mkdir(parents=True, exist_ok=True)
        self._reaper_task: Optional[asyncio.Task] = None
        logger.info(
            "Storage initialised",
            root=str(self.config.root),
            ttl_seconds=self.config.ttl_seconds,
            reap_interval_seconds=self.config.reap_interval_seconds,
            max_disk_usage_percent=self.config.max_disk_usage_percent,
        )

    async def save_upload(
        self,
        doc_id: str,
        upload: UploadFile,
        max_bytes: int,
    ) -> Tuple[str, str, str, int]:
        """
        Persist an UploadFile to MinIO streaming in 1MB chunks.

        Returns the MinIO bucket, object key, sanitized filename, and size.
        Raises FileTooLargeError if the stream exceeds max_bytes.
        """
        safe_name = self._sanitize_filename(upload.filename or "document")
        object_key = f"{doc_id}/{safe_name}"

        size = 0
        chunk_size = 1024 * 1024
        chunks = []

        await upload.seek(0)
        try:
            # Read all chunks and validate size
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLargeError(size, max_bytes)
                chunks.append(chunk)

            # Upload to MinIO
            file_data = io.BytesIO(b"".join(chunks))
            await minio_service.upload_file(
                bucket=minio_service.temp_files_bucket,
                object_name=object_key,
                data=file_data,
                length=size,
                content_type=upload.content_type or "application/octet-stream",
            )

            logger.info(
                "Upload stored in MinIO",
                doc_id=doc_id,
                bucket=minio_service.temp_files_bucket,
                key=object_key,
                size_bytes=size,
            )
            return minio_service.temp_files_bucket, object_key, safe_name, size

        except FileTooLargeError:
            raise
        except Exception as exc:
            logger.error(
                "Failed to save upload to MinIO", error=str(exc), doc_id=doc_id
            )
            raise
        finally:
            await upload.close()

    async def delete_document(self, doc_id: str) -> None:
        """Remove all files for a document from MinIO."""
        # List all objects with prefix doc_id/ in temp-files bucket
        try:
            objects = minio_service.client.list_objects(
                minio_service.temp_files_bucket, prefix=f"{doc_id}/", recursive=True
            )

            for obj in objects:
                await minio_service.delete_file(
                    minio_service.temp_files_bucket, obj.object_name
                )
                logger.info(
                    "Deleted document file from MinIO",
                    doc_id=doc_id,
                    key=obj.object_name,
                )
        except Exception as exc:
            logger.error(
                "Failed to delete document from MinIO", doc_id=doc_id, error=str(exc)
            )

    async def start_reaper(self) -> None:
        """
        V2: Reaper not needed - MinIO lifecycle policies handle expiration.
        Kept for backwards compatibility but does nothing.
        """
        logger.info("Storage reaper not needed - MinIO lifecycle policies handle TTL")

    async def stop_reaper(self) -> None:
        """V2: No-op - kept for backwards compatibility."""
        pass

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        base = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        return base or "document"


storage = Storage()
