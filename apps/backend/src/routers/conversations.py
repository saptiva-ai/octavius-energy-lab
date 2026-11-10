"""
Conversations API endpoints as specified in saptiva-chat-fixes-v3.yaml.
"""

import uuid
from datetime import datetime
from typing import Dict, Optional

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..core.telemetry import metrics_collector
from ..models.chat import ChatSession as ChatSessionModel
from ..models.chat import ConversationState
from ..schemas.chat import ChatSession, ChatSessionListResponse
from ..services.tools import normalize_tools_state

logger = structlog.get_logger(__name__)
router = APIRouter()


class ConversationCreateRequest(BaseModel):
    """Request to create a new conversation."""

    title: Optional[str] = None
    model: str = "Saptiva Turbo"
    tools_enabled: Optional[Dict[str, bool]] = None


class ConversationUpdateRequest(BaseModel):
    """Request to update conversation metadata."""

    title: Optional[str] = None
    auto_title: Optional[bool] = Field(
        default=False,
        description="If True, this is an automatic title (don't set override)",
    )
    model: Optional[str] = None
    tools_enabled: Optional[Dict[str, bool]] = None


class ConversationResponse(BaseModel):
    """Response for conversation operations."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    model: str
    idempotency_key: Optional[str] = None
    tools_enabled: Dict[str, bool] = Field(default_factory=dict)


@router.get(
    "/conversations", response_model=ChatSessionListResponse, tags=["conversations"]
)
async def get_conversations(
    limit: int = 20,
    offset: int = 0,
    search: Optional[str] = None,
    http_request: Request = None,
) -> ChatSessionListResponse:
    """
    GET /api/conversations -> lista compacta (id,title,updatedAt)

    Returns a compact list of conversations for the sidebar.
    """
    user_id = getattr(http_request.state, "user_id", "anonymous")

    try:
        # Build query
        query = ChatSessionModel.find(ChatSessionModel.user_id == user_id)

        # Apply search filter if provided
        if search:
            query = query.find({"title": {"$regex": search, "$options": "i"}})

        # Get total count
        total_count = await query.count()

        # Get sessions with pagination, ordered by most recent update
        sessions_docs = (
            await query.sort(-ChatSessionModel.updated_at)
            .skip(offset)
            .limit(limit)
            .to_list()
        )

        # Convert to response schema
        sessions = []
        for session in sessions_docs:
            sessions.append(
                ChatSession(
                    id=session.id,
                    title=session.title,
                    user_id=session.user_id,
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                    first_message_at=session.first_message_at,  # Progressive Commitment
                    last_message_at=session.last_message_at,  # Progressive Commitment
                    message_count=session.message_count,
                    settings=(
                        session.settings.model_dump()
                        if hasattr(session.settings, "model_dump")
                        else session.settings
                    ),
                    pinned=session.pinned,
                    state=session.state,  # P0-BE-UNIQ-EMPTY: Include state
                    tools_enabled=normalize_tools_state(
                        getattr(session, "tools_enabled", None)
                    ),
                )
            )

        has_more = offset + len(sessions) < total_count

        logger.info(
            "Retrieved conversations list",
            user_id=user_id,
            count=len(sessions),
            total=total_count,
        )

        return ChatSessionListResponse(
            sessions=sessions, total_count=total_count, has_more=has_more
        )

    except Exception as e:
        logger.error("Error retrieving conversations", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversations",
        )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    tags=["conversations"],
)
async def get_conversation(
    conversation_id: str, http_request: Request = None
) -> ConversationResponse:
    """
    GET /api/conversations/:id -> conversation details

    Returns conversation metadata without full message history.
    """
    user_id = getattr(http_request.state, "user_id", "anonymous")

    try:
        # Get conversation
        conversation = await ChatSessionModel.get(conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
            )

        # Check access
        if conversation.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to conversation",
            )

        # Extract model from settings
        model = "Saptiva Turbo"  # default
        if hasattr(conversation.settings, "model"):
            model = conversation.settings.model
        elif (
            isinstance(conversation.settings, dict) and "model" in conversation.settings
        ):
            model = conversation.settings["model"]

        logger.info(
            "Retrieved conversation details",
            conversation_id=conversation_id,
            user_id=user_id,
        )

        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=conversation.message_count,
            model=model,
            idempotency_key=conversation.idempotency_key,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error retrieving conversation",
            error=str(e),
            conversation_id=conversation_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversation",
        )


@router.post(
    "/conversations", response_model=ConversationResponse, tags=["conversations"]
)
async def create_conversation(
    request: ConversationCreateRequest, http_request: Request = None
) -> ConversationResponse:
    """
    POST /api/conversations -> crea nueva conversación o reusa draft existente

    P0-BE-POST-REUSE: Reuses existing empty DRAFT conversation if one exists for the user.
    This prevents creating multiple empty conversations when user clicks "New" repeatedly.

    The unique index 'unique_draft_per_user' in MongoDB enforces one DRAFT per user.
    """
    user_id = getattr(http_request.state, "user_id", "anonymous")
    idempotency_key = None

    if http_request is not None:
        idempotency_key = http_request.headers.get("Idempotency-Key")

    def build_response(
        conversation: ChatSessionModel, fallback_model: str
    ) -> ConversationResponse:
        """Normalize conversation document into API response."""
        model = fallback_model
        settings = conversation.settings
        if hasattr(settings, "model"):
            model = settings.model
        elif isinstance(settings, dict) and "model" in settings:
            model = settings["model"]

        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=conversation.message_count,
            model=model,
            tools_enabled=normalize_tools_state(
                getattr(conversation, "tools_enabled", None)
            ),
        )

    try:
        if idempotency_key:
            logger.info(
                "Create conversation with idempotency key",
                user_id=user_id,
                idempotency_key=idempotency_key,
            )
            existing_with_key = await ChatSessionModel.find_one(
                ChatSessionModel.user_id == user_id,
                ChatSessionModel.idempotency_key == idempotency_key,
            )
            if existing_with_key:
                logger.info(
                    "Returning existing conversation for idempotent request",
                    conversation_id=existing_with_key.id,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                )
                return build_response(existing_with_key, request.model)

        # P0-BE-POST-REUSE: Check if user already has a DRAFT conversation
        existing_draft = await ChatSessionModel.find_one(
            ChatSessionModel.user_id == user_id, ChatSessionModel.state == "draft"
        )

        if existing_draft:
            # If draft is empty (0 messages), reuse it
            if existing_draft.message_count == 0:
                logger.info(
                    "Reusing existing empty draft conversation",
                    conversation_id=existing_draft.id,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                )

                if request.tools_enabled is not None:
                    new_tools_state = normalize_tools_state(request.tools_enabled)
                    await existing_draft.update(
                        {
                            "$set": {
                                "tools_enabled": new_tools_state,
                                "updated_at": datetime.utcnow(),
                            }
                        }
                    )
                    existing_draft.tools_enabled = new_tools_state

                if (
                    idempotency_key
                    and existing_draft.idempotency_key != idempotency_key
                ):
                    await existing_draft.update(
                        {
                            "$set": {
                                "idempotency_key": idempotency_key,
                                "updated_at": datetime.utcnow(),
                            }
                        }
                    )
                    existing_draft.idempotency_key = idempotency_key

                return build_response(existing_draft, request.model)
            else:
                # Draft has messages, convert it to ACTIVE state to allow new draft creation
                logger.info(
                    "Converting non-empty draft to active state",
                    conversation_id=existing_draft.id,
                    user_id=user_id,
                    message_count=existing_draft.message_count,
                    state_from="draft",
                    state_to="active",
                )
                await existing_draft.update(
                    {
                        "$set": {
                            "state": ConversationState.ACTIVE.value,
                            "updated_at": datetime.utcnow(),
                        }
                    }
                )

        # Generate conversation ID and title
        conversation_id = str(uuid.uuid4())
        title = (
            request.title
            or f"Nueva conversación {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        # Create conversation in DRAFT state (enforced by unique index)
        tools_state = normalize_tools_state(request.tools_enabled)

        conversation = ChatSessionModel(
            id=conversation_id,
            user_id=user_id,
            title=title,
            idempotency_key=idempotency_key,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            message_count=0,
            settings={"model": request.model},
            state="draft",  # P0-BE-UNIQ-EMPTY: Explicit DRAFT state
            tools_enabled=tools_state,
        )

        await conversation.insert()

        logger.info(
            "Created new draft conversation",
            conversation_id=conversation_id,
            user_id=user_id,
            title=title,
            model=request.model,
            state="draft",
            idempotency_key=idempotency_key,
        )

        return build_response(conversation, request.model)

    except Exception as e:
        # Handle duplicate key error (E11000) from unique_draft_per_user index
        if "E11000" in str(e) and "unique_draft_per_user" in str(e):
            logger.warning(
                "Duplicate draft detected, attempting to fix orphaned draft",
                error=str(e),
                user_id=user_id,
            )

            # Try to fix by transitioning existing draft with messages to ACTIVE
            try:
                existing_draft_with_msgs = await ChatSessionModel.find_one(
                    ChatSessionModel.user_id == user_id,
                    ChatSessionModel.state == ConversationState.DRAFT.value,
                )

                if (
                    existing_draft_with_msgs
                    and existing_draft_with_msgs.message_count > 0
                ):
                    # Transition to ACTIVE
                    await existing_draft_with_msgs.update(
                        {
                            "$set": {
                                "state": ConversationState.ACTIVE.value,
                                "updated_at": datetime.utcnow(),
                            }
                        }
                    )

                    logger.info(
                        "Fixed orphaned draft, transitioned to active",
                        conversation_id=existing_draft_with_msgs.id,
                        user_id=user_id,
                        message_count=existing_draft_with_msgs.message_count,
                        idempotency_key=idempotency_key,
                    )

                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="An existing draft was fixed. Please try creating a new conversation again.",
                    )
            except HTTPException:
                raise
            except Exception as fix_error:
                logger.error(
                    "Failed to fix orphaned draft",
                    error=str(fix_error),
                    user_id=user_id,
                )

        logger.error(
            "Error creating conversation",
            error=str(e),
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create conversation",
        )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    tags=["conversations"],
)
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdateRequest,
    http_request: Request = None,
) -> ConversationResponse:
    """
    PATCH /api/conversations/:id -> rename/meta

    Updates conversation metadata (title, model, etc.).
    """
    user_id = getattr(http_request.state, "user_id", "anonymous")

    try:
        # Get conversation
        conversation = await ChatSessionModel.get(conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
            )

        # Check access
        if conversation.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to conversation",
            )

        # Prepare updates
        updates = {"updated_at": datetime.utcnow()}

        if request.title is not None:
            updates["title"] = request.title
            # Only mark as manually renamed if this is NOT an automatic title
            if not request.auto_title:
                updates["title_override"] = True

        if request.model is not None:
            # Update settings
            settings = conversation.settings
            if isinstance(settings, dict):
                settings["model"] = request.model
            else:
                settings = {"model": request.model}
            updates["settings"] = settings

        if request.tools_enabled is not None:
            normalized_tools = normalize_tools_state(request.tools_enabled)
            previous_tools = normalize_tools_state(
                getattr(conversation, "tools_enabled", None)
            )

            for tool_name, enabled in normalized_tools.items():
                if previous_tools.get(tool_name) != enabled:
                    metrics_collector.record_tool_toggle(tool_name, enabled)

            updates["tools_enabled"] = normalized_tools

        # Apply updates
        await conversation.update({"$set": updates})

        # Refresh conversation data
        updated_conversation = await ChatSessionModel.get(conversation_id)

        # Extract model from settings
        model = "Saptiva Turbo"  # default
        if hasattr(updated_conversation.settings, "model"):
            model = updated_conversation.settings.model
        elif (
            isinstance(updated_conversation.settings, dict)
            and "model" in updated_conversation.settings
        ):
            model = updated_conversation.settings["model"]

        logger.info(
            "Updated conversation",
            conversation_id=conversation_id,
            user_id=user_id,
            updates=list(updates.keys()),
        )

        return ConversationResponse(
            id=updated_conversation.id,
            title=updated_conversation.title,
            created_at=updated_conversation.created_at,
            updated_at=updated_conversation.updated_at,
            message_count=updated_conversation.message_count,
            model=model,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error updating conversation", error=str(e), conversation_id=conversation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update conversation",
        )


@router.delete("/conversations/{conversation_id}", tags=["conversations"])
async def delete_conversation(conversation_id: str, http_request: Request = None):
    """
    DELETE /api/conversations/:id -> delete conversation

    Deletes a conversation and all its messages.
    """
    user_id = getattr(http_request.state, "user_id", "anonymous")

    try:
        # Get conversation
        conversation = await ChatSessionModel.get(conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
            )

        # Check access
        if conversation.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to conversation",
            )

        # Delete conversation (this should cascade to messages)
        await conversation.delete()

        logger.info(
            "Deleted conversation", conversation_id=conversation_id, user_id=user_id
        )

        return {"message": "Conversation deleted successfully", "id": conversation_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error deleting conversation", error=str(e), conversation_id=conversation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation",
        )


class TitleGenerationRequest(BaseModel):
    """Request to generate a title from message text."""

    text: str = Field(
        ..., min_length=1, max_length=500, description="User message text"
    )


class TitleGenerationResponse(BaseModel):
    """Response with generated title."""

    title: str = Field(..., description="Generated title (3-6 words)")


@router.post("/title", response_model=TitleGenerationResponse, tags=["conversations"])
async def generate_title(request: TitleGenerationRequest) -> TitleGenerationResponse:
    """
    POST /api/title -> Generate a short title from user message

    Uses a lightweight LLM to create a concise title without activating tools.
    Fallback to heuristic if LLM fails.
    """
    try:
        from ..services.saptiva_client import SaptivaClient

        saptiva_client = SaptivaClient()

        # System prompt for title generation (optimized for sidebar UI)
        system_prompt = (
            "Genera un título MUY CORTO de máximo 40 caracteres, usando 3-5 palabras clave. "
            "Extrae solo lo esencial del mensaje. Sin emojis, sin puntuación final, "
            "respeta el idioma original, conserva nombres propios. "
            "NO uses encabezados, formato markdown, ni palabras como 'hola', 'ayuda', 'cómo', 'qué'."
        )

        # Try to generate with LLM (lightweight model, no tools)
        try:
            response = await saptiva_client.chat_completion(
                model="SAPTIVA_TURBO",  # Use fastest model
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Mensaje: {request.text}"},
                ],
                temperature=0.3,  # Low temperature for consistency
                max_tokens=20,  # Short response
            )

            title = response.choices[0]["message"].get("content", "").strip()

            # Clean up the title
            title = title.replace('"', "").replace("'", "")
            # Remove common unwanted prefixes
            for prefix in ["Título:", "Title:", "**", "##"]:
                if title.startswith(prefix):
                    title = title[len(prefix) :].strip()

            # Limit to reasonable length (40 chars for sidebar UI)
            if len(title) > 40:
                title = title[:37] + "..."

            # If title is too short or empty, use fallback
            if len(title) < 3:
                raise ValueError("Generated title too short")

            logger.info(
                "Generated title via LLM",
                original_length=len(request.text),
                title=title,
            )
            return TitleGenerationResponse(title=title)

        except Exception as llm_error:
            logger.warning(
                "LLM title generation failed, using heuristic", error=str(llm_error)
            )
            # Fallback to heuristic
            title = _generate_title_heuristic(request.text)
            return TitleGenerationResponse(title=title)

    except Exception as e:
        logger.error(
            "Error generating title", error=str(e), text_length=len(request.text)
        )
        # Last resort fallback
        title = _generate_title_heuristic(request.text)
        return TitleGenerationResponse(title=title)


def _generate_title_heuristic(text: str) -> str:
    """
    Heuristic title generation as fallback.

    Rules:
    - Take first line, trim whitespace
    - Limit to 40 chars (optimized for sidebar UI)
    - Capitalize first letter
    - Remove final punctuation
    - Smart truncation at word boundaries
    """
    # Clean text
    cleaned = text.replace("\n", " ").strip()

    # Limit length with smart truncation
    if len(cleaned) > 40:
        # Try to truncate at word boundary
        truncated = cleaned[:37]
        last_space = truncated.rfind(" ")
        if last_space > 20:  # Only truncate at word if we keep enough content
            cleaned = truncated[:last_space] + "..."
        else:
            cleaned = truncated + "..."

    # Remove final punctuation
    while cleaned and cleaned[-1] in ".:;!?…":
        cleaned = cleaned[:-1]

    # Capitalize first letter
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]

    # If result is too short or empty, use default
    if len(cleaned) < 3:
        return "Nueva conversación"

    return cleaned


# ============================================================================
# Canvas State Endpoints
# ============================================================================


class CanvasStateUpdate(BaseModel):
    """Canvas state update request"""

    is_sidebar_open: Optional[bool] = None
    active_artifact_id: Optional[str] = None
    active_message_id: Optional[str] = None
    active_chart: Optional[Dict] = None


class CanvasStateResponse(BaseModel):
    """Canvas state response"""

    is_sidebar_open: bool
    active_artifact_id: Optional[str]
    active_message_id: Optional[str]
    active_chart: Optional[Dict]
    updated_at: datetime


@router.patch("/sessions/{session_id}/canvas", tags=["conversations"])
async def save_canvas_state(
    session_id: str, canvas_update: CanvasStateUpdate, request: Request
):
    """
    Save canvas state for a conversation session.
    Updates only the fields provided in the request.
    """
    user_id = request.state.user_id

    # Find session
    session = await ChatSessionModel.find_one(
        ChatSessionModel.id == session_id, ChatSessionModel.user_id == user_id
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    # Prepare update data
    from ..models.chat import CanvasState

    current_canvas = session.canvas_state
    if current_canvas is None:
        # Create new canvas state
        current_canvas = CanvasState()

    # Update only provided fields
    if canvas_update.is_sidebar_open is not None:
        current_canvas.is_sidebar_open = canvas_update.is_sidebar_open
    if canvas_update.active_artifact_id is not None:
        current_canvas.active_artifact_id = canvas_update.active_artifact_id
    if canvas_update.active_message_id is not None:
        current_canvas.active_message_id = canvas_update.active_message_id
    if canvas_update.active_chart is not None:
        current_canvas.active_chart = canvas_update.active_chart

    current_canvas.updated_at = datetime.utcnow()

    # Save to database
    await session.update(
        {
            "$set": {
                "canvas_state": current_canvas.model_dump(),
                "updated_at": datetime.utcnow(),
            }
        }
    )

    logger.info(
        "Canvas state saved",
        session_id=session_id,
        is_open=current_canvas.is_sidebar_open,
        has_chart=bool(current_canvas.active_chart),
    )

    return {"status": "success", "message": "Canvas state saved"}


@router.get(
    "/sessions/{session_id}/canvas",
    response_model=CanvasStateResponse,
    tags=["conversations"],
)
async def get_canvas_state(session_id: str, request: Request):
    """
    Get canvas state for a conversation session.
    Returns the persisted canvas state or default values if not set.
    """
    user_id = request.state.user_id

    # Find session
    session = await ChatSessionModel.find_one(
        ChatSessionModel.id == session_id, ChatSessionModel.user_id == user_id
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    # Return canvas state or defaults
    if session.canvas_state:
        return CanvasStateResponse(
            is_sidebar_open=session.canvas_state.is_sidebar_open,
            active_artifact_id=session.canvas_state.active_artifact_id,
            active_message_id=session.canvas_state.active_message_id,
            active_chart=session.canvas_state.active_chart,
            updated_at=session.canvas_state.updated_at,
        )
    else:
        # Return default canvas state
        return CanvasStateResponse(
            is_sidebar_open=False,
            active_artifact_id=None,
            active_message_id=None,
            active_chart=None,
            updated_at=session.updated_at,
        )
