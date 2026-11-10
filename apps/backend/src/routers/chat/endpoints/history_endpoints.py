"""
History Endpoints - HTTP endpoints for chat history retrieval.

This module contains endpoints related to retrieving chat message history.

Endpoints:
    GET /history/{chat_id} - Get chat history with optional research tasks

Responsibilities:
    - Message history retrieval
    - Research task enrichment
    - Pagination and filtering
    - Cache management
"""

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status

from ....core.exceptions import NotFoundError
from ....core.redis_cache import get_redis_cache
from ....models.chat import ChatMessage as ChatMessageModel
from ....models.chat import MessageRole
from ....schemas.chat import ChatHistoryResponse, ChatMessage
from ....services.history_service import HistoryService

logger = structlog.get_logger(__name__)
router = APIRouter()

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@router.get("/history/{chat_id}", response_model=ChatHistoryResponse, tags=["chat"])
async def get_chat_history(
    chat_id: str,
    response: Response,
    limit: int = 50,
    offset: int = 0,
    include_system: bool = False,
    include_research_tasks: bool = True,
    http_request: Request = None,
) -> ChatHistoryResponse:
    """
    Get chat history for a specific chat session with optional research tasks.

    Retrieves message history with pagination and optional research task enrichment.

    Args:
        chat_id: Chat session ID
        response: HTTP response for headers
        limit: Maximum number of messages to return (default: 50)
        offset: Number of messages to skip (default: 0)
        include_system: Include system messages in response (default: False)
        include_research_tasks: Include research task data in messages (default: True)
        http_request: HTTP request with user_id in state

    Returns:
        ChatHistoryResponse with messages and pagination info

    Notes:
        - Messages are ordered by created_at descending (newest first)
        - Research tasks are enriched in message metadata
        - Response is cached for performance
    """
    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(http_request.state, "user_id", "mock-user-id")

    try:
        # Check cache first
        cache = await get_redis_cache()
        cached_history = await cache.get_chat_history(
            chat_id=chat_id,
            limit=limit,
            offset=offset,
            include_research=include_research_tasks,
        )

        if cached_history:
            logger.debug(
                "Returning cached chat history",
                chat_id=chat_id,
                limit=limit,
                offset=offset,
            )
            return ChatHistoryResponse(**cached_history)

        # Verify access using HistoryService
        chat_session = await HistoryService.get_session_with_permission_check(
            chat_id, user_id
        )

        # Query messages with filters
        query = ChatMessageModel.find(ChatMessageModel.chat_id == chat_id)

        if not include_system:
            query = query.find(ChatMessageModel.role != MessageRole.SYSTEM)

        # Get total count
        total_count = await query.count()

        # Get messages with pagination (newest first)
        messages_docs = (
            await query.sort(-ChatMessageModel.created_at)
            .skip(offset)
            .limit(limit)
            .to_list()
        )

        # Get research tasks for this chat if requested
        research_tasks = {}
        if include_research_tasks:
            from ....models.task import Task as TaskModel

            # Find all research tasks associated with this chat
            task_docs = await TaskModel.find(
                TaskModel.chat_id == chat_id, TaskModel.task_type == "deep_research"
            ).to_list()

            # Index by task_id for fast lookup
            research_tasks = {
                str(task.id): {
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
                }
                for task in task_docs
            }

        # Convert to response schema with research task enrichment
        messages = []
        for msg in messages_docs:
            message_data = ChatMessage(
                id=msg.id,
                chat_id=msg.chat_id,
                role=msg.role,
                content=msg.content,
                status=msg.status,
                created_at=msg.created_at,
                updated_at=msg.updated_at,
                metadata=msg.metadata,
                model=msg.model,
                tokens=msg.tokens,
                latency_ms=msg.latency_ms,
                task_id=msg.task_id,
            )

            # Enrich with research task data if available
            if msg.task_id and str(msg.task_id) in research_tasks:
                # Add research task data to metadata
                if not message_data.metadata:
                    message_data.metadata = {}
                message_data.metadata["research_task"] = research_tasks[
                    str(msg.task_id)
                ]

            messages.append(message_data)

        has_more = offset + len(messages) < total_count

        logger.info(
            "Retrieved chat history with research tasks",
            chat_id=chat_id,
            message_count=len(messages),
            research_tasks_count=len(research_tasks),
            total_count=total_count,
            user_id=user_id,
        )

        response_data = {
            "chat_id": chat_id,
            "messages": [msg.model_dump(mode="json") for msg in messages],
            "total_count": total_count,
            "has_more": has_more,
        }

        # Cache the response for performance
        await cache.set_chat_history(
            chat_id=chat_id,
            data=response_data,
            limit=limit,
            offset=offset,
            include_research=include_research_tasks,
        )

        return ChatHistoryResponse(**response_data)

    except NotFoundError:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error retrieving chat history",
            error=str(exc),
            exc_type=type(exc).__name__,
            chat_id=chat_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat history",
        )
