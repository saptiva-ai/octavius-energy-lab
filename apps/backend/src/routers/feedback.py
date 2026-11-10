"""
Feedback router - handles message feedback (thumbs up/down) from users.

Used for:
- Collecting user ratings on assistant responses
- Analytics and system improvement
- Iterative model/prompt tuning
"""

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..core.auth import get_current_user
from ..middleware.rate_limit import limiter
from ..models.chat import ChatSession
from ..models.feedback import FeedbackRating, MessageFeedback
from ..models.user import User
from ..services.feedback_service import feedback_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackCreateRequest(BaseModel):
    """Request payload for submitting message feedback."""

    message_id: str = Field(..., description="ID of the message being rated")
    conversation_id: str = Field(..., description="Chat session ID")
    rating: str = Field(..., pattern="^(up|down)$", description="Thumbs up or down")
    reason: Optional[str] = Field(
        None, max_length=500, description="Optional explanation for the feedback"
    )


class FeedbackResponse(BaseModel):
    """Response payload after submitting feedback."""

    id: str
    feedback_id: Optional[str] = None  # FDBK-0001 format
    created_at: datetime


class FeedbackDetailResponse(BaseModel):
    """Detailed feedback response for retrieval."""

    id: str
    feedback_id: Optional[str] = None  # FDBK-0001 format
    message_id: str
    conversation_id: str
    rating: str
    reason: Optional[str]
    created_at: datetime


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("60/minute")  # Prevent spam - 60 feedback submissions per minute
async def submit_feedback(
    request: Request,
    payload: FeedbackCreateRequest,
    current_user: User = Depends(get_current_user),
) -> FeedbackResponse:
    """
    Submit feedback for a chat message.

    Users can rate assistant responses with thumbs up/down
    and optionally provide a reason explaining their rating.

    Rate limited to prevent spam.
    """
    # Validate conversation ownership
    chat_session = await ChatSession.get(payload.conversation_id)
    if not chat_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if chat_session.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to submit feedback for this conversation",
        )

    # Check if user already submitted feedback for this message
    existing_feedback = await MessageFeedback.find_one(
        MessageFeedback.message_id == payload.message_id,
        MessageFeedback.user_id == str(current_user.id),
    )

    if existing_feedback:
        # Update existing feedback instead of creating duplicate
        existing_feedback.rating = FeedbackRating(payload.rating)
        existing_feedback.reason = payload.reason
        existing_feedback.created_at = datetime.utcnow()

        # Enrich with context if not already present (CA-06)
        if existing_feedback.context is None:
            context = await feedback_service.get_context_for_message(
                message_id=payload.message_id,
                conversation_id=payload.conversation_id,
            )
            existing_feedback.context = context.to_dict() if context else None

        await existing_feedback.save()

        logger.info(
            "Feedback updated",
            feedback_id=str(existing_feedback.id),
            message_id=payload.message_id,
            user_id=str(current_user.id),
            rating=payload.rating,
        )

        return FeedbackResponse(
            id=str(existing_feedback.id),
            feedback_id=existing_feedback.feedback_id,
            created_at=existing_feedback.created_at,
        )

    # Get context enrichment (CA-06)
    context = await feedback_service.get_context_for_message(
        message_id=payload.message_id,
        conversation_id=payload.conversation_id,
    )
    context_dict = context.to_dict() if context else None

    # Generate incremental feedback ID (FDBK-0001)
    incremental_id = await feedback_service.get_next_feedback_id()

    # Create new feedback with enriched context and incremental ID
    feedback = MessageFeedback(
        message_id=payload.message_id,
        conversation_id=payload.conversation_id,
        user_id=str(current_user.id),
        rating=FeedbackRating(payload.rating),
        reason=payload.reason,
        context=context_dict,
        feedback_id=incremental_id,
    )
    await feedback.insert()

    logger.info(
        "Feedback submitted",
        feedback_id=incremental_id,
        internal_id=str(feedback.id),
        message_id=payload.message_id,
        conversation_id=payload.conversation_id,
        user_id=str(current_user.id),
        rating=payload.rating,
        has_reason=bool(payload.reason),
    )

    return FeedbackResponse(
        id=str(feedback.id),
        feedback_id=incremental_id,
        created_at=feedback.created_at,
    )


@router.get(
    "/message/{message_id}",
    response_model=Optional[FeedbackDetailResponse],
)
async def get_message_feedback(
    message_id: str,
    current_user: User = Depends(get_current_user),
) -> Optional[FeedbackDetailResponse]:
    """
    Get user's feedback for a specific message.

    Returns None if no feedback exists for this message from this user.
    """
    feedback = await MessageFeedback.find_one(
        MessageFeedback.message_id == message_id,
        MessageFeedback.user_id == str(current_user.id),
    )

    if not feedback:
        return None

    return FeedbackDetailResponse(
        id=str(feedback.id),
        feedback_id=feedback.feedback_id,
        message_id=feedback.message_id,
        conversation_id=feedback.conversation_id,
        rating=feedback.rating.value,
        reason=feedback.reason,
        created_at=feedback.created_at,
    )
