"""
Unified history API endpoints for chat + research timeline.
"""

import time
from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from ..core.config import Settings, get_settings
from ..models.chat import MessageRole
from ..models.history import HistoryEventType
from ..schemas.chat import ChatHistoryResponse, ChatSessionListResponse
from ..services.history_service import HistoryService

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/history", response_model=ChatSessionListResponse, tags=["history"])
async def get_chat_history_overview(
    limit: int = Query(
        default=20, ge=1, le=100, description="Number of sessions to retrieve"
    ),
    offset: int = Query(default=0, ge=0, description="Number of sessions to skip"),
    search: Optional[str] = Query(default=None, description="Search in session titles"),
    date_from: Optional[datetime] = Query(
        default=None, description="Filter sessions from date"
    ),
    date_to: Optional[datetime] = Query(
        default=None, description="Filter sessions to date"
    ),
    http_request: Request = None,
) -> ChatSessionListResponse:
    """
    Get chat session history overview with optional filtering.
    """
    user_id = getattr(http_request.state, "user_id", "anonymous")

    try:
        # Get sessions using service
        result = await HistoryService.get_chat_sessions(
            user_id=user_id,
            limit=limit,
            offset=offset,
            search=search,
            date_from=date_from,
            date_to=date_to,
        )

        return ChatSessionListResponse(
            sessions=result["sessions"],
            total_count=result["total_count"],
            has_more=result["has_more"],
        )

    except Exception as e:
        logger.error(
            "Error retrieving chat history overview", error=str(e), user_id=user_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat history",
        )


@router.get("/history/{chat_id}", response_model=ChatHistoryResponse, tags=["history"])
async def get_chat_detailed_history(
    chat_id: str,
    limit: int = Query(
        default=50, ge=1, le=200, description="Number of messages to retrieve"
    ),
    offset: int = Query(default=0, ge=0, description="Number of messages to skip"),
    include_system: bool = Query(default=False, description="Include system messages"),
    message_type: Optional[MessageRole] = Query(
        default=None, description="Filter by message role"
    ),
    http_request: Request = None,
) -> ChatHistoryResponse:
    """
    Get detailed chat history for a specific session.
    """
    user_id = getattr(http_request.state, "user_id", "anonymous")

    try:
        # Verify access
        await HistoryService.get_session_with_permission_check(chat_id, user_id)

        # Get messages using service
        result = await HistoryService.get_chat_messages(
            chat_id=chat_id,
            limit=limit,
            offset=offset,
            include_system=include_system,
            message_type=message_type.value if message_type else None,
        )

        return ChatHistoryResponse(
            chat_id=chat_id,
            messages=result["messages"],
            total_count=result["total_count"],
            has_more=result["has_more"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error retrieving detailed chat history", error=str(e), chat_id=chat_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat history",
        )


@router.get("/history/{chat_id}/export", tags=["history"])
async def export_chat_history(
    chat_id: str,
    format: str = Query(
        default="json", pattern="^(json|csv|txt)$", description="Export format"
    ),
    include_metadata: bool = Query(
        default=False, description="Include message metadata"
    ),
    http_request: Request = None,
):
    """
    Export chat history in various formats.
    """
    user_id = getattr(http_request.state, "user_id", "anonymous")

    try:
        # Verify access
        await HistoryService.get_session_with_permission_check(chat_id, user_id)

        # Export using service
        return await HistoryService.export_chat_history(
            chat_id=chat_id, format=format, include_metadata=include_metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error exporting chat history", error=str(e), chat_id=chat_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export chat history",
        )


@router.get("/history/stats", tags=["history"])
async def get_user_chat_stats(
    http_request: Request,
    days: int = Query(
        default=30, ge=1, le=365, description="Number of days to analyze"
    ),
):
    """
    Get chat usage statistics for the user.
    """
    user_id = getattr(http_request.state, "user_id", "anonymous")

    try:
        # Get stats using service
        return await HistoryService.get_user_chat_statistics(user_id=user_id, days=days)

    except Exception as e:
        logger.error("Error retrieving chat stats", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat statistics",
        )


# ======================================
# UNIFIED HISTORY ENDPOINTS (New)
# ======================================

# Cache headers for history responses
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@router.get("/history/{chat_id}/unified", tags=["history"])
async def get_unified_chat_history(
    chat_id: str,
    response: Response,
    request: Request,
    limit: int = Query(
        default=50, ge=1, le=200, description="Number of events to return"
    ),
    offset: int = Query(default=0, ge=0, description="Number of events to skip"),
    event_types: Optional[str] = Query(
        None, description="Comma-separated event types filter"
    ),
    include_research: bool = Query(default=True, description="Include research events"),
    include_sources: bool = Query(
        default=False, description="Include source discovery events"
    ),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """
    Get unified chat + research history with pagination and caching.

    Returns events ordered chronologically with support for:
    - Pagination (limit/offset)
    - Event type filtering
    - Redis caching for performance
    - P95 latency <= 600ms target
    """

    start_time = time.time()
    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(request.state, "user_id", "mock-user-id")

    try:
        # Verify access and existence
        chat_session = await HistoryService.get_session_with_permission_check(
            chat_id, user_id
        )

        # Parse event types filter
        event_type_filter = None
        if event_types:
            try:
                event_type_filter = [
                    HistoryEventType(t.strip()) for t in event_types.split(",")
                ]
            except ValueError as e:
                return JSONResponse(
                    content={
                        "error": "Invalid event type",
                        "message": f"Invalid event type in filter: {str(e)}",
                    },
                    status_code=status.HTTP_400_BAD_REQUEST,
                    headers=NO_STORE_HEADERS,
                )

        # Build event type filter based on parameters
        if event_type_filter is None:
            event_type_filter = [HistoryEventType.CHAT_MESSAGE]

            if include_research:
                event_type_filter.extend(
                    [
                        HistoryEventType.RESEARCH_STARTED,
                        HistoryEventType.RESEARCH_PROGRESS,
                        HistoryEventType.RESEARCH_COMPLETED,
                        HistoryEventType.RESEARCH_FAILED,
                    ]
                )

            if include_sources:
                event_type_filter.extend(
                    [
                        HistoryEventType.SOURCE_FOUND,
                        HistoryEventType.EVIDENCE_DISCOVERED,
                    ]
                )

        # Get timeline from service (includes caching)
        timeline_data = await HistoryService.get_chat_timeline(
            chat_id=chat_id,
            limit=limit,
            offset=offset,
            event_types=event_type_filter,
            use_cache=True,
        )

        # If no events, return empty structure instead of 404
        if not timeline_data:
            timeline_data = {
                "chat_id": chat_id,
                "events": [],
                "total_count": 0,
                "has_more": False,
                "limit": limit,
                "offset": offset,
            }
        else:
            # Ensure events key exists even if empty
            timeline_data.setdefault("events", [])
            timeline_data.setdefault("total_count", 0)
            timeline_data.setdefault("has_more", False)
            timeline_data.setdefault("limit", limit)
            timeline_data.setdefault("offset", offset)

        processing_time = (time.time() - start_time) * 1000

        # Add performance metadata
        timeline_data.update(
            {
                "latency_ms": int(processing_time),
                "user_id": user_id,
                "filters": {
                    "include_research": include_research,
                    "include_sources": include_sources,
                    "event_types": (
                        [et.value for et in event_type_filter]
                        if event_type_filter
                        else None
                    ),
                },
            }
        )

        logger.info(
            "Retrieved unified chat history",
            chat_id=chat_id,
            user_id=user_id,
            event_count=len(timeline_data["events"]),
            total_count=timeline_data["total_count"],
            latency_ms=processing_time,
            limit=limit,
            offset=offset,
        )

        return JSONResponse(content=timeline_data, headers=NO_STORE_HEADERS)

    except HTTPException:
        raise
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        logger.error(
            "Error retrieving unified chat history",
            chat_id=chat_id,
            user_id=user_id,
            error=str(e),
            latency_ms=processing_time,
        )
        return JSONResponse(
            content={
                "error": "Internal server error",
                "chat_id": chat_id,
                "message": "Failed to retrieve chat history",
                "latency_ms": int(processing_time),
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers=NO_STORE_HEADERS,
        )


@router.get("/history/{chat_id}/research/{task_id}", tags=["history"])
async def get_research_timeline(
    chat_id: str,
    task_id: str,
    response: Response,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """
    Get research-specific timeline for a task.

    Returns all research events (started, progress, sources, completed) for a specific task.
    """

    start_time = time.time()
    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(request.state, "user_id", "mock-user-id")

    try:
        # Verify access
        await HistoryService.get_session_with_permission_check(chat_id, user_id)

        # Get research timeline
        events = await HistoryService.get_research_timeline(chat_id, task_id)

        processing_time = (time.time() - start_time) * 1000

        result = {
            "chat_id": chat_id,
            "task_id": task_id,
            "events": [event.model_dump(mode="json") for event in events],
            "event_count": len(events),
            "latency_ms": int(processing_time),
        }

        logger.info(
            "Retrieved research timeline",
            chat_id=chat_id,
            task_id=task_id,
            user_id=user_id,
            event_count=len(events),
            latency_ms=processing_time,
        )

        return JSONResponse(content=result, headers=NO_STORE_HEADERS)

    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        logger.error(
            "Error retrieving research timeline",
            chat_id=chat_id,
            task_id=task_id,
            user_id=user_id,
            error=str(e),
            latency_ms=processing_time,
        )
        return JSONResponse(
            content={
                "error": "Failed to retrieve research timeline",
                "latency_ms": int(processing_time),
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers=NO_STORE_HEADERS,
        )


@router.get("/history/{chat_id}/status", tags=["history"])
async def get_chat_status(
    chat_id: str,
    response: Response,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """
    Get current status of chat including active research tasks.

    Lightweight endpoint for UI status checking.
    """

    start_time = time.time()
    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(request.state, "user_id", "mock-user-id")

    try:
        # Verify access
        chat_session = await HistoryService.get_session_with_permission_check(
            chat_id, user_id
        )

        # Get recent events for status check
        recent_timeline = await HistoryService.get_chat_timeline(
            chat_id=chat_id,
            limit=10,
            offset=0,
            event_types=None,  # All types
            use_cache=False,  # Always fresh for status
        )

        # Find active research tasks
        active_research = []
        for event in recent_timeline["events"]:
            if (
                event["event_type"] in ["research_started", "research_progress"]
                and event["status"] == "processing"
            ):
                active_research.append(
                    {
                        "task_id": event["task_id"],
                        "progress": event.get("research_data", {}).get("progress", 0),
                        "current_step": event.get("research_data", {}).get(
                            "current_step"
                        ),
                        "started_at": event["timestamp"],
                    }
                )

        processing_time = (time.time() - start_time) * 1000

        result = {
            "chat_id": chat_id,
            "status": "active" if active_research else "idle",
            "message_count": chat_session.message_count,
            "last_activity": chat_session.updated_at.isoformat(),
            "active_research": active_research,
            "active_research_count": len(active_research),
            "latency_ms": int(processing_time),
        }

        return JSONResponse(content=result, headers=NO_STORE_HEADERS)

    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        logger.error(
            "Error retrieving chat status",
            chat_id=chat_id,
            user_id=user_id,
            error=str(e),
            latency_ms=processing_time,
        )
        return JSONResponse(
            content={
                "error": "Failed to retrieve chat status",
                "latency_ms": int(processing_time),
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers=NO_STORE_HEADERS,
        )
