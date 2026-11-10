"""
Chat API schemas
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Import FileMetadata from models for type-safe file attachments
from ..core.config import default_chat_model
from ..models.chat import FileMetadata


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


class ChatMessage(BaseModel):
    """Chat message schema"""

    id: Optional[str] = Field(None, description="Message ID")
    chat_id: str = Field(..., description="Chat session ID")
    role: MessageRole = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    status: MessageStatus = Field(
        default=MessageStatus.DELIVERED, description="Message status"
    )
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    # File attachments (explicit typed fields)
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

    # Legacy metadata (backwards compatibility)
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Legacy metadata (use files field instead)"
    )

    # Model metadata
    model: Optional[str] = Field(None, description="Model used for generation")
    tokens: Optional[int] = Field(None, description="Token count")
    latency_ms: Optional[int] = Field(None, description="Response latency")
    task_id: Optional[str] = Field(None, description="Associated task ID")


class ChatSettings(BaseModel):
    """Chat settings schema"""

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


class ChatSession(BaseModel):
    """Chat session schema"""

    id: Optional[str] = Field(None, description="Chat session ID")
    title: str = Field(..., max_length=200, description="Chat session title")
    user_id: str = Field(..., description="User ID")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

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
        default_factory=dict, description="Enabled tools for the chat"
    )
    state: Optional[ConversationState] = Field(
        ConversationState.ACTIVE, description="P0-BE-UNIQ-EMPTY: Conversation state"
    )
    idempotency_key: Optional[str] = Field(
        default=None, description="Idempotency key used during session creation"
    )

    @field_validator("state", mode="before")
    @classmethod
    def default_state_if_none(cls, v):
        """
        Handle legacy conversations without state field.

        Legacy conversations (created before state management) have state=None.
        These are treated as ACTIVE since they have messages.
        """
        if v is None:
            return ConversationState.ACTIVE.value
        return v


class ChatRequest(BaseModel):
    """Chat request schema"""

    message: str = Field(
        ..., min_length=1, max_length=10000, description="User message"
    )
    chat_id: Optional[str] = Field(None, description="Existing chat session ID")
    model: Optional[str] = Field(None, description="Model to use for response")
    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description="Temperature setting"
    )
    max_tokens: Optional[int] = Field(None, ge=1, le=8192, description="Max tokens")
    stream: bool = Field(default=True, description="Enable streaming response")
    tools_enabled: Dict[str, bool] = Field(
        default_factory=dict, description="Tools to enable"
    )
    enabled_tools: Optional[Dict[str, bool]] = Field(
        default=None, alias="enabled_tools"
    )
    context: Optional[Dict[str, Any]] = Field(
        None, description="Additional context (dict)"
    )
    document_ids: Optional[List[str]] = Field(
        None, description="Document IDs to attach for RAG context (legacy)"
    )
    file_ids: Optional[List[str]] = Field(
        None, description="File IDs to attach for RAG context (Files V1)"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata for the user message (e.g., file info for UI indicators)",
    )
    channel: str = Field(
        default="chat", description="Communication channel (chat, report, title, etc.)"
    )

    @model_validator(mode="before")
    @classmethod
    def ensure_tools_enabled(cls, values):
        if isinstance(values, dict):
            if "tools_enabled" not in values or values["tools_enabled"] is None:
                alias_value = values.get("enabled_tools")
                values["tools_enabled"] = alias_value or {}
        return values

    @field_validator("message")
    @classmethod
    def validate_message_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v):
        """Validar que el canal sea uno de los permitidos"""
        allowed_channels = {"chat", "report", "title", "summary", "code"}
        if v not in allowed_channels:
            raise ValueError(f"Channel must be one of: {', '.join(allowed_channels)}")
        return v


class ChatResponse(BaseModel):
    """Chat response schema"""

    chat_id: str = Field(..., description="Chat session ID")
    message_id: str = Field(..., description="Response message ID")
    content: str = Field(..., description="Response content")
    artifact: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional structured artifact (e.g., audit_report_response) for UI rendering",
    )
    role: MessageRole = Field(default=MessageRole.ASSISTANT, description="Message role")
    model: str = Field(..., description="Model used for response")
    created_at: datetime = Field(..., description="Creation timestamp")

    # Response metadata
    tokens: Optional[int] = Field(None, description="Token count")
    latency_ms: Optional[int] = Field(None, description="Response latency")
    finish_reason: Optional[str] = Field(None, description="Completion reason")

    # Tool usage
    tools_used: Optional[List[str]] = Field(None, description="Tools used in response")
    task_id: Optional[str] = Field(
        None, description="Associated task ID for deep research"
    )
    tools_enabled: Dict[str, bool] = Field(
        default_factory=dict, description="Enabled tools for this response"
    )


class ChatHistoryRequest(BaseModel):
    """Chat history request schema"""

    chat_id: str = Field(..., description="Chat session ID")
    limit: int = Field(
        default=50, ge=1, le=100, description="Number of messages to retrieve"
    )
    offset: int = Field(default=0, ge=0, description="Number of messages to skip")
    include_system: bool = Field(default=False, description="Include system messages")


class ChatHistoryResponse(BaseModel):
    """Chat history response schema"""

    chat_id: str = Field(..., description="Chat session ID")
    messages: List[ChatMessage] = Field(..., description="Chat messages")
    total_count: int = Field(..., description="Total number of messages")
    has_more: bool = Field(..., description="Whether there are more messages")


class ChatSessionListResponse(BaseModel):
    """Chat session list response schema"""

    sessions: List[ChatSession] = Field(..., description="Chat sessions")
    total_count: int = Field(..., description="Total number of sessions")
    has_more: bool = Field(..., description="Whether there are more sessions")


class ChatSessionUpdateRequest(BaseModel):
    """Chat session update request schema"""

    title: Optional[str] = Field(
        None, max_length=200, description="New chat session title"
    )
    pinned: Optional[bool] = Field(None, description="Pin/unpin the chat session")
    tools_enabled: Optional[Dict[str, bool]] = Field(
        None, description="Updated tool configuration"
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        if v is not None and not v.strip():
            raise ValueError("Title cannot be empty or whitespace only")
        return v.strip() if v else None


class CanvasStateUpdateRequest(BaseModel):
    """Canvas state update request schema"""

    is_sidebar_open: Optional[bool] = Field(
        None, description="Whether canvas sidebar is open"
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
