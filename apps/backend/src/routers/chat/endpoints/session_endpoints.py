"""
Session Endpoints - HTTP endpoints for chat session management.

This module contains endpoints related to managing chat sessions.

Endpoints:
    GET    /sessions                    - List user's chat sessions
    GET    /sessions/{id}/research      - Get research tasks for session
    PATCH  /sessions/{id}               - Update session (rename, pin)
    DELETE /sessions/{id}               - Delete session and messages

Responsibilities:
    - Session CRUD operations
    - Research tasks retrieval
    - Permission checks
    - Cache invalidation
"""

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status

from ....core.exceptions import NotFoundError
from ....core.redis_cache import get_redis_cache
from ....models.chat import ChatMessage as ChatMessageModel
from ....schemas.chat import (
    CanvasStateUpdateRequest,
    ChatSessionListResponse,
    ChatSessionUpdateRequest,
)
from ....schemas.common import ApiResponse
from ....services.history_service import HistoryService

logger = structlog.get_logger(__name__)
router = APIRouter()

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@router.get("/sessions", response_model=ChatSessionListResponse, tags=["chat"])
async def get_chat_sessions(
    response: Response, limit: int = 20, offset: int = 0, http_request: Request = None
) -> ChatSessionListResponse:
    """
    Get chat sessions for the authenticated user.

    Returns paginated list of user's chat sessions ordered by last activity.

    Args:
        response: HTTP response for headers
        limit: Maximum number of sessions to return (default: 20)
        offset: Number of sessions to skip (default: 0)
        http_request: HTTP request with user_id in state

    Returns:
        ChatSessionListResponse with sessions list and pagination info
    """
    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(http_request.state, "user_id", "mock-user-id")

    try:
        # Use HistoryService for consistent session retrieval
        result = await HistoryService.get_chat_sessions(
            user_id=user_id, limit=limit, offset=offset
        )

        logger.info(
            "Retrieved chat sessions",
            user_id=user_id,
            session_count=len(result["sessions"]),
            total_count=result["total_count"],
        )

        return ChatSessionListResponse(
            sessions=result["sessions"],
            total_count=result["total_count"],
            has_more=result["has_more"],
        )

    except Exception as exc:
        logger.error(
            "Error retrieving chat sessions",
            error=str(exc),
            exc_type=type(exc).__name__,
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat sessions",
        )


@router.get("/sessions/{session_id}/research", tags=["chat"])
async def get_session_research_tasks(
    session_id: str,
    response: Response,
    limit: int = 20,
    offset: int = 0,
    status_filter: Optional[str] = None,
    http_request: Request = None,
):
    """
    Get all research tasks associated with a chat session.

    Returns research tasks (deep research, web search, etc.) for the session.

    Args:
        session_id: Chat session ID
        response: HTTP response for headers
        limit: Maximum number of tasks to return
        offset: Number of tasks to skip
        status_filter: Filter by task status (pending, running, completed, failed)
        http_request: HTTP request with user_id in state

    Returns:
        JSON response with research tasks and pagination info
    """
    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(http_request.state, "user_id", "mock-user-id")

    try:
        # Verify access using HistoryService
        await HistoryService.get_session_with_permission_check(session_id, user_id)

        cache = await get_redis_cache()

        # Check cache first for research tasks list
        cached_tasks = await cache.get_research_tasks(
            session_id=session_id,
            limit=limit,
            offset=offset,
            status_filter=status_filter,
        )

        if cached_tasks:
            logger.debug(
                "Returning cached research tasks",
                session_id=session_id,
                limit=limit,
                offset=offset,
                status_filter=status_filter,
            )
            return cached_tasks

        # Import here to avoid circular imports
        from ....models.task import Task as TaskModel

        # Build query for research tasks
        query = TaskModel.find(
            TaskModel.chat_id == session_id, TaskModel.task_type == "deep_research"
        )

        # Apply status filter if provided
        if status_filter:
            query = query.find(TaskModel.status == status_filter)

        # Get total count
        total_count = await query.count()

        # Get tasks with pagination
        task_docs = (
            await query.sort(-TaskModel.created_at).skip(offset).limit(limit).to_list()
        )

        # Convert to response format
        research_tasks = []
        for task in task_docs:
            research_tasks.append(
                {
                    "task_id": str(task.id),
                    "status": task.status.value,
                    "progress": task.progress,
                    "current_step": task.current_step,
                    "total_steps": task.total_steps,
                    "created_at": task.created_at,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at,
                    "error_message": task.error_message,
                    "input_data": task.input_data,
                    "result_data": task.result_data,
                    "metadata": task.metadata,
                }
            )

        response_data = {
            "tasks": research_tasks,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + len(research_tasks)) < total_count,
        }

        # Cache the result
        await cache.set_research_tasks(
            session_id=session_id,
            tasks_data=response_data,
            limit=limit,
            offset=offset,
            status_filter=status_filter,
        )

        logger.info(
            "Retrieved research tasks",
            session_id=session_id,
            task_count=len(research_tasks),
            total_count=total_count,
        )

        return response_data

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.detail,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error retrieving research tasks",
            session_id=session_id,
            error=str(exc),
            exc_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve research tasks",
        )


@router.patch("/sessions/{chat_id}", response_model=ApiResponse, tags=["chat"])
async def update_chat_session(
    chat_id: str,
    update_request: ChatSessionUpdateRequest,
    http_request: Request,
    response: Response,
) -> ApiResponse:
    """
    Update a chat session (rename, pin/unpin).

    Allows updating session title and pinned status.

    Args:
        chat_id: Chat session ID to update
        update_request: Update request with optional title and pinned fields
        http_request: HTTP request with user_id in state
        response: HTTP response for headers

    Returns:
        ApiResponse with success status and updated fields
    """
    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(http_request.state, "user_id", "mock-user-id")

    try:
        # Verify access using HistoryService
        chat_session = await HistoryService.get_session_with_permission_check(
            chat_id, user_id
        )

        # Update fields if provided
        update_data = {}
        if update_request.title is not None:
            update_data["title"] = update_request.title
        if update_request.pinned is not None:
            update_data["pinned"] = update_request.pinned

        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            await chat_session.update({"$set": update_data})

        logger.info(
            "Chat session updated",
            chat_id=chat_id,
            user_id=user_id,
            updates=update_data,
        )

        return ApiResponse(
            success=True,
            message="Chat session updated successfully",
            data={"chat_id": chat_id, "updated_fields": list(update_data.keys())},
        )

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.detail,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to update chat session",
            error=str(exc),
            exc_type=type(exc).__name__,
            chat_id=chat_id,
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update chat session",
        )


@router.delete("/sessions/{chat_id}", response_model=ApiResponse, tags=["chat"])
async def delete_chat_session(
    chat_id: str, http_request: Request, response: Response
) -> ApiResponse:
    """
    Delete a chat session and all its messages.

    Permanently deletes the session and all associated messages.
    This operation cannot be undone.

    Args:
        chat_id: Chat session ID to delete
        http_request: HTTP request with user_id in state
        response: HTTP response for headers

    Returns:
        ApiResponse with success status
    """
    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(http_request.state, "user_id", "mock-user-id")

    try:
        # Verify access using HistoryService
        chat_session = await HistoryService.get_session_with_permission_check(
            chat_id, user_id
        )

        cache = await get_redis_cache()

        # Delete all messages in the chat
        await ChatMessageModel.find(ChatMessageModel.chat_id == chat_id).delete()

        # Delete the chat session
        await chat_session.delete()

        # Invalidate all caches for this chat
        await cache.invalidate_all_for_chat(chat_id)

        logger.info("Deleted chat session", chat_id=chat_id, user_id=user_id)

        return ApiResponse(success=True, message="Chat session deleted successfully")

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.detail,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error deleting chat session",
            error=str(exc),
            exc_type=type(exc).__name__,
            chat_id=chat_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete chat session",
        )


@router.patch(
    "/sessions/{session_id}/canvas", response_model=ApiResponse, tags=["chat"]
)
async def update_canvas_state(
    session_id: str,
    canvas_update: CanvasStateUpdateRequest,
    http_request: Request,
    response: Response,
) -> ApiResponse:
    """
    Update canvas state for a chat session.

    Saves the current state of the canvas sidebar (open/closed, active chart, etc.)
    to MongoDB for persistence across page refreshes.

    Args:
        session_id: Chat session ID
        canvas_update: Canvas state update request
        http_request: HTTP request with user_id in state
        response: HTTP response for headers

    Returns:
        ApiResponse with success status
    """

    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(http_request.state, "user_id", "mock-user-id")

    try:
        # Verify access
        chat_session = await HistoryService.get_session_with_permission_check(
            session_id, user_id
        )

        # Create or update canvas state
        canvas_state_data = canvas_update.model_dump(exclude_unset=True)
        canvas_state_data["updated_at"] = datetime.utcnow()

        # Update the session
        await chat_session.update(
            {
                "$set": {
                    "canvas_state": canvas_state_data,
                    "updated_at": datetime.utcnow(),
                }
            }
        )

        logger.info(
            "Canvas state updated",
            session_id=session_id,
            user_id=user_id,
            is_open=canvas_state_data.get("is_sidebar_open"),
            has_chart=canvas_state_data.get("active_chart") is not None,
        )

        return ApiResponse(
            success=True,
            message="Canvas state updated successfully",
            data={"session_id": session_id},
        )

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.detail,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to update canvas state",
            error=str(exc),
            exc_type=type(exc).__name__,
            session_id=session_id,
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update canvas state",
        )


@router.get("/sessions/{session_id}/canvas", tags=["chat"])
async def get_canvas_state(session_id: str, http_request: Request, response: Response):
    """
    Get canvas state for a chat session.

    Retrieves the persisted canvas sidebar state from MongoDB.

    Args:
        session_id: Chat session ID
        http_request: HTTP request with user_id in state
        response: HTTP response for headers

    Returns:
        Canvas state data or null if not set
    """
    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(http_request.state, "user_id", "mock-user-id")

    try:
        # Verify access
        chat_session = await HistoryService.get_session_with_permission_check(
            session_id, user_id
        )

        canvas_state = chat_session.canvas_state

        logger.info(
            "Canvas state retrieved",
            session_id=session_id,
            user_id=user_id,
            has_state=canvas_state is not None,
        )

        return ApiResponse(
            success=True,
            message="Canvas state retrieved",
            data=canvas_state.model_dump() if canvas_state else None,
        )

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.detail,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to retrieve canvas state",
            error=str(exc),
            exc_type=type(exc).__name__,
            session_id=session_id,
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve canvas state",
        )
