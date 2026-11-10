"""
In-memory event bus for file ingestion SSE streams.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Set

import structlog

from ..schemas.files import FileEventPayload

logger = structlog.get_logger(__name__)


class FileEventBus:
    def __init__(self) -> None:
        self._subscribers: Dict[str, Set[asyncio.Queue[FileEventPayload]]] = (
            defaultdict(set)
        )
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def subscribe(
        self, file_id: str
    ) -> AsyncIterator[asyncio.Queue[FileEventPayload]]:
        queue: asyncio.Queue[FileEventPayload] = asyncio.Queue()
        async with self._lock:
            self._subscribers[file_id].add(queue)

        try:
            yield queue
        finally:
            async with self._lock:
                subscribers = self._subscribers.get(file_id)
                if subscribers and queue in subscribers:
                    subscribers.remove(queue)
                if subscribers and len(subscribers) == 0:
                    self._subscribers.pop(file_id, None)

    async def publish(self, file_id: str, payload: FileEventPayload) -> None:
        async with self._lock:
            subscribers = list(self._subscribers.get(file_id, set()))

        if not subscribers:
            logger.debug(
                "No subscribers for file event", file_id=file_id, phase=payload.phase
            )
            return

        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning(
                    "Dropping file event due to full queue",
                    file_id=file_id,
                    phase=payload.phase,
                )


file_event_bus = FileEventBus()
