"""
Unified history models for chat + research timeline
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from beanie import Document, Indexed
from beanie.operators import In
from pydantic import BaseModel, Field


class HistoryEventType(str, Enum):
    """History event type enumeration"""

    CHAT_MESSAGE = "chat_message"
    RESEARCH_STARTED = "research_started"
    RESEARCH_PROGRESS = "research_progress"
    RESEARCH_COMPLETED = "research_completed"
    RESEARCH_FAILED = "research_failed"
    SOURCE_FOUND = "source_found"
    EVIDENCE_DISCOVERED = "evidence_discovered"


class HistoryEventStatus(str, Enum):
    """History event status enumeration"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatEventData(BaseModel):
    """Chat message event data"""

    role: str
    content: str
    model: Optional[str] = None
    tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    # File attachments (explicit typed fields)
    file_ids: Optional[List[str]] = Field(
        default_factory=list, description="File/document IDs attached to this message"
    )
    files: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list, description="File metadata for UI display"
    )
    schema_version: Optional[int] = Field(
        default=1, description="Message schema version"
    )
    # Legacy metadata for backwards compatibility
    metadata: Optional[Dict[str, Any]] = Field(None, description="Legacy metadata")


class ResearchEventData(BaseModel):
    """Research event data"""

    task_id: str
    query: Optional[str] = None
    progress: Optional[float] = None
    current_step: Optional[str] = None
    sources_found: Optional[int] = None
    iterations_completed: Optional[int] = None
    error_message: Optional[str] = None


class SourceEventData(BaseModel):
    """Source discovery event data"""

    source_id: str
    url: str
    title: str
    relevance_score: float
    credibility_score: float


class EvidenceEventData(BaseModel):
    """Evidence discovery event data"""

    evidence_id: str
    claim: str
    support_level: str
    confidence: float


class HistoryEvent(Document):
    """Unified history event document"""

    id: str = Field(default_factory=lambda: str(uuid4()), alias="_id")
    chat_id: Indexed(str) = Field(..., description="Chat session ID")
    user_id: Indexed(str) = Field(..., description="User ID")

    event_type: HistoryEventType = Field(..., description="Event type")
    status: HistoryEventStatus = Field(
        default=HistoryEventStatus.COMPLETED, description="Event status"
    )

    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )
    sequence_order: int = Field(..., description="Sequence order within chat")

    # Reference IDs
    message_id: Optional[str] = Field(None, description="Associated message ID")
    task_id: Optional[str] = Field(None, description="Associated task ID")
    source_id: Optional[str] = Field(None, description="Associated source ID")
    evidence_id: Optional[str] = Field(None, description="Associated evidence ID")

    # Event-specific data
    chat_data: Optional[ChatEventData] = Field(None, description="Chat event data")
    research_data: Optional[ResearchEventData] = Field(
        None, description="Research event data"
    )
    source_data: Optional[SourceEventData] = Field(
        None, description="Source event data"
    )
    evidence_data: Optional[EvidenceEventData] = Field(
        None, description="Evidence event data"
    )

    # Additional metadata
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    class Settings:
        name = "history_events"
        indexes = [
            "chat_id",
            "user_id",
            "event_type",
            "timestamp",
            "sequence_order",
            "task_id",
            [("chat_id", 1), ("sequence_order", 1)],  # Chat timeline
            [("chat_id", 1), ("timestamp", 1)],  # Chat chronological
            [("user_id", 1), ("timestamp", -1)],  # User recent events
        ]

    def __str__(self) -> str:
        return f"HistoryEvent(id={self.id}, type={self.event_type}, chat_id={self.chat_id})"


class HistoryEventFactory:
    """Factory for creating history events"""

    @staticmethod
    async def create_chat_message_event(
        chat_id: str,
        user_id: str,
        message_id: str,
        role: str,
        content: str,
        model: Optional[str] = None,
        tokens: Optional[int] = None,
        latency_ms: Optional[int] = None,
        **kwargs,
    ) -> HistoryEvent:
        """Create a chat message event"""

        # Get next sequence order
        sequence_order = await HistoryEventFactory._get_next_sequence(chat_id)

        # Extract file fields from kwargs for chat_data
        file_ids = kwargs.pop("file_ids", [])
        files = kwargs.pop("files", [])
        schema_version = kwargs.pop("schema_version", 1)
        message_metadata = kwargs.pop("message_metadata", None)

        event = HistoryEvent(
            chat_id=chat_id,
            user_id=user_id,
            event_type=HistoryEventType.CHAT_MESSAGE,
            message_id=message_id,
            sequence_order=sequence_order,
            chat_data=ChatEventData(
                role=role,
                content=content,
                model=model,
                tokens=tokens,
                latency_ms=latency_ms,
                file_ids=file_ids,
                files=files,
                schema_version=schema_version,
                metadata=message_metadata,
            ),
            metadata=kwargs,  # Remaining kwargs go to event metadata
        )

        await event.insert()
        return event

    @staticmethod
    async def create_research_started_event(
        chat_id: str, user_id: str, task_id: str, query: str, **kwargs
    ) -> HistoryEvent:
        """Create a research started event"""

        sequence_order = await HistoryEventFactory._get_next_sequence(chat_id)

        event = HistoryEvent(
            chat_id=chat_id,
            user_id=user_id,
            event_type=HistoryEventType.RESEARCH_STARTED,
            task_id=task_id,
            sequence_order=sequence_order,
            status=HistoryEventStatus.PROCESSING,
            research_data=ResearchEventData(task_id=task_id, query=query, progress=0.0),
            metadata=kwargs,
        )

        await event.insert()
        return event

    @staticmethod
    async def create_research_progress_event(
        chat_id: str,
        user_id: str,
        task_id: str,
        progress: float,
        current_step: str,
        sources_found: Optional[int] = None,
        iterations_completed: Optional[int] = None,
        **kwargs,
    ) -> HistoryEvent:
        """Create a research progress event"""

        sequence_order = await HistoryEventFactory._get_next_sequence(chat_id)

        event = HistoryEvent(
            chat_id=chat_id,
            user_id=user_id,
            event_type=HistoryEventType.RESEARCH_PROGRESS,
            task_id=task_id,
            sequence_order=sequence_order,
            status=HistoryEventStatus.PROCESSING,
            research_data=ResearchEventData(
                task_id=task_id,
                progress=progress,
                current_step=current_step,
                sources_found=sources_found,
                iterations_completed=iterations_completed,
            ),
            metadata=kwargs,
        )

        await event.insert()
        return event

    @staticmethod
    async def create_research_completed_event(
        chat_id: str,
        user_id: str,
        task_id: str,
        sources_found: int,
        iterations_completed: int,
        **kwargs,
    ) -> HistoryEvent:
        """Create a research completed event"""

        sequence_order = await HistoryEventFactory._get_next_sequence(chat_id)

        event = HistoryEvent(
            chat_id=chat_id,
            user_id=user_id,
            event_type=HistoryEventType.RESEARCH_COMPLETED,
            task_id=task_id,
            sequence_order=sequence_order,
            status=HistoryEventStatus.COMPLETED,
            research_data=ResearchEventData(
                task_id=task_id,
                progress=100.0,
                sources_found=sources_found,
                iterations_completed=iterations_completed,
            ),
            metadata=kwargs,
        )

        await event.insert()
        return event

    @staticmethod
    async def create_research_failed_event(
        chat_id: str,
        user_id: str,
        task_id: str,
        error_message: str,
        progress: Optional[float] = None,
        current_step: Optional[str] = None,
        **kwargs,
    ) -> HistoryEvent:
        """Create a research failed event"""

        sequence_order = await HistoryEventFactory._get_next_sequence(chat_id)

        event = HistoryEvent(
            chat_id=chat_id,
            user_id=user_id,
            event_type=HistoryEventType.RESEARCH_FAILED,
            task_id=task_id,
            sequence_order=sequence_order,
            status=HistoryEventStatus.FAILED,
            research_data=ResearchEventData(
                task_id=task_id,
                progress=progress,
                current_step=current_step,
                error_message=error_message,
            ),
            metadata=kwargs,
        )

        await event.insert()
        return event

    @staticmethod
    async def create_source_found_event(
        chat_id: str,
        user_id: str,
        task_id: str,
        source_id: str,
        url: str,
        title: str,
        relevance_score: float,
        credibility_score: float,
        **kwargs,
    ) -> HistoryEvent:
        """Create a source found event"""

        sequence_order = await HistoryEventFactory._get_next_sequence(chat_id)

        event = HistoryEvent(
            chat_id=chat_id,
            user_id=user_id,
            event_type=HistoryEventType.SOURCE_FOUND,
            task_id=task_id,
            source_id=source_id,
            sequence_order=sequence_order,
            source_data=SourceEventData(
                source_id=source_id,
                url=url,
                title=title,
                relevance_score=relevance_score,
                credibility_score=credibility_score,
            ),
            metadata=kwargs,
        )

        await event.insert()
        return event

    @staticmethod
    async def _get_next_sequence(chat_id: str) -> int:
        """Get the next sequence number for a chat"""
        last_event = (
            await HistoryEvent.find(HistoryEvent.chat_id == chat_id)
            .sort(-HistoryEvent.sequence_order)
            .first_or_none()
        )

        return (last_event.sequence_order + 1) if last_event else 1


class HistoryQuery:
    """Helper class for querying history"""

    @staticmethod
    async def get_chat_timeline(
        chat_id: str,
        limit: int = 50,
        offset: int = 0,
        event_types: Optional[List[HistoryEventType]] = None,
    ) -> List[HistoryEvent]:
        """Get timeline events for a chat"""

        query = HistoryEvent.find(HistoryEvent.chat_id == chat_id)

        if event_types:
            query = query.find(In(HistoryEvent.event_type, event_types))

        return (
            await query.sort(HistoryEvent.sequence_order)
            .skip(offset)
            .limit(limit)
            .to_list()
        )

    @staticmethod
    async def get_chat_timeline_count(
        chat_id: str, event_types: Optional[List[HistoryEventType]] = None
    ) -> int:
        """Get count of timeline events for a chat"""

        query = HistoryEvent.find(HistoryEvent.chat_id == chat_id)

        if event_types:
            query = query.find(In(HistoryEvent.event_type, event_types))

        return await query.count()

    @staticmethod
    async def get_research_events_for_task(task_id: str) -> List[HistoryEvent]:
        """Get all research events for a specific task"""

        return (
            await HistoryEvent.find(HistoryEvent.task_id == task_id)
            .sort(HistoryEvent.sequence_order)
            .to_list()
        )

    @staticmethod
    async def get_latest_research_event(
        chat_id: str, task_id: str
    ) -> Optional[HistoryEvent]:
        """Get the latest research event for a task in a chat"""

        return (
            await HistoryEvent.find(
                HistoryEvent.chat_id == chat_id,
                HistoryEvent.task_id == task_id,
                In(
                    HistoryEvent.event_type,
                    [
                        HistoryEventType.RESEARCH_STARTED,
                        HistoryEventType.RESEARCH_PROGRESS,
                        HistoryEventType.RESEARCH_COMPLETED,
                        HistoryEventType.RESEARCH_FAILED,
                    ],
                ),
            )
            .sort(-HistoryEvent.sequence_order)
            .first_or_none()
        )
