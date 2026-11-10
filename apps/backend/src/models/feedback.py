"""
Message Feedback models for collecting user reactions to AI responses.

Used for:
- Collecting thumbs up/down ratings on assistant messages
- Storing optional reasons for feedback (what was good/bad)
- Analytics and system improvement iteration
- Tracking feedback with incremental IDs (FDBK-0001)
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from beanie import Document, Indexed
from pydantic import Field


class FeedbackRating(str, Enum):
    """Feedback rating enumeration"""

    UP = "up"
    DOWN = "down"


class FeedbackStatus(str, Enum):
    """Feedback tracking status"""

    NEW = "new"
    OPEN = "Open"
    BACKLOG = "Backlog"
    IN_PROGRESS = "In Progress"
    REVIEW = "Review"
    DONE = "Done"
    CLOSED = "Closed"


class MessageFeedback(Document):
    """
    Message feedback document model.

    Stores user feedback (thumbs up/down) for assistant messages
    to enable system improvement and analytics.

    Includes incremental feedback_id (FDBK-0001) for easy reference
    and ticket tracking for issue management.
    """

    id: str = Field(default_factory=lambda: str(uuid4()), alias="_id")
    message_id: Indexed(str) = Field(..., description="ID of the message being rated")
    conversation_id: Indexed(str) = Field(..., description="Chat session ID")
    user_id: Indexed(str) = Field(..., description="User who submitted feedback")
    rating: FeedbackRating = Field(..., description="Thumbs up or down")
    reason: Optional[str] = Field(
        None, max_length=500, description="Optional explanation for the feedback"
    )
    context: Optional[Dict[str, Any]] = Field(
        None,
        description="Enriched context: original_query, response_text, sql_executed, intent, confidence",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When feedback was submitted"
    )

    # Incremental Feedback ID system (FDBK-0001, FDBK-0002, etc.)
    feedback_id: Optional[Indexed(str, unique=True)] = Field(
        None, description="Human-readable incremental ID (FDBK-0001)"
    )

    # Ticket tracking for issue management
    ticket_id: Optional[str] = Field(
        None, description="Linked kanban ticket ID (e.g., 2026-02-04__BUG__example)"
    )
    status: FeedbackStatus = Field(
        default=FeedbackStatus.NEW, description="Tracking status for feedback triage"
    )
    assigned_to: Optional[str] = Field(
        None, description="Email of person assigned to handle this feedback"
    )

    class Settings:
        name = "message_feedback"
        indexes = [
            "message_id",
            "conversation_id",
            "user_id",
            "rating",
            "created_at",
            "feedback_id",  # Unique index for FDBK-XXXX lookup
            "status",  # Filter by status
            [("conversation_id", 1), ("created_at", -1)],  # Feedback history per chat
            [("user_id", 1), ("rating", 1)],  # User's feedback patterns
            [("message_id", 1), ("user_id", 1)],  # Unique feedback per message per user
            [("status", 1), ("created_at", -1)],  # Filter by status, sorted by date
        ]

    def __str__(self) -> str:
        return f"MessageFeedback(id={self.id}, message_id={self.message_id}, rating={self.rating})"
