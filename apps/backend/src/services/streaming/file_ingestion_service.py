"""
File Ingestion Service - Handles document ingestion for chat sessions.

REFACTOR-001: Extracted from streaming_handler.py handle_stream method.
Reduces streaming_handler.py by ~85 LOC.
"""

import asyncio
from datetime import datetime
from typing import List

import structlog

from ...mcp_integration.tools.ingest_files import IngestFilesTool
from ...models.document import Document, DocumentStatus

logger = structlog.get_logger(__name__)


class FileIngestionService:
    """
    Handles document ingestion with anti-hallucination wait logic.

    This service encapsulates the document ingestion flow:
    1. Check if documents are already READY (skip ingestion)
    2. Dispatch ingestion via IngestFilesTool
    3. Wait for documents to become READY (anti-hallucination)
    """

    # Default timeout settings
    DEFAULT_MAX_WAIT_SECONDS = 30
    DEFAULT_POLL_INTERVAL = 0.5
    MONGODB_PROPAGATION_DELAY = 0.1

    @classmethod
    async def ingest_files_if_needed(
        cls,
        session_id: str,
        file_ids: List[str],
        background_tasks,
        max_wait_seconds: float = DEFAULT_MAX_WAIT_SECONDS,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> bool:
        """
        Ingest files if not already READY, with anti-hallucination wait.

        Args:
            session_id: Chat session ID
            file_ids: List of document IDs to ingest
            background_tasks: FastAPI BackgroundTasks instance
            max_wait_seconds: Maximum time to wait for documents
            poll_interval: Interval between status checks

        Returns:
            True if all documents are READY, False if timeout occurred
        """
        if not file_ids or not background_tasks:
            return True

        # Check if all documents are already READY
        all_ready = await cls._check_all_documents_ready(file_ids)

        if all_ready:
            logger.info(
                "Skipping ingestion - documents already READY",
                session_id=session_id,
                file_count=len(file_ids),
            )
            return True

        # Dispatch ingestion
        try:
            await cls._dispatch_ingestion(session_id, file_ids, background_tasks)
        except Exception as ingest_exc:
            logger.error(
                "Document ingestion failed",
                session_id=session_id,
                error=str(ingest_exc),
                exc_info=True,
            )
            return False

        # Wait for documents to become READY
        return await cls._wait_for_documents_ready(
            session_id=session_id,
            file_ids=file_ids,
            max_wait_seconds=max_wait_seconds,
            poll_interval=poll_interval,
        )

    @classmethod
    async def _check_all_documents_ready(cls, file_ids: List[str]) -> bool:
        """Check if all documents have READY status."""
        ready_count = 0
        for doc_id in file_ids:
            doc = await Document.get(doc_id)
            if doc and doc.status == DocumentStatus.READY:
                ready_count += 1
        return ready_count == len(file_ids)

    @classmethod
    async def _dispatch_ingestion(
        cls,
        session_id: str,
        file_ids: List[str],
        background_tasks,
    ) -> None:
        """Dispatch document ingestion via IngestFilesTool."""
        ingest_tool = IngestFilesTool()
        result = await ingest_tool.execute(
            payload={
                "conversation_id": session_id,
                "file_refs": file_ids,
            },
            context={"background_tasks": background_tasks},
        )

        logger.info(
            "Document ingestion dispatched",
            session_id=session_id,
            file_count=len(file_ids),
            ingested=result.get("ingested", 0),
            status=result.get("status"),
        )

        # CRITICAL: Add delay to allow MongoDB write to propagate
        await asyncio.sleep(cls.MONGODB_PROPAGATION_DELAY)

        logger.info(
            "[RAG DEBUG] Waited for MongoDB write propagation",
            session_id=session_id,
            delay_ms=int(cls.MONGODB_PROPAGATION_DELAY * 1000),
            timestamp=datetime.utcnow().isoformat(),
        )

    @classmethod
    async def _wait_for_documents_ready(
        cls,
        session_id: str,
        file_ids: List[str],
        max_wait_seconds: float,
        poll_interval: float,
    ) -> bool:
        """
        Wait until all documents have READY status.

        Anti-hallucination measure: ensures RAG context is available
        before LLM generates response.
        """
        elapsed = 0.0

        while elapsed < max_wait_seconds:
            all_ready = True
            for doc_id in file_ids:
                doc = await Document.get(doc_id)
                if doc and doc.status != DocumentStatus.READY:
                    all_ready = False
                    break

            if all_ready:
                logger.info(
                    "[RAG ANTI-HALLUCINATION] All documents READY",
                    session_id=session_id,
                    elapsed_seconds=round(elapsed, 2),
                    file_count=len(file_ids),
                )
                return True

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning(
            "[RAG ANTI-HALLUCINATION] Timeout waiting for documents",
            session_id=session_id,
            timeout_seconds=max_wait_seconds,
            file_count=len(file_ids),
        )
        return False
