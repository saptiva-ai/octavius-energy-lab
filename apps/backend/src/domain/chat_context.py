"""
Chat Domain Models - Dataclasses for internal data flow.

Uses dataclasses for type-safe, immutable data structures that represent
the chat context and intermediate processing states.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ChatContext:
    """
    Immutable context for a chat request.

    Encapsulates all information needed to process a chat message,
    following the DTO (Data Transfer Object) pattern.
    """

    # Request metadata
    user_id: str
    request_id: str
    timestamp: datetime

    # Chat identification
    chat_id: Optional[str]
    session_id: Optional[str]  # Resolved session ID after get_or_create

    # Message content
    message: str
    context: Optional[List[Dict[str, str]]]

    # Configuration
    model: str
    tools_enabled: Dict[str, bool]
    stream: bool

    # Optional fields with defaults
    document_ids: Optional[List[str]] = None  # Attached documents for RAG
    tool_results: Dict[str, Any] = field(
        default_factory=dict
    )  # MCP tool results for context injection
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    kill_switch_active: bool = False

    def with_session(self, session_id: str) -> "ChatContext":
        """Create new context with resolved session ID."""
        # Since frozen=True, we create a new instance
        return ChatContext(
            user_id=self.user_id,
            request_id=self.request_id,
            timestamp=self.timestamp,
            chat_id=self.chat_id,
            session_id=session_id,
            message=self.message,
            context=self.context,
            document_ids=self.document_ids,
            tool_results=self.tool_results,
            model=self.model,
            tools_enabled=self.tools_enabled,
            stream=self.stream,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            kill_switch_active=self.kill_switch_active,
        )

    def with_model(self, model: str) -> "ChatContext":
        """Create new context with a different model (e.g., routing escalation)."""
        return ChatContext(
            user_id=self.user_id,
            request_id=self.request_id,
            timestamp=self.timestamp,
            chat_id=self.chat_id,
            session_id=self.session_id,
            message=self.message,
            context=self.context,
            document_ids=self.document_ids,
            tool_results=self.tool_results,
            model=model,
            tools_enabled=self.tools_enabled,
            stream=self.stream,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            kill_switch_active=self.kill_switch_active,
        )

    def with_document_ids(self, document_ids: List[str]) -> "ChatContext":
        """Create new context with updated document IDs for RAG."""
        return ChatContext(
            user_id=self.user_id,
            request_id=self.request_id,
            timestamp=self.timestamp,
            chat_id=self.chat_id,
            session_id=self.session_id,
            message=self.message,
            context=self.context,
            document_ids=document_ids,
            tool_results=self.tool_results,
            model=self.model,
            tools_enabled=self.tools_enabled,
            stream=self.stream,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            kill_switch_active=self.kill_switch_active,
        )


@dataclass
class MessageMetadata:
    """Metadata about a processed message."""

    message_id: str
    chat_id: str
    user_message_id: str
    assistant_message_id: Optional[str]
    model_used: str
    tokens_used: Optional[Dict[str, int]] = None
    latency_ms: Optional[float] = None
    decision_metadata: Optional[Dict[str, Any]] = None


@dataclass
class ChatProcessingResult:
    """
    Result of processing a chat message.

    Encapsulates the AI response and all associated metadata.
    """

    # Response content
    content: str
    sanitized_content: str

    # Metadata
    metadata: MessageMetadata

    # Processing info
    processing_time_ms: float
    strategy_used: str  # 'simple' or 'coordinated'

    # Research info (if applicable)
    task_id: Optional[str] = None
    research_triggered: bool = False

    # Session info
    session_title: Optional[str] = None
    session_updated: bool = False


@dataclass
class ChatOperation:
    """
    Represents a chat operation to be executed.

    Follows Command Pattern - encapsulates all information needed
    to execute a chat operation.
    """

    context: ChatContext
    operation_type: str  # 'send_message', 'escalate', 'update_session', etc.
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate operation type."""
        valid_types = {"send_message", "escalate", "update_session", "delete_session"}
        if self.operation_type not in valid_types:
            raise ValueError(f"Invalid operation type: {self.operation_type}")
