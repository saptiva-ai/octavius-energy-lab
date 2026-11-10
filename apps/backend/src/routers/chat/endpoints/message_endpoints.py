"""
Message Endpoints - HTTP endpoints for chat message operations.

This module contains endpoints related to sending and processing chat messages.

Endpoints:
    POST /chat - Send chat message (streaming or non-streaming)
    POST /chat/{chat_id}/escalate - Escalate conversation to research mode

Responsibilities:
    - Handle HTTP request/response for chat messages
    - Delegate to handlers (streaming or message handlers)
    - Build responses with ChatResponseBuilder
"""

import time
from datetime import datetime
from typing import Any

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sse_starlette.sse import EventSourceResponse

from ....core.config import Settings, get_settings
from ....core.dependencies import get_chat_service
from ....core.redis_cache import get_redis_cache
from ....domain import ChatContext, ChatResponseBuilder
from ....domain.message_handlers import create_handler_chain
from ....schemas.chat import ChatRequest
from ....schemas.common import ApiResponse
from ....services.chat_helpers import build_chat_context
from ....services.chat_service import ChatService
from ....services.session_context_manager import SessionContextManager
from ....services.tool_execution_service import ToolExecutionService
from ..handlers import StreamingHandler

logger = structlog.get_logger(__name__)
router = APIRouter()

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

# El navegador pide gzip y el servidor de Next comprime las respuestas de su
# proxy (/api/* -> backend): el gzip retenía el SSE completo y `status` y el
# texto llegaban juntos al final (medido 2026-10-21 con la web 1.0.17).
# `no-transform` hace que la compresión lo deje pasar evento por evento.
SSE_HEADERS = {"Cache-Control": "no-store, no-transform"}


def respuesta_sse(eventos: Any) -> EventSourceResponse:
    """Respuesta SSE del chat que nadie en el camino comprime ni acumula."""
    return EventSourceResponse(
        eventos, media_type="text/event-stream", headers=SSE_HEADERS
    )


@router.post("/chat", tags=["chat"])
async def send_chat_message(
    request: ChatRequest,
    http_request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Send a chat message and get AI response.

    Refactored using:
    - ChatContext dataclass for type-safe request encapsulation
    - Chain of Responsibility for message handling
    - Strategy Pattern for pluggable chat handlers
    - Builder Pattern for declarative response construction

    Handles both new conversations and continuing existing ones.
    Supports streaming via SSE when request.stream = True.
    """
    user_id = getattr(http_request.state, "user_id", "mock-user-id")

    # ========================================================================
    # STREAMING PATH
    # ========================================================================
    if getattr(request, "stream", False):
        # Check Accept header for SSE streaming
        accept_header = http_request.headers.get("accept", "")
        if "text/event-stream" in accept_header:
            streaming_handler = StreamingHandler(settings, chat_service=chat_service)
            return respuesta_sse(
                streaming_handler.handle_stream(request, user_id, background_tasks)
            )
        else:
            # If the client did not request SSE, fall back to non-streaming JSON
            request.stream = False

    # ========================================================================
    # NON-STREAMING PATH
    # ========================================================================
    start_time = time.time()
    response.headers.update(NO_STORE_HEADERS)

    try:
        # 1. Build context
        context = build_chat_context(request, user_id, settings)

        logger.info(
            "Processing chat request",
            request_id=context.request_id,
            user_id=context.user_id,
            model=context.model,
            has_documents=bool(context.document_ids),
        )

        # 2. Initialize cache (chat_service injected via Depends)
        cache = await get_redis_cache()

        # 3. Get or create session
        chat_session = await chat_service.get_or_create_session(
            chat_id=context.chat_id,
            user_id=context.user_id,
            first_message=context.message,
            tools_enabled=context.tools_enabled,
        )

        context = context.with_session(chat_session.id)

        # 4. Prepare session context (files)
        request_file_ids = list((request.file_ids or []) + (request.document_ids or []))

        current_file_ids = await SessionContextManager.prepare_session_context(
            chat_session=chat_session,
            request_file_ids=request_file_ids,
            user_id=user_id,
            redis_cache=cache,
            request_id=context.request_id,
        )

        # 🚨 CRITICAL FIX: Prevent Stale Read after file adoption
        # Even though we just adopted files and committed to DB, MongoDB read replicas
        # may not reflect the write yet (eventual consistency).
        # SOLUTION: Use request_file_ids directly (in-memory) instead of trusting DB
        effective_document_ids = current_file_ids  # Start with what DB says

        if request_file_ids and len(request_file_ids) > 0:
            # FORCE MERGE: Ensure files from request are ALWAYS in context
            # This bypasses DB latency/stale reads
            effective_document_ids = list(
                set(effective_document_ids + request_file_ids)
            )

            logger.info(
                "🔒 [STALE READ FIX] Using request file_ids directly in context",
                request_file_ids=request_file_ids,
                db_file_ids=current_file_ids,
                effective_file_ids=effective_document_ids,
                nonce=context.request_id[:8],
            )

        # Update context with resolved file IDs
        # BUGFIX: Always update context, even if current_file_ids is empty list
        # Empty list [] is falsy in Python, which prevented context update
        context = ChatContext(
            user_id=context.user_id,
            request_id=context.request_id,
            timestamp=context.timestamp,
            chat_id=context.chat_id,
            session_id=context.session_id,
            message=context.message,
            context=context.context,
            document_ids=effective_document_ids,  # ✅ USE IN-MEMORY FORCED LIST
            tool_results={},  # Will be populated below
            model=context.model,
            tools_enabled=context.tools_enabled,
            stream=context.stream,
            temperature=context.temperature,
            max_tokens=context.max_tokens,
            kill_switch_active=context.kill_switch_active,
        )

        # 4.5. Invoke MCP tools before LLM (NEW: Phase 2 MCP integration)
        tool_results = await ToolExecutionService.invoke_relevant_tools(
            context, user_id
        )

        if tool_results:
            # Update context with tool results for LLM injection
            context = ChatContext(
                user_id=context.user_id,
                request_id=context.request_id,
                timestamp=context.timestamp,
                chat_id=context.chat_id,
                session_id=context.session_id,
                message=context.message,
                context=context.context,
                document_ids=context.document_ids,
                tool_results=tool_results,
                model=context.model,
                tools_enabled=context.tools_enabled,
                stream=context.stream,
                temperature=context.temperature,
                max_tokens=context.max_tokens,
                kill_switch_active=context.kill_switch_active,
            )
            logger.info(
                "Tool results added to context",
                request_id=context.request_id,
                tool_count=len(tool_results),
            )

        # 5. Add user message
        user_message_metadata = request.metadata.copy() if request.metadata else {}
        if effective_document_ids:
            user_message_metadata["file_ids"] = effective_document_ids

        user_message = await chat_service.add_user_message(
            chat_session=chat_session,
            content=context.message,
            metadata=user_message_metadata if user_message_metadata else None,
        )

        # 6. Delegate to handler chain (Chain of Responsibility Pattern)
        handler_chain = create_handler_chain()
        handler_result = await handler_chain.handle(
            context=context,
            chat_service=chat_service,
            user_id=user_id,
            chat_session=chat_session,
            user_message=user_message,
            current_file_ids=effective_document_ids,  # ✅ Use in-memory forced list
        )

        if handler_result:
            # Handler processed the message successfully
            logger.info(
                "Message processed by handler chain",
                strategy=handler_result.strategy_used,
                processing_time_ms=handler_result.processing_time_ms,
            )

            # BUGFIX: Save assistant message to database
            # Without this, LLM responses are not persisted in chat history
            # Extract decision_metadata and tool_invocations
            decision_metadata = (
                handler_result.metadata.decision_metadata
                if handler_result.metadata
                else None
            )
            tool_invocations = (
                decision_metadata.get("tool_invocations", [])
                if decision_metadata
                else []
            )

            logger.info(
                "About to save assistant message with metadata",
                decision_metadata=decision_metadata,
                tool_invocations=tool_invocations,
                has_tool_invocations=len(tool_invocations) > 0,
            )

            # Build message metadata
            message_metadata = {
                "strategy_used": handler_result.strategy_used,
                "processing_time_ms": handler_result.processing_time_ms,
                "tokens_used": (
                    handler_result.metadata.tokens_used
                    if handler_result.metadata
                    else None
                ),
                "decision_metadata": decision_metadata,
                "tool_invocations": tool_invocations,
            }

            # Paridad con streaming: el AnalyticsResponse del function-calling
            # nativo se persiste al nivel raíz de la metadata del mensaje
            # (el frontend lee metadata.retail_analytics al recargar el hilo).
            if decision_metadata and decision_metadata.get("retail_analytics"):
                message_metadata["retail_analytics"] = decision_metadata[
                    "retail_analytics"
                ]

            # Calculate latency for dashboard metrics
            latency_ms = int((time.time() - start_time) * 1000)
            message_metadata["latency_ms"] = latency_ms  # For dashboard queries

            assistant_message = await chat_service.add_assistant_message(
                chat_session=chat_session,
                content=handler_result.sanitized_content or handler_result.content,
                model=context.model,
                metadata=message_metadata,
                latency_ms=latency_ms,
            )

            logger.info(
                "Assistant message saved to database",
                message_id=str(assistant_message.id),
                session_id=str(chat_session.id),
                content_length=len(handler_result.content),
            )

            # Invalidate caches
            await cache.invalidate_chat_history(chat_session.id)

            # Build response
            response_builder = (
                ChatResponseBuilder()
                .from_processing_result(handler_result)
                .with_metadata("processing_time_ms", (time.time() - start_time) * 1000)
                .with_metadata("assistant_message_id", str(assistant_message.id))
            )

            return response_builder.build()

        # Fallback (should not happen with StandardChatHandler)
        logger.warning(
            "No handler processed the message - this should not happen",
            message=context.message[:50],
            session_id=context.session_id,
        )

        # Legacy strategy execution path (fallback)
        # ... (rest of original implementation if needed)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No handler could process the message",
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Chat request failed",
            error=str(exc),
            exc_type=type(exc).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat processing failed: {str(exc)}",
        )


@router.post("/chat/{chat_id}/escalate", response_model=ApiResponse, tags=["chat"])
async def escalate_to_research(
    chat_id: str,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Escalate conversation to deep research mode.

    BE-6: Deep research escalation endpoint.
    Triggers web search + LLM synthesis for complex queries.

    Args:
        chat_id: Chat session ID to escalate
        http_request: HTTP request with user_id in state
        settings: Application settings

    Returns:
        ApiResponse with success/failure status
    """
    user_id = getattr(http_request.state, "user_id", "mock-user-id")

    logger.info(
        "Research escalation requested",
        chat_id=chat_id,
        user_id=user_id,
        kill_switch=settings.deep_research_kill_switch,
    )

    # BE-6: Check kill switch
    if settings.deep_research_kill_switch:
        logger.warning(
            "Research escalation blocked by kill switch",
            chat_id=chat_id,
            user_id=user_id,
        )
        return ApiResponse(
            success=False,
            message="Deep research is currently disabled.",
            data={"kill_switch_active": True},
        )

    try:
        # Get session (chat_service injected via Depends)
        chat_session = await chat_service.get_session(chat_id, user_id)

        if not chat_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {chat_id} not found",
            )

        # Trigger research (implementation depends on research coordinator)
        # For now, just mark the session
        await chat_session.update(
            {"$set": {"research_escalated": True, "updated_at": datetime.utcnow()}}
        )

        logger.info("Research escalation successful", chat_id=chat_id, user_id=user_id)

        return ApiResponse(
            success=True,
            message="Conversation escalated to research mode",
            data={"chat_id": chat_id, "research_mode": True},
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Research escalation failed",
            chat_id=chat_id,
            error=str(exc),
            exc_type=type(exc).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Escalation failed: {str(exc)}",
        )
