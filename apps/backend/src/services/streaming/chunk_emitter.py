"""
Chunk Emitter Service.

Extracted from streaming_handler.py for better testability and DRY compliance.
Handles uniform text chunking for SSE streaming.

REFACTOR-001: Phase 5.1 extraction.
"""

from __future__ import annotations

import json
from asyncio import Queue
from typing import Any, Dict, List

import structlog

logger = structlog.get_logger(__name__)


class ChunkEmitter:
    """
    Service for emitting text in uniform chunks for SSE streaming.

    Responsibilities:
        - Split text into consistent chunk sizes
        - Emit chunks to asyncio queues
        - Build properly formatted SSE chunk events
    """

    DEFAULT_CHUNK_SIZE = 50  # Characters per chunk

    @staticmethod
    def split_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> List[str]:
        """
        Split text into chunks of specified size.

        Pure function for easy testing.

        Args:
            text: The text to split
            chunk_size: Maximum characters per chunk

        Returns:
            List of text chunks
        """
        if not text:
            return []

        chunks = []
        for i in range(0, len(text), chunk_size):
            chunks.append(text[i : i + chunk_size])

        return chunks

    @staticmethod
    def build_chunk_event(content: str) -> Dict[str, Any]:
        """
        Build a properly formatted SSE chunk event.

        Args:
            content: The chunk content

        Returns:
            SSE event dict with event type and JSON data
        """
        return {
            "event": "chunk",
            "data": json.dumps({"content": content}),
        }

    @staticmethod
    async def emit_chunks(
        text: str,
        queue: Queue,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        log_progress: bool = False,
    ) -> int:
        """
        Split text into chunks and emit them to the queue.

        Args:
            text: The text to chunk and emit
            queue: The asyncio queue to put events into
            chunk_size: Maximum characters per chunk
            log_progress: Whether to log chunk emission progress

        Returns:
            Number of chunks emitted
        """
        if not text:
            return 0

        chunks = ChunkEmitter.split_text(text, chunk_size)
        total_chunks = len(chunks)

        if log_progress:
            logger.info(
                "chunk_emitter.starting",
                total_length=len(text),
                chunk_size=chunk_size,
                total_chunks=total_chunks,
            )

        for i, chunk_text in enumerate(chunks):
            chunk_event = ChunkEmitter.build_chunk_event(chunk_text)
            await queue.put(chunk_event)

            if log_progress:
                logger.debug(
                    "chunk_emitter.chunk_queued",
                    chunk_index=i,
                    chunk_length=len(chunk_text),
                )

        if log_progress:
            logger.info(
                "chunk_emitter.completed",
                chunks_emitted=total_chunks,
            )

        return total_chunks

    @staticmethod
    async def emit_text_as_chunks(
        text: str,
        queue: Queue,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> str:
        """
        Convenience method that emits chunks and returns the original text.

        Useful for cases where you need to track full_response while emitting.

        Args:
            text: The text to chunk and emit
            queue: The asyncio queue to put events into
            chunk_size: Maximum characters per chunk

        Returns:
            The original text (for assignment to full_response)
        """
        await ChunkEmitter.emit_chunks(text, queue, chunk_size)
        return text
