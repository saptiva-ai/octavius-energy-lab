"""
Feedback Service - Context enrichment for message feedback (CA-06).

Enriches feedback with context from the original conversation:
- Original user query
- Response text
- SQL executed (if applicable)
- Intent classification
- Confidence score
- Data returned (chart artifacts, etc.)

Also handles incremental Feedback ID generation (FDBK-0001).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import structlog

    logger = structlog.get_logger(__name__)
except ModuleNotFoundError:
    import logging

    logger = logging.getLogger(__name__)

from pymongo import ReturnDocument

from ..models.chat import ChatMessage, MessageRole
from ..models.feedback import FeedbackRating


@dataclass
class FeedbackContext:
    """
    Context extracted from the conversation for feedback enrichment.

    Contains all relevant information about the message being rated:
    - What the user asked (original_query)
    - What the system responded (response_text)
    - Technical details (SQL, intent, confidence)
    """

    original_query: Optional[str] = None
    response_text: Optional[str] = None
    sql_executed: Optional[str] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    handler_name: Optional[str] = None
    data_returned: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        result = {}
        if self.original_query is not None:
            result["original_query"] = self.original_query
        if self.response_text is not None:
            result["response_text"] = self.response_text
        if self.sql_executed is not None:
            result["sql_executed"] = self.sql_executed
        if self.intent is not None:
            result["intent"] = self.intent
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.handler_name is not None:
            result["handler_name"] = self.handler_name
        if self.data_returned is not None:
            result["data_returned"] = self.data_returned
        return result


@dataclass
class EnrichedFeedback:
    """
    Feedback enriched with context from the conversation.

    Combines base feedback fields with extracted context.
    """

    message_id: str
    conversation_id: str
    user_id: str
    rating: FeedbackRating
    reason: Optional[str] = None
    context: Optional[FeedbackContext] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        result = {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "rating": (
                self.rating.value
                if isinstance(self.rating, FeedbackRating)
                else self.rating
            ),
        }
        if self.reason is not None:
            result["reason"] = self.reason
        if self.context is not None:
            result["context"] = self.context.to_dict()
        return result


class FeedbackService:
    """
    Service for feedback context enrichment and ID generation.

    Extracts context from conversation messages to enrich feedback
    with diagnostic information useful for system improvement.

    Also generates incremental Feedback IDs (FDBK-0001) using
    MongoDB's findAndModify for atomic counter increment.
    """

    async def get_next_feedback_id(self) -> str:
        """
        Generate the next incremental Feedback ID (FDBK-0001, FDBK-0002, etc.)

        Uses MongoDB's findAndModify with upsert for atomic counter increment.
        The counter is stored in a 'counters' collection.

        Returns:
            str: Formatted feedback ID like "FDBK-0001"
        """
        from ..core.database import Database

        db = Database.get_database()
        if db is None:
            raise RuntimeError("Database not initialized")

        counters = db.counters

        # Atomic increment with upsert
        result = await counters.find_one_and_update(
            {"_id": "feedback_id"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        seq = result["seq"]
        feedback_id = f"FDBK-{seq:04d}"

        logger.info("Generated feedback ID", feedback_id=feedback_id, seq=seq)
        return feedback_id

    async def get_context_for_message(
        self,
        message_id: str,
        conversation_id: str,
    ) -> Optional[FeedbackContext]:
        """
        Extract context for a message being rated.

        Fetches the message and the previous user message to build
        a complete context for the feedback.

        Args:
            message_id: ID of the assistant message being rated
            conversation_id: ID of the conversation

        Returns:
            FeedbackContext with extracted information, or None if message not found
        """
        # Get the message being rated
        message = await self._get_message(message_id)
        if message is None:
            logger.warning(
                "Message not found for feedback enrichment",
                message_id=message_id,
            )
            return None

        # Get the previous user message (original query)
        user_message = await self._get_previous_user_message(
            conversation_id=conversation_id,
            before_message_id=message_id,
        )

        # Extract context from message metadata
        metadata = message.metadata or {}

        return FeedbackContext(
            original_query=user_message.content if user_message else None,
            response_text=message.content,
            sql_executed=metadata.get("sql_query"),
            intent=metadata.get("intent"),
            confidence=metadata.get("confidence"),
            handler_name=metadata.get("handler_name"),
            data_returned=metadata.get("chart_data"),
        )

    async def enrich_feedback(
        self,
        message_id: str,
        conversation_id: str,
        user_id: str,
        rating: FeedbackRating,
        reason: Optional[str] = None,
    ) -> EnrichedFeedback:
        """
        Create enriched feedback with context.

        Args:
            message_id: ID of the message being rated
            conversation_id: ID of the conversation
            user_id: ID of the user submitting feedback
            rating: Thumbs up or down
            reason: Optional explanation

        Returns:
            EnrichedFeedback with context
        """
        context = await self.get_context_for_message(
            message_id=message_id,
            conversation_id=conversation_id,
        )

        return EnrichedFeedback(
            message_id=message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            rating=rating,
            reason=reason,
            context=context,
        )

    async def _get_message(self, message_id: str) -> Optional[ChatMessage]:
        """Fetch a message by ID."""
        try:
            return await ChatMessage.get(message_id)
        except Exception as e:
            logger.error(
                "Error fetching message",
                message_id=message_id,
                error=str(e),
            )
            return None

    async def _get_previous_user_message(
        self,
        conversation_id: str,
        before_message_id: str,
    ) -> Optional[ChatMessage]:
        """
        Find the user message that preceded the assistant message.

        This is the "original query" that triggered the response being rated.
        """
        try:
            # Find user messages in the conversation before the rated message
            user_messages = (
                await ChatMessage.find(
                    ChatMessage.chat_id == conversation_id,
                    ChatMessage.role == MessageRole.USER,
                )
                .sort("-created_at")
                .limit(10)
                .to_list()
            )

            if not user_messages:
                return None

            # Get the rated message to compare timestamps
            rated_message = await ChatMessage.get(before_message_id)
            if not rated_message:
                # Fallback: return most recent user message
                return user_messages[0] if user_messages else None

            # Find the user message just before the rated message
            for msg in user_messages:
                if msg.created_at < rated_message.created_at:
                    return msg

            # Fallback: return most recent user message
            return user_messages[0] if user_messages else None

        except Exception as e:
            logger.error(
                "Error fetching previous user message",
                conversation_id=conversation_id,
                before_message_id=before_message_id,
                error=str(e),
            )
            return None


# Singleton instance for dependency injection
feedback_service = FeedbackService()
