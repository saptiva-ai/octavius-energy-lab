"""
Streaming service for reading Aletheia events and providing SSE streams.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

import httpx
import structlog
from pydantic import BaseModel

from ..core.config import get_settings
from .aletheia_client import get_aletheia_client

logger = structlog.get_logger(__name__)


class StreamEvent(BaseModel):
    """Stream event model"""

    event_type: str
    task_id: str
    timestamp: datetime
    data: Dict[str, Any]
    progress: Optional[float] = None


class EventReader:
    """Reads events from Aletheia's NDJSON event stream"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.settings = get_settings()

    async def read_events_file(
        self, file_path: str
    ) -> AsyncGenerator[StreamEvent, None]:
        """Read events from a local NDJSON file"""

        try:
            if not os.path.exists(file_path):
                logger.warning(
                    "Events file not found", file_path=file_path, task_id=self.task_id
                )
                return

            # Track last position to only read new events
            last_position = 0

            while True:
                try:
                    with open(file_path, "r") as f:
                        f.seek(last_position)

                        for line in f:
                            line = line.strip()
                            if not line:
                                continue

                            try:
                                event_data = json.loads(line)

                                # Convert to our event format
                                event = StreamEvent(
                                    event_type=event_data.get("event_type", "unknown"),
                                    task_id=self.task_id,
                                    timestamp=datetime.fromisoformat(
                                        event_data.get(
                                            "timestamp", datetime.utcnow().isoformat()
                                        )
                                    ),
                                    data=event_data,
                                    progress=event_data.get("progress"),
                                )

                                yield event

                            except json.JSONDecodeError as e:
                                logger.warning(
                                    "Failed to parse event line",
                                    line=line,
                                    error=str(e),
                                    task_id=self.task_id,
                                )

                        last_position = f.tell()

                except IOError as e:
                    logger.error(
                        "Error reading events file", error=str(e), file_path=file_path
                    )
                    break

                # Wait before checking for new events
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(
                "Unexpected error in event reader", error=str(e), task_id=self.task_id
            )

    async def read_events_http(
        self, stream_url: str
    ) -> AsyncGenerator[StreamEvent, None]:
        """Read events from HTTP stream (for remote Aletheia)"""

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", stream_url) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            event_data = json.loads(line)

                            event = StreamEvent(
                                event_type=event_data.get("event_type", "unknown"),
                                task_id=self.task_id,
                                timestamp=datetime.fromisoformat(
                                    event_data.get(
                                        "timestamp", datetime.utcnow().isoformat()
                                    )
                                ),
                                data=event_data,
                                progress=event_data.get("progress"),
                            )

                            yield event

                        except json.JSONDecodeError as e:
                            logger.warning(
                                "Failed to parse event from stream",
                                line=line,
                                error=str(e),
                                task_id=self.task_id,
                            )

        except httpx.HTTPError as e:
            logger.error(
                "HTTP error reading event stream", error=str(e), url=stream_url
            )
        except Exception as e:
            logger.error(
                "Unexpected error reading HTTP stream",
                error=str(e),
                task_id=self.task_id,
            )


class StreamingService:
    """Service for managing event streams from Aletheia"""

    def __init__(self):
        self.settings = get_settings()
        self.active_streams: Dict[str, AsyncGenerator] = {}

    async def get_event_stream(self, task_id: str) -> AsyncGenerator[StreamEvent, None]:
        """Get event stream for a task"""

        # Check if we already have an active stream for this task
        if task_id in self.active_streams:
            logger.info("Reusing existing stream", task_id=task_id)
            async for event in self.active_streams[task_id]:
                yield event
            return

        reader = EventReader(task_id)

        try:
            # Try to read from local file first (for local Aletheia)
            local_file_path = f"./runs/{task_id}/events.ndjson"
            if os.path.exists(local_file_path):
                logger.info(
                    "Reading events from local file",
                    task_id=task_id,
                    file_path=local_file_path,
                )

                async for event in reader.read_events_file(local_file_path):
                    yield event
            else:
                # Fallback to HTTP stream
                aletheia_client = await get_aletheia_client()
                stream_url = await aletheia_client.get_events_stream_url(task_id)

                logger.info(
                    "Reading events from HTTP stream", task_id=task_id, url=stream_url
                )

                async for event in reader.read_events_http(stream_url):
                    yield event

        except Exception as e:
            logger.error("Error in event stream", error=str(e), task_id=task_id)

            # Send error event
            error_event = StreamEvent(
                event_type="stream_error",
                task_id=task_id,
                timestamp=datetime.utcnow(),
                data={"error": str(e)},
                progress=None,
            )
            yield error_event

        finally:
            # Clean up active stream
            if task_id in self.active_streams:
                del self.active_streams[task_id]

    async def generate_mock_events(
        self, task_id: str
    ) -> AsyncGenerator[StreamEvent, None]:
        """Generate mock events for testing (when Aletheia is not available)"""

        mock_events = [
            {
                "event_type": "task_started",
                "message": "Research task initiated",
                "progress": 0.0,
                "details": {"stage": "initialization"},
            },
            {
                "event_type": "search_started",
                "message": "Starting web search",
                "progress": 0.1,
                "details": {"search_queries": ["main query", "related terms"]},
            },
            {
                "event_type": "sources_found",
                "message": "Found 15 relevant sources",
                "progress": 0.3,
                "details": {
                    "sources_count": 15,
                    "domains": ["example.com", "academic.edu"],
                },
            },
            {
                "event_type": "processing_sources",
                "message": "Processing source content",
                "progress": 0.5,
                "details": {"processed": 8, "total": 15},
            },
            {
                "event_type": "evidence_extraction",
                "message": "Extracting evidence from sources",
                "progress": 0.7,
                "details": {"evidence_items": 12},
            },
            {
                "event_type": "synthesis_started",
                "message": "Synthesizing findings",
                "progress": 0.9,
                "details": {"synthesis_method": "iterative_refinement"},
            },
            {
                "event_type": "task_completed",
                "message": "Research completed successfully",
                "progress": 1.0,
                "details": {
                    "total_sources": 15,
                    "evidence_items": 12,
                    "report_size": "2.3KB",
                },
            },
        ]

        logger.info(
            "Generating mock events", task_id=task_id, event_count=len(mock_events)
        )

        for i, event_data in enumerate(mock_events):
            # Create event
            event = StreamEvent(
                event_type=event_data["event_type"],
                task_id=task_id,
                timestamp=datetime.utcnow(),
                data=event_data,
                progress=event_data["progress"],
            )

            yield event

            # Add delay between events (except for the last one)
            if i < len(mock_events) - 1:
                await asyncio.sleep(2)

        logger.info("Mock event stream completed", task_id=task_id)

    async def create_sse_generator(
        self, task_id: str, use_mock: bool = True
    ) -> AsyncGenerator[str, None]:
        """Create Server-Sent Events formatted generator"""

        try:
            # Send initial connection event
            connection_event = {
                "event_type": "connection_established",
                "task_id": task_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {"message": "Event stream connected"},
            }

            yield f"data: {json.dumps(connection_event)}\n\n"

            # Choose event source
            if use_mock:
                event_stream = self.generate_mock_events(task_id)
            else:
                event_stream = self.get_event_stream(task_id)

            # Stream events
            async for event in event_stream:
                event_dict = event.model_dump()
                event_dict["timestamp"] = event.timestamp.isoformat()

                yield f"data: {json.dumps(event_dict)}\n\n"

            # Send completion event
            completion_event = {
                "event_type": "stream_completed",
                "task_id": task_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {"message": "Event stream completed"},
            }

            yield f"data: {json.dumps(completion_event)}\n\n"

        except Exception as e:
            logger.error("Error in SSE generator", error=str(e), task_id=task_id)

            # Send error event
            error_event = {
                "event_type": "stream_error",
                "task_id": task_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {"error": str(e)},
            }

            yield f"data: {json.dumps(error_event)}\n\n"


# Singleton instance
_streaming_service: Optional[StreamingService] = None


def get_streaming_service() -> StreamingService:
    """Get singleton streaming service instance"""
    global _streaming_service

    if _streaming_service is None:
        _streaming_service = StreamingService()

    return _streaming_service
