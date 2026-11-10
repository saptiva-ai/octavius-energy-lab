"""
Artifact router - basic CRUD for user-created artifacts.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ..core.auth import get_current_user
from ..middleware.rate_limit import limiter
from ..models.artifact import Artifact, ArtifactType
from ..models.chat import ChatSession
from ..models.user import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


class ArtifactCreateRequest(BaseModel):
    """Request payload for creating an artifact."""

    title: str = Field(..., max_length=200)
    type: ArtifactType
    content: Union[str, Dict[str, Any]]
    chat_session_id: Optional[str] = None


class ArtifactUpdateRequest(BaseModel):
    """Request payload for updating an artifact."""

    title: Optional[str] = Field(None, max_length=200)
    content: Union[str, Dict[str, Any]]


class ArtifactVersionResponse(BaseModel):
    """Version payload for responses."""

    version: int
    content: Union[str, Dict[str, Any]]
    created_at: datetime


class ArtifactResponse(BaseModel):
    """Response payload for artifact endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    chat_session_id: Optional[str]
    title: str
    type: ArtifactType
    content: Union[str, Dict[str, Any]]
    versions: List[ArtifactVersionResponse]
    created_at: datetime
    updated_at: datetime


async def _assert_chat_ownership(
    chat_session_id: Optional[str], current_user: User
) -> None:
    """Validate chat ownership when linking artifacts."""
    if not chat_session_id:
        return

    chat_session = await ChatSession.get(chat_session_id)
    if not chat_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found"
        )

    if chat_session.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to link this chat session",
        )


def _to_response(artifact: Artifact) -> ArtifactResponse:
    """Convert Artifact model to response schema."""
    return ArtifactResponse(
        id=str(artifact.id),
        user_id=artifact.user_id,
        chat_session_id=artifact.chat_session_id,
        title=artifact.title,
        type=artifact.type,
        content=artifact.content,
        versions=[
            ArtifactVersionResponse(
                version=v.version, content=v.content, created_at=v.created_at
            )
            for v in artifact.versions
        ],
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


@router.post(
    "/",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("100/hour")  # Max 100 artifact creations per hour per user
async def create_artifact(
    request: Request,
    payload: ArtifactCreateRequest,
    current_user: User = Depends(get_current_user),
) -> ArtifactResponse:
    """Create a new artifact for the authenticated user."""
    await _assert_chat_ownership(payload.chat_session_id, current_user)

    # Chart artifacts must carry a structured (dict) payload
    if payload.type == ArtifactType.CHART and not isinstance(payload.content, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chart content must be a dictionary",
        )

    artifact = Artifact(
        user_id=str(current_user.id),
        chat_session_id=payload.chat_session_id,
        title=payload.title,
        type=payload.type,
        content=payload.content,
        versions=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    artifact.add_version(payload.content)
    await artifact.insert()

    logger.info(
        "Artifact created",
        artifact_id=str(artifact.id),
        user_id=str(current_user.id),
        chat_session_id=payload.chat_session_id,
        type=artifact.type.value,
    )

    return _to_response(artifact)


@router.get(
    "/{artifact_id}",
    response_model=ArtifactResponse,
)
async def get_artifact(
    artifact_id: str, current_user: User = Depends(get_current_user)
) -> ArtifactResponse:
    """Retrieve a single artifact by ID."""
    artifact = await Artifact.get(artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found"
        )

    if artifact.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this artifact",
        )

    return _to_response(artifact)


@router.put(
    "/{artifact_id}",
    response_model=ArtifactResponse,
)
async def update_artifact(
    artifact_id: str,
    payload: ArtifactUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> ArtifactResponse:
    """Update artifact content and append a new version."""
    artifact = await Artifact.get(artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found"
        )

    if artifact.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this artifact",
        )

    if payload.title:
        artifact.title = payload.title

    artifact.add_version(payload.content)
    await artifact.save()

    logger.info(
        "Artifact updated",
        artifact_id=artifact_id,
        user_id=str(current_user.id),
        version=len(artifact.versions),
    )

    return _to_response(artifact)


@router.get(
    "/session/{session_id}/charts",
    response_model=List[Dict[str, Any]],
)
async def get_session_charts(
    session_id: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Get all chart artifacts for a chat session.

    Used by frontend canvas to:
    - Load chart history
    - Multi-chart mode (future)
    - Session cleanup

    Args:
        session_id: Chat session ID
        limit: Maximum number of charts to return (default 10)
        current_user: Authenticated user

    Returns:
        List of chart metadata (id, title, created_at)

    Raises:
        403: If user doesn't own the session
        404: If session not found
    """
    # Verify session ownership
    chat_session = await ChatSession.get(session_id)
    if not chat_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found"
        )

    if chat_session.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this session's charts",
        )

    # Query charts
    charts = (
        await Artifact.find(
            Artifact.chat_session_id == session_id,
            Artifact.type == ArtifactType.CHART,
        )
        .sort("-created_at")
        .limit(limit)
        .to_list()
    )

    logger.info(
        "fetched_session_charts",
        session_id=session_id,
        user_id=str(current_user.id),
        count=len(charts),
    )

    # Return lightweight metadata (not full content)
    return [
        {
            "id": str(chart.id),
            "title": chart.title,
            "type": chart.type.value,
            "created_at": chart.created_at.isoformat(),
        }
        for chart in charts
    ]


@router.get(
    "/{artifact_id}/full",
    response_model=Dict[str, Any],
)
async def get_artifact_full(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get complete artifact including enriched metadata.

    Used by canvas to display:
    - Full Plotly configuration
    - SQL query generated
    - Metric interpretation
    - All metadata fields

    Args:
        artifact_id: Unique artifact ID
        current_user: Authenticated user

    Returns:
        Complete artifact with all fields

    Raises:
        403: If user doesn't own artifact
        404: If artifact not found
    """
    artifact = await Artifact.get(artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found"
        )

    if artifact.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this artifact",
        )

    logger.info(
        "fetched_artifact_full",
        artifact_id=artifact_id,
        user_id=str(current_user.id),
        type=artifact.type.value,
    )

    return {
        "id": str(artifact.id),
        "title": artifact.title,
        "type": artifact.type.value,
        "content": artifact.content,  # Full artifact payload (e.g. plotly_config, metadata)
        "created_at": artifact.created_at.isoformat(),
        "updated_at": artifact.updated_at.isoformat(),
        "session_id": artifact.chat_session_id,
    }
