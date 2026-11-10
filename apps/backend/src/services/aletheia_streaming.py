"""
Aletheia event streaming service for real-time research updates.
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, Optional

import aiohttp
import structlog
from pydantic import BaseModel

from ..core.config import get_settings
from ..services.aletheia_client import get_aletheia_client

logger = structlog.get_logger(__name__)


class StreamEvent(BaseModel):
    """Real-time stream event from Aletheia."""

    event_type: str
    task_id: str
    timestamp: datetime
    data: Dict[str, Any]
    sequence: Optional[int] = None


class AletheiaEventStreamer:
    """Service for streaming events from Aletheia's NDJSON endpoint."""

    def __init__(self):
        self.settings = get_settings()
        self._active_streams: Dict[str, bool] = {}
        self._stream_buffers: Dict[str, asyncio.Queue] = {}
        self._buffer_size = 100  # Maximum events in buffer

    async def stream_task_events(
        self,
        task_id: str,
        max_duration: int = 3600,  # 1 hour max
        enable_backpressure: bool = True,
        max_retries: int = 3,
        event_callback: Optional[Callable[[StreamEvent], Awaitable[None]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream events from Aletheia's events.ndjson endpoint as SSE.

        Args:
            task_id: The research task ID
            max_duration: Maximum stream duration in seconds
            enable_backpressure: Enable backpressure control
            max_retries: Maximum reconnection attempts

        Yields:
            SSE-formatted event strings
        """
        self._active_streams[task_id] = True
        start_time = time.time()
        retry_count = 0

        # Initialize buffer for backpressure control
        if enable_backpressure:
            self._stream_buffers[task_id] = asyncio.Queue(maxsize=self._buffer_size)

        try:
            logger.info(
                "Starting Aletheia event stream",
                task_id=task_id,
                backpressure=enable_backpressure,
                max_retries=max_retries,
            )

            while retry_count <= max_retries and self._active_streams.get(
                task_id, False
            ):
                try:
                    # Get Aletheia client
                    aletheia_client = await get_aletheia_client()

                    # Get the events stream URL from Aletheia
                    events_url = await aletheia_client.get_events_stream_url(task_id)

                    # Create HTTP session for streaming
                    timeout = aiohttp.ClientTimeout(total=None, sock_read=30)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        # Stream events from Aletheia with retry logic
                        async for event in self._stream_from_aletheia_with_retries(
                            session,
                            events_url,
                            task_id,
                            enable_backpressure,
                            event_callback,
                        ):
                            # Check if stream should stop
                            if not self._active_streams.get(task_id, False):
                                logger.info(
                                    "Stream stopped by request", task_id=task_id
                                )
                                return

                            # Check max duration
                            if time.time() - start_time > max_duration:
                                logger.info(
                                    "Stream reached max duration", task_id=task_id
                                )
                                return

                            yield event

                    # If we reach here, stream completed successfully
                    break

                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    retry_count += 1
                    if retry_count <= max_retries:
                        backoff_time = min(
                            2**retry_count, 30
                        )  # Exponential backoff, max 30s
                        logger.warning(
                            "Stream connection failed, retrying",
                            task_id=task_id,
                            retry=retry_count,
                            max_retries=max_retries,
                            backoff_time=backoff_time,
                            error=str(e),
                        )

                        # Send reconnection event
                        reconnect_event = StreamEvent(
                            event_type="stream_reconnecting",
                            task_id=task_id,
                            timestamp=datetime.utcnow(),
                            data={
                                "message": f"Connection lost, retrying in {backoff_time}s",
                                "retry_count": retry_count,
                                "max_retries": max_retries,
                            },
                        )
                        if event_callback:
                            try:
                                await event_callback(reconnect_event)
                            except Exception as callback_error:
                                logger.warning(
                                    "Stream callback failed",
                                    task_id=task_id,
                                    error=str(callback_error),
                                    event_type=reconnect_event.event_type,
                                )
                        yield self._format_sse_event(reconnect_event)

                        await asyncio.sleep(backoff_time)
                    else:
                        logger.error(
                            "Max retries exceeded", task_id=task_id, error=str(e)
                        )
                        raise

        except Exception as e:
            logger.error(
                "Error in Aletheia event stream", task_id=task_id, error=str(e)
            )
            # Send error event
            error_event = StreamEvent(
                event_type="stream_error",
                task_id=task_id,
                timestamp=datetime.utcnow(),
                data={"error": str(e), "error_type": "stream_error"},
            )
            if event_callback:
                try:
                    await event_callback(error_event)
                except Exception as callback_error:
                    logger.warning(
                        "Stream callback failed",
                        task_id=task_id,
                        error=str(callback_error),
                        event_type=error_event.event_type,
                    )
            yield self._format_sse_event(error_event)

        finally:
            self._active_streams.pop(task_id, None)
            self._stream_buffers.pop(task_id, None)  # Clean up buffer
            logger.info("Aletheia event stream closed", task_id=task_id)

    async def _stream_from_aletheia_with_retries(
        self,
        session: aiohttp.ClientSession,
        events_url: str,
        task_id: str,
        enable_backpressure: bool = True,
        event_callback: Optional[Callable[[StreamEvent], Awaitable[None]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream NDJSON events from Aletheia with backpressure control.
        """
        last_heartbeat = time.time()
        sequence = 0
        buffer = self._stream_buffers.get(task_id) if enable_backpressure else None

        try:
            async with session.get(events_url) as response:
                if response.status != 200:
                    raise Exception(
                        f"Failed to connect to Aletheia stream: {response.status}"
                    )

                logger.info(
                    "Connected to Aletheia events stream",
                    task_id=task_id,
                    url=events_url,
                    backpressure=enable_backpressure,
                )

                # Send initial connection event
                connection_event = StreamEvent(
                    event_type="stream_connected",
                    task_id=task_id,
                    timestamp=datetime.utcnow(),
                    data={"message": "Connected to research stream"},
                    sequence=sequence,
                )

                if event_callback:
                    try:
                        await event_callback(connection_event)
                    except Exception as callback_error:
                        logger.warning(
                            "Stream callback failed",
                            task_id=task_id,
                            error=str(callback_error),
                            event_type=connection_event.event_type,
                        )

                if buffer:
                    try:
                        buffer.put_nowait(self._format_sse_event(connection_event))
                    except asyncio.QueueFull:
                        logger.warning("Buffer full, dropping event", task_id=task_id)
                else:
                    yield self._format_sse_event(connection_event)

                sequence += 1

                # Start buffer consumer if using backpressure
                if buffer:
                    consumer_task = asyncio.create_task(
                        self._consume_buffer(buffer, task_id)
                    )

                # Read NDJSON lines from Aletheia
                async for line in response.content:
                    if not self._active_streams.get(task_id, False):
                        break

                    if line:
                        try:
                            # Parse NDJSON event
                            event_data = json.loads(line.decode("utf-8").strip())

                            # Convert to StreamEvent
                            stream_event = StreamEvent(
                                event_type=event_data.get("type", "progress"),
                                task_id=task_id,
                                timestamp=datetime.utcnow(),
                                data=event_data,
                                sequence=sequence,
                            )

                            if event_callback:
                                try:
                                    await event_callback(stream_event)
                                except Exception as callback_error:
                                    logger.warning(
                                        "Stream callback failed",
                                        task_id=task_id,
                                        error=str(callback_error),
                                        event_type=stream_event.event_type,
                                    )

                            formatted_event = self._format_sse_event(stream_event)

                            if buffer:
                                try:
                                    buffer.put_nowait(formatted_event)
                                except asyncio.QueueFull:
                                    # Drop oldest event and add new one
                                    try:
                                        buffer.get_nowait()
                                        buffer.put_nowait(formatted_event)
                                        logger.debug(
                                            "Buffer backpressure: dropped event",
                                            task_id=task_id,
                                        )
                                    except asyncio.QueueEmpty:
                                        pass
                            else:
                                yield formatted_event

                            sequence += 1
                            last_heartbeat = time.time()

                        except (json.JSONDecodeError, ValueError) as e:
                            logger.warning(
                                "Failed to parse Aletheia event",
                                error=str(e),
                                line=line,
                            )
                            continue

                    # Send heartbeat if no events for 30 seconds
                    if time.time() - last_heartbeat > 30:
                        heartbeat_event = StreamEvent(
                            event_type="heartbeat",
                            task_id=task_id,
                            timestamp=datetime.utcnow(),
                            data={
                                "message": "Stream alive",
                                "buffer_size": buffer.qsize() if buffer else 0,
                            },
                            sequence=sequence,
                        )

                        if event_callback:
                            try:
                                await event_callback(heartbeat_event)
                            except Exception as callback_error:
                                logger.warning(
                                    "Stream callback failed",
                                    task_id=task_id,
                                    error=str(callback_error),
                                    event_type=heartbeat_event.event_type,
                                )

                        formatted_heartbeat = self._format_sse_event(heartbeat_event)

                        if buffer:
                            try:
                                buffer.put_nowait(formatted_heartbeat)
                            except asyncio.QueueFull:
                                pass  # Skip heartbeat if buffer is full
                        else:
                            yield formatted_heartbeat

                        sequence += 1
                        last_heartbeat = time.time()

                    # Adaptive delay based on buffer size
                    if buffer:
                        buffer_size = buffer.qsize()
                        delay = min(0.01 * buffer_size, 0.5)  # Max 500ms delay
                        if delay > 0.1:
                            logger.debug(
                                "Adaptive delay for backpressure",
                                task_id=task_id,
                                delay=delay,
                            )
                    else:
                        delay = 0.1

                    await asyncio.sleep(delay)

                # Consume remaining buffer events
                if buffer:
                    while not buffer.empty():
                        try:
                            event = buffer.get_nowait()
                            yield event
                        except asyncio.QueueEmpty:
                            break

                    consumer_task.cancel()

        except aiohttp.ClientError as e:
            logger.error(
                "HTTP error streaming from Aletheia", task_id=task_id, error=str(e)
            )
            raise Exception(f"Connection to Aletheia failed: {str(e)}")

    async def _consume_buffer(self, buffer: asyncio.Queue, task_id: str):
        """
        Consumer task for backpressure buffer.
        """
        try:
            while self._active_streams.get(task_id, False):
                try:
                    # Wait for events in buffer with timeout
                    event = await asyncio.wait_for(buffer.get(), timeout=1.0)
                    yield event
                except asyncio.TimeoutError:
                    continue  # No events available, check if stream is still active
                except asyncio.CancelledError:
                    break
        except Exception as e:
            logger.error("Error in buffer consumer", task_id=task_id, error=str(e))

    def _format_sse_event(self, event: StreamEvent) -> str:
        """
        Format StreamEvent as SSE event string.
        """
        event_json = event.model_dump_json()
        return f"data: {event_json}\n\n"

    async def stop_stream(self, task_id: str):
        """Stop an active event stream."""
        if task_id in self._active_streams:
            self._active_streams[task_id] = False
            logger.info("Requested stream stop", task_id=task_id)

    async def create_mock_stream(
        self,
        task_id: str,
        duration: int = 180,
        event_callback: Optional[Callable[[StreamEvent], Awaitable[None]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Create a mock event stream for testing when Aletheia is unavailable.
        """
        self._active_streams[task_id] = True
        start_time = time.time()
        sequence = 0

        try:
            logger.info("Starting mock event stream", task_id=task_id)

            # Mock research phases
            phases = [
                {
                    "phase": "initialization",
                    "progress": 0.0,
                    "message": "Initializing research task",
                },
                {
                    "phase": "search",
                    "progress": 0.1,
                    "message": "Searching for relevant sources",
                },
                {
                    "phase": "analysis",
                    "progress": 0.3,
                    "message": "Analyzing source content",
                },
                {
                    "phase": "evidence",
                    "progress": 0.5,
                    "message": "Extracting evidence and key findings",
                },
                {
                    "phase": "synthesis",
                    "progress": 0.7,
                    "message": "Synthesizing research results",
                },
                {
                    "phase": "citation",
                    "progress": 0.9,
                    "message": "Generating citations and references",
                },
                {
                    "phase": "completion",
                    "progress": 1.0,
                    "message": "Research completed successfully",
                },
            ]

            for phase in phases:
                if not self._active_streams.get(task_id, False):
                    break

                # Send phase update
                phase_event = StreamEvent(
                    event_type="progress_update",
                    task_id=task_id,
                    timestamp=datetime.utcnow(),
                    data={
                        "phase": phase["phase"],
                        "progress": phase["progress"],
                        "message": phase["message"],
                        "step": sequence + 1,
                        "total_steps": len(phases),
                    },
                    sequence=sequence,
                )

                if event_callback:
                    try:
                        await event_callback(phase_event)
                    except Exception as callback_error:
                        logger.warning(
                            "Stream callback failed",
                            task_id=task_id,
                            error=str(callback_error),
                            event_type=phase_event.event_type,
                        )

                yield self._format_sse_event(phase_event)
                sequence += 1

                # Wait between phases
                await asyncio.sleep(duration / len(phases))

            # Send completion event
            completion_event = StreamEvent(
                event_type="task_completed",
                task_id=task_id,
                timestamp=datetime.utcnow(),
                data={
                    "status": "completed",
                    "message": "Research task completed successfully",
                    "results_available": True,
                    "total_time": time.time() - start_time,
                },
                sequence=sequence,
            )

            if event_callback:
                try:
                    await event_callback(completion_event)
                except Exception as callback_error:
                    logger.warning(
                        "Stream callback failed",
                        task_id=task_id,
                        error=str(callback_error),
                        event_type=completion_event.event_type,
                    )

            yield self._format_sse_event(completion_event)

        except Exception as e:
            logger.error("Error in mock stream", task_id=task_id, error=str(e))
            error_event = StreamEvent(
                event_type="stream_error",
                task_id=task_id,
                timestamp=datetime.utcnow(),
                data={"error": str(e), "error_type": "mock_stream_error"},
            )
            if event_callback:
                try:
                    await event_callback(error_event)
                except Exception as callback_error:
                    logger.warning(
                        "Stream callback failed",
                        task_id=task_id,
                        error=str(callback_error),
                        event_type=error_event.event_type,
                    )
            yield self._format_sse_event(error_event)

        finally:
            self._active_streams.pop(task_id, None)
            logger.info("Mock event stream completed", task_id=task_id)

    async def get_stream_status(self, task_id: str) -> Dict[str, Any]:
        """Get the status of an active stream."""
        is_active = self._active_streams.get(task_id, False)

        return {
            "task_id": task_id,
            "stream_active": is_active,
            "timestamp": datetime.utcnow().isoformat(),
        }


# Singleton instance
_event_streamer: Optional[AletheiaEventStreamer] = None


def get_event_streamer() -> AletheiaEventStreamer:
    """Get singleton event streamer instance."""
    global _event_streamer
    if _event_streamer is None:
        _event_streamer = AletheiaEventStreamer()
    return _event_streamer
