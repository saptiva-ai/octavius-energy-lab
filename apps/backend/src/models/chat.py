"""
Chat document models
"""

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional
from uuid import uuid4

from beanie import Document, Indexed, Link
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from ..core.config import default_chat_model
from .document_state import DocumentState, ProcessingStatus
from .user import User


class MessageRole(str, Enum):
    """Message role enumeration"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageStatus(str, Enum):
    """Message status enumeration"""

    SENDING = "sending"
    DELIVERED = "delivered"
    ERROR = "error"
    STREAMING = "streaming"


class FileMetadata(BaseModel):
    """
    Explicit file metadata model for message attachments.

    Replaces Dict[str, Any] to ensure type safety and BSON compatibility.
    """

    file_id: str = Field(..., description="Document/file ID")
    filename: str = Field(..., description="Original filename")
    bytes: int = Field(..., description="File size in bytes")
    pages: Optional[int] = Field(None, description="Number of pages (for PDFs)")
    mimetype: Optional[str] = Field(None, description="MIME type")

    # Pydantic V2: Replace class Config with model_config
    model_config = ConfigDict(
        # Ensure compatibility with MongoDB ObjectId serialization
        json_encoders={str: str}  # Keep file_id as string for flexibility
    )


class ConversationState(str, Enum):
    """P0-BE-UNIQ-EMPTY: Conversation state enumeration

    State lifecycle:
    - DRAFT: Empty conversation (0 messages), unique per user
    - ACTIVE: Has messages, normal conversation state
    - CREATING: Being created (transient state)
    - ERROR: Creation failed
    """

    DRAFT = "draft"  # Empty conversation, no messages yet (unique per user)
    ACTIVE = "active"  # Has at least one message, normal conversation
    CREATING = "creating"  # Being created (transient state)
    ERROR = "error"  # Creation failed


class ChatMessage(Document):
    """Chat message document model"""

    id: str = Field(default_factory=lambda: str(uuid4()), alias="_id")
    chat_id: Indexed(str) = Field(..., description="Chat session ID")
    role: MessageRole = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    status: MessageStatus = Field(
        default=MessageStatus.DELIVERED, description="Message status"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    # File attachments (explicit typed model)
    file_ids: List[str] = Field(
        default_factory=list, description="File/document IDs attached to this message"
    )
    files: List[FileMetadata] = Field(
        default_factory=list, description="Explicit file metadata for UI display"
    )

    # Schema version for migrations
    schema_version: int = Field(
        default=2, description="Schema version (2 = explicit files field)"
    )

    # Legacy metadata (for backwards compatibility, will be deprecated)
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Legacy metadata (use files field instead)"
    )

    # Model metadata
    model: Optional[str] = Field(None, description="Model used for generation")
    tokens: Optional[int] = Field(None, description="Token count")
    latency_ms: Optional[int] = Field(None, description="Response latency")
    task_id: Optional[str] = Field(None, description="Associated task ID")

    class Settings:
        name = "messages"
        indexes = [
            "chat_id",
            "created_at",
            "role",
            "status",
            [("chat_id", 1), ("created_at", 1)],  # Compound index for chat history
        ]

    def __str__(self) -> str:
        return f"ChatMessage(id={self.id}, role={self.role}, chat_id={self.chat_id})"


class ChatSettings(BaseModel):
    """Chat settings subdocument"""

    model: str = Field(default_factory=default_chat_model, description="Selected model")
    temperature: float = Field(
        default=0.7, ge=0.0, le=2.0, description="Temperature setting"
    )
    max_tokens: int = Field(default=1024, ge=1, le=8192, description="Max tokens")
    tools_enabled: Dict[str, bool] = Field(
        default_factory=lambda: {"web_search": False, "deep_research": False},
        description="Enabled tools",
    )
    research_params: Optional[Dict[str, Any]] = Field(
        None, description="Research parameters"
    )


class CanvasState(BaseModel):
    """Canvas state subdocument for persistence"""

    is_sidebar_open: bool = Field(
        default=False, description="Whether canvas sidebar is open"
    )
    active_artifact_id: Optional[str] = Field(
        None, description="Currently active artifact ID"
    )
    active_message_id: Optional[str] = Field(
        None, description="Currently active message ID"
    )
    active_chart: Optional[Dict[str, Any]] = Field(
        None, description="Active chart artifact data"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last canvas update"
    )


class ChatSession(Document):
    """Chat session document model"""

    id: str = Field(default_factory=lambda: str(uuid4()), alias="_id")
    title: str = Field(..., max_length=200, description="Chat session title")
    title_override: bool = Field(
        default=False, description="Whether title was manually set by user"
    )
    user_id: Indexed(str) = Field(..., description="User ID")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    # Progressive Commitment: Message timestamps
    first_message_at: Optional[datetime] = Field(
        None, description="Timestamp of first user message"
    )
    last_message_at: Optional[datetime] = Field(
        None, description="Timestamp of last message"
    )

    message_count: int = Field(default=0, description="Number of messages")
    settings: ChatSettings = Field(
        default_factory=ChatSettings, description="Chat settings"
    )
    pinned: bool = Field(default=False, description="Whether the chat is pinned")
    tools_enabled: Dict[str, bool] = Field(
        default_factory=dict, description="Enabled tools for this chat"
    )

    # Simple Memory System: JSON-based fact recall
    memory_facts: Dict[str, str] = Field(
        default_factory=dict,
        description="Extracted facts as JSON. Key format: bank.period.metric",
    )
    memory_context: Dict[str, str] = Field(
        default_factory=dict,
        description="Current conversation context: bank, period, metric",
    )

    # Canvas state persistence
    canvas_state: Optional[CanvasState] = Field(
        None, description="Canvas sidebar state for this conversation"
    )

    # MVP-FILE-CONTEXT: Structured document states for this conversation
    documents: List[DocumentState] = Field(
        default_factory=list,
        description="Documents with processing state attached to this conversation",
    )

    # DEPRECATED: Legacy field for backward compatibility (remove in v2.0)
    attached_file_ids: List[str] = Field(
        default_factory=list,
        description="DEPRECATED: Use 'documents' field instead. Kept for migration.",
    )

    # P0-BE-UNIQ-EMPTY: State to track conversation lifecycle
    state: ConversationState = Field(
        default=ConversationState.DRAFT, description="Conversation state"
    )

    # P0-CHAT-IDEMPOTENCY: Store creation idempotency key (if provided by client)
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Idempotency key used during creation (ensures single-flight)",
    )

    # Optional user reference (for relational queries)
    user: Optional[Link[User]] = Field(None, description="User reference")

    # P0-STATE-MACHINE: Valid state transitions (ClassVar to avoid Pydantic field detection)
    VALID_TRANSITIONS: ClassVar[Dict[ConversationState, List[ConversationState]]] = {
        ConversationState.CREATING: [ConversationState.DRAFT, ConversationState.ERROR],
        ConversationState.DRAFT: [ConversationState.ACTIVE, ConversationState.ERROR],
        ConversationState.ACTIVE: [],  # Terminal state
        ConversationState.ERROR: [ConversationState.DRAFT],  # Allow retry
    }

    class Settings:
        name = "chat_sessions"
        indexes = [
            "user_id",
            "created_at",
            "updated_at",
            "title",
            "state",
            "idempotency_key",
            [("user_id", 1), ("updated_at", -1)],  # User's recent chats
            [("user_id", 1), ("state", 1)],  # Find user's drafts
            # P0-BE-UNIQ-EMPTY: Partial unique index - only one DRAFT per user
            # Note: Index is created manually via MongoDB (see scripts/apply-draft-unique-index.py)
            # Beanie doesn't support partialFilterExpression in Settings.indexes
            # {
            #     "keys": [("user_id", 1), ("state", 1)],
            #     "unique": True,
            #     "partialFilterExpression": {"state": "draft"},
            #     "name": "unique_draft_per_user"
            # }
            IndexModel(
                [("updated_at", ASCENDING)],
                expireAfterSeconds=3600,
                partialFilterExpression={"state": "draft", "message_count": 0},
                name="ttl_cleanup_drafts",
            ),
        ]

    def __str__(self) -> str:
        return f"ChatSession(id={self.id}, title={self.title}, user_id={self.user_id})"

    async def get_messages(self, limit: int = 50, skip: int = 0) -> List[ChatMessage]:
        """Get messages for this chat session"""
        return (
            await ChatMessage.find(ChatMessage.chat_id == self.id)
            .sort(-ChatMessage.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def add_message(
        self, role: MessageRole, content: str, **kwargs
    ) -> ChatMessage:
        """Add a new message to this chat session"""
        message = ChatMessage(chat_id=self.id, role=role, content=content, **kwargs)
        await message.insert()

        # Update session stats
        self.message_count += 1
        self.updated_at = datetime.utcnow()
        now = datetime.utcnow()

        # Progressive Commitment: Set timestamps
        if self.message_count == 1:
            # First message: set first_message_at
            self.first_message_at = now
        # Always update last_message_at
        self.last_message_at = now

        # P0-BE-UNIQ-EMPTY: Transition from DRAFT to ACTIVE on first message
        if self.message_count == 1 and self.state == ConversationState.DRAFT:
            await self.transition_state(
                ConversationState.ACTIVE, reason="first_message_received"
            )
        else:
            await self.save()

        # Invalidate cache for this chat
        try:
            from ..core.redis_cache import get_redis_cache

            cache = await get_redis_cache()
            await cache.invalidate_all_for_chat(self.id)
        except Exception as e:
            # Don't fail if cache invalidation fails
            import structlog

            logger = structlog.get_logger(__name__)
            logger.warning("Failed to invalidate cache", error=str(e), chat_id=self.id)

        # Record in unified history
        try:
            from ..services.history_service import HistoryService

            await HistoryService.record_chat_message(
                chat_id=self.id, user_id=self.user_id, message=message
            )
        except Exception as e:
            # Don't fail message creation if history fails
            import structlog

            logger = structlog.get_logger(__name__)
            logger.warning(
                "Failed to record message in unified history",
                error=str(e),
                chat_id=self.id,
                message_id=message.id,
            )

        return message

    async def transition_state(self, new_state: ConversationState, reason: str = None):
        """
        Safely transition conversation state with validation.

        P0-STATE-MACHINE: Implements state machine with explicit valid transitions.
        Logs all transitions for debugging and monitoring.

        Args:
            new_state: Target state to transition to
            reason: Human-readable reason for the transition (for logging)

        Raises:
            ValueError: If the transition is not valid according to VALID_TRANSITIONS

        Example:
            >>> await session.transition_state(ConversationState.ACTIVE, "first_message_received")
        """
        import structlog

        logger = structlog.get_logger(__name__)

        current = self.state or ConversationState.ACTIVE  # Handle None for legacy

        # Same state is always valid (no-op)
        if current == new_state:
            logger.debug(
                "State transition skipped (same state)",
                chat_id=self.id,
                state=current.value,
                reason=reason or "not_specified",
            )
            return

        # Check if transition is valid
        valid_next = self.VALID_TRANSITIONS.get(current, [])
        if new_state not in valid_next:
            error_msg = f"Invalid state transition: {current.value} → {new_state.value}"
            logger.error(
                "Invalid state transition attempted",
                chat_id=self.id,
                user_id=self.user_id,
                from_state=current.value,
                to_state=new_state.value,
                reason=reason or "not_specified",
                message_count=self.message_count,
                error=error_msg,
            )
            raise ValueError(error_msg)

        # Perform transition
        logger.info(
            "State transition",
            chat_id=self.id,
            user_id=self.user_id,
            from_state=current.value,
            to_state=new_state.value,
            reason=reason or "not_specified",
            message_count=self.message_count,
        )

        self.state = new_state
        self.updated_at = datetime.utcnow()
        await self.save()

    # Document management helper methods
    def add_document(self, doc_id: str, name: str, **kwargs) -> DocumentState:
        """
        Add a new document to the conversation.

        Args:
            doc_id: Document ID
            name: Original filename
            **kwargs: Additional metadata (pages, size_bytes, mimetype, etc.)

        Returns:
            The created DocumentState

        Example:
            >>> session = ChatSession(...)
            >>> doc = session.add_document(
            ...     doc_id="doc-123",
            ...     name="report.pdf",
            ...     pages=32,
            ...     size_bytes=1024000
            ... )
        """
        doc_state = DocumentState(doc_id=doc_id, name=name, **kwargs)
        self.documents.append(doc_state)

        # Keep legacy field in sync during migration
        if doc_id not in self.attached_file_ids:
            self.attached_file_ids.append(doc_id)

        return doc_state

    def get_document(self, doc_id: str) -> Optional[DocumentState]:
        """
        Get document state by ID.

        Args:
            doc_id: Document ID to search for

        Returns:
            DocumentState if found, None otherwise
        """
        return next((d for d in self.documents if d.doc_id == doc_id), None)

    def get_ready_documents(self) -> List[DocumentState]:
        """
        Get all documents ready for RAG.

        Returns:
            List of documents with status=READY
        """
        return [d for d in self.documents if d.is_ready()]

    def get_processing_documents(self) -> List[DocumentState]:
        """
        Get all documents currently being processed.

        Returns:
            List of documents in processing states
        """
        return [d for d in self.documents if d.is_processing()]

    def update_document_status(
        self, doc_id: str, status: ProcessingStatus, **kwargs
    ) -> Optional[DocumentState]:
        """
        Update document processing status.

        Args:
            doc_id: Document ID
            status: New processing status
            **kwargs: Additional fields to update (error, segments_count, etc.)

        Returns:
            Updated DocumentState if found, None otherwise

        Example:
            >>> session.update_document_status(
            ...     "doc-123",
            ...     ProcessingStatus.READY,
            ...     segments_count=15
            ... )
        """
        doc = self.get_document(doc_id)
        if doc:
            doc.status = status
            doc.updated_at = datetime.utcnow()

            for key, value in kwargs.items():
                if hasattr(doc, key):
                    setattr(doc, key, value)

        return doc
