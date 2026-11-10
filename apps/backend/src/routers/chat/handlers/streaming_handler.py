"""
Streaming Handler - SSE (Server-Sent Events) chat response handler.

This module handles streaming responses for chat messages,
following Single Responsibility Principle.

Responsibilities:
    - Stream chat responses via SSE
    - Handle document context for streaming
    - Manage streaming-specific errors
    - Save streamed responses to database
"""

import time
from asyncio import Queue, create_task
from typing import Any, AsyncGenerator, Dict, Optional

import structlog
from fastapi import BackgroundTasks

from ....core.config import Settings
from ....core.redis_cache import get_redis_cache
from ....domain import ChatContext
from ....schemas.chat import ChatRequest
from ....services.audit_mcp_client import audit_document_via_mcp
from ....services.chat_helpers import build_chat_context
from ....services.chat_service import ChatService
from ....services.saptiva_client import get_saptiva_client
from ....services.session_context_manager import SessionContextManager
from ....services.streaming import (
    AuditDocumentResolver,
    AuditResponseBuilder,
    ChatStreamProducer,
    DocumentContextBuilder,
    FileIngestionService,
    FinalizerContext,
    MessagePersistenceService,
    ProducerContext,
    StreamingErrorLogger,
    StreamResponseFinalizer,
    SystemPromptBuilder,
)
from ....services.tool_execution_service import ToolExecutionService

logger = structlog.get_logger(__name__)


# REFACTOR-001: 14 services extracted to services/streaming/
# See services/streaming/__init__.py for full service catalog


class StreamingHandler:
    """
    Handles streaming SSE responses for chat messages.

    This class encapsulates all streaming-specific logic,
    following Single Responsibility Principle.
    """

    def __init__(
        self,
        settings: Settings,
        chat_service: Optional["ChatService"] = None,
    ):
        """
        Initialize streaming handler.

        Args:
            settings: Application settings
            chat_service: Optional ChatService instance. If not provided,
                creates a new instance. Pass an instance for dependency
                injection in tests.
        """
        self.settings = settings
        self._chat_service = chat_service

    async def handle_stream(
        self, request: ChatRequest, user_id: str, background_tasks: BackgroundTasks
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Handle chat message with streaming response.
        """
        try:
            context = build_chat_context(request, user_id, self.settings)

            logger.info(
                "Streaming chat request",
                request_id=context.request_id,
                model=context.model,
            )

            # Initialize services (use injected or create new)
            chat_service = self._chat_service or ChatService(self.settings)
            cache = await get_redis_cache()

            # Get or create session
            chat_session = await chat_service.get_or_create_session(
                chat_id=context.chat_id,
                user_id=context.user_id,
                first_message=context.message,
                tools_enabled=context.tools_enabled,
            )

            context = context.with_session(chat_session.id)

            # Prepare session context (files)
            request_file_ids = list(
                (request.file_ids or []) + (request.document_ids or [])
            )

            current_file_ids = await SessionContextManager.prepare_session_context(
                chat_session=chat_session,
                request_file_ids=request_file_ids,
                user_id=user_id,
                redis_cache=cache,
                request_id=context.request_id,
            )

            # REFACTOR-001 Phase 12: Use ChatContext.with_document_ids()
            if current_file_ids:
                context = context.with_document_ids(current_file_ids)

                # REFACTOR-001 Phase 7: Use FileIngestionService for document ingestion
                await FileIngestionService.ingest_files_if_needed(
                    session_id=str(chat_session.id),
                    file_ids=current_file_ids,
                    background_tasks=background_tasks,
                )

            # Add user message
            user_message_metadata = request.metadata.copy() if request.metadata else {}
            if current_file_ids:
                user_message_metadata["file_ids"] = current_file_ids

            user_message = await chat_service.add_user_message(
                chat_session=chat_session,
                content=context.message,
                metadata=user_message_metadata if user_message_metadata else None,
            )

            # Check for audit command
            if context.message.strip().startswith("Auditar archivo:"):
                async for event in self._stream_audit_response(
                    chat_service, chat_session, context, user_message
                ):
                    yield event
                return

            # Stream chat response
            async for event in self._stream_chat_response(
                context,
                chat_service,
                chat_session,
                cache,
                user_message,
            ):
                yield event

        except Exception as exc:
            # REFACTOR-001 Phase 10: Use StreamingErrorLogger for error handling
            StreamingErrorLogger.log_from_request(
                exc=exc,
                user_id=user_id,
                request=request,
                context=context if "context" in locals() else None,
            )

            yield MessagePersistenceService.build_error_event(
                error_message=str(exc),
                error_type=type(exc).__name__,
                recoverable=False,
            )

    async def _stream_audit_response(
        self,
        chat_service: ChatService,
        chat_session,
        context: ChatContext,
        user_message,
    ) -> AsyncGenerator[dict, None]:
        """
        Stream audit validation progress in real-time.

        Args:
            chat_service: ChatService instance
            chat_session: ChatSession model
            context: ChatContext with request data
            user_message: Saved user message model

        Yields:
            SSE events for audit progress
        """
        logger.info("Audit command", user_id=context.user_id)

        # REFACTOR-001 Phase 7: Use AuditDocumentResolver
        resolved, resolution_error = await AuditDocumentResolver.resolve(
            message=context.message,
            document_ids=context.document_ids,
        )

        if resolution_error:
            error_msg = f"❌ {resolution_error.error_message}"
            await chat_service.add_assistant_message(
                chat_session=chat_session,
                content=error_msg,
                model=context.model,
                metadata={"error": resolution_error.error_code},
            )
            yield AuditResponseBuilder.build_error_event(
                error_type=resolution_error.error_code,
                message=error_msg,
            )
            return

        document = resolved.document
        pdf_path = resolved.pdf_path
        is_temp = resolved.is_temp

        # REFACTOR-001: Use AuditResponseBuilder for SSE events
        yield AuditResponseBuilder.build_meta_event(
            chat_id=str(chat_session.id),
            user_message_id=str(user_message.id),
            model=context.model,
            document_id=str(document.id),
            filename=document.filename,
        )

        accumulated_content = []
        validation_complete_event = None

        try:
            # Yield initial progress message
            start_content = AuditResponseBuilder.build_start_event(document.filename)
            accumulated_content.append(start_content)
            yield AuditResponseBuilder.build_chunk_event(
                content=start_content,
                audit_event={"type": "validation_start", "filename": document.filename},
            )

            # Call MCP auditor service (non-streaming)
            mcp_result = await audit_document_via_mcp(
                file_path=str(pdf_path),
                policy_id="auto",
                client_name=None,
                enable_disclaimer=True,
                enable_format=True,
                enable_typography=True,
                enable_grammar=True,
                enable_logo=True,
                enable_color_palette=True,
                enable_entity_consistency=True,
                enable_semantic_consistency=True,
            )

            # REFACTOR-001 Phase 5.4: Use AuditResponseBuilder for response building
            validation_complete_event = (
                AuditResponseBuilder.build_validation_complete_event(
                    mcp_result=mcp_result,
                    filename=document.filename,
                )
            )

            # Build result content using AuditResponseBuilder
            summary = AuditResponseBuilder.extract_summary(mcp_result)
            content = AuditResponseBuilder.build_result_content(
                summary=summary,
                executive_summary_md=mcp_result.get("executive_summary_markdown"),
            )

            accumulated_content.append(content)

            # Yield result chunk
            yield AuditResponseBuilder.build_chunk_event(
                content=content,
                audit_event=validation_complete_event,
            )

            # REFACTOR-001 Phase 11: Use AuditResponseBuilder for persistence
            await AuditResponseBuilder.persist_validation_report(
                document_id=str(document.id),
                user_id=str(document.user_id),
                mcp_result=mcp_result,
                validation_event=validation_complete_event,
                summary=summary,
            )

            # Build audit artifact and message metadata using AuditResponseBuilder
            audit_artifact = AuditResponseBuilder.build_audit_artifact(
                filename=document.filename,
                validation_event=validation_complete_event,
                findings=mcp_result.get("top_findings", []),
            )

            full_content = "".join(accumulated_content)
            message_metadata = AuditResponseBuilder.build_message_metadata(
                document_id=str(document.id),
                filename=document.filename,
                validation_event=validation_complete_event,
                artifact=audit_artifact,
            )

            assistant_message = await chat_service.add_assistant_message(
                chat_session=chat_session,
                content=full_content,
                model=context.model,
                metadata=message_metadata,
            )
            logger.info("Audit message saved", message_id=str(assistant_message.id))

            # Yield done event using AuditResponseBuilder
            yield AuditResponseBuilder.build_done_event(
                message_id=str(assistant_message.id),
                content=full_content,
                model=context.model,
                chat_id=str(chat_session.id),
                metadata=message_metadata,
                artifact=audit_artifact,
            )

        except Exception as exc:
            logger.error("Audit streaming failed", error=str(exc), exc_info=True)

            error_msg = f"❌ Error durante la auditoría: {str(exc)}"
            await chat_service.add_assistant_message(
                chat_session=chat_session,
                content=error_msg,
                model=context.model,
                metadata={"error": "audit_execution_failed"},
            )

            yield AuditResponseBuilder.build_error_event(
                error_type="audit_execution_failed",
                message=error_msg,
                details=str(exc),
            )

        finally:
            # Clean up temporary PDF file
            if is_temp and pdf_path.exists():
                pdf_path.unlink()

    async def _stream_chat_response(
        self,
        context: ChatContext,
        chat_service: ChatService,
        chat_session,
        cache,
        user_message,
    ) -> AsyncGenerator[dict, None]:
        """
        Stream chat response from Saptiva API.

        Args:
            context: ChatContext with request data
            chat_service: ChatService instance
            chat_session: ChatSession model
            cache: Redis cache instance
            user_message: User message model with ID

        Yields:
            SSE events with message chunks and completion
        """
        # Capture start time for latency tracking (dashboard metrics)
        stream_start_time = time.perf_counter()

        # FIX-001: Wrap entire streaming logic in try-catch for proper error propagation
        try:
            # REFACTOR-001 Phase 2: Use DocumentContextBuilder service
            doc_context_builder = DocumentContextBuilder()
            document_context, doc_warnings = await doc_context_builder.build(
                document_ids=context.document_ids or [],
                session_id=context.session_id,
                user_id=context.user_id,
                question=context.message,
            )

            # Initialize Saptiva client (singleton managed async factory)
            saptiva_client = await get_saptiva_client()

            # REFACTOR-001 Phase 8: Use SystemPromptBuilder for prompt resolution
            prompt_result = SystemPromptBuilder.build(
                model=context.model,
                document_context=document_context,
                document_ids=context.document_ids,
                user_query=context.message,
            )
            system_prompt = prompt_result.system_prompt
            model_params = prompt_result.model_params

            logger.info(
                "System prompt resolved",
                model=context.model,
                has_docs=bool(document_context),
            )

            # Domain-tool augmentation por PRE-FETCH — solo cuando el function-calling
            # nativo está OFF (si está ON, el producer maneja las tools y no duplicamos).
            # retail_analytics_data viaja hasta el finally (mismo scope de función) para
            # adjuntarse a la metadata del mensaje/evento done — sin esto el frontend
            # solo veía el texto ya parafraseado por el LLM, nunca el dato estructurado.
            retail_analytics_data: Optional[Dict[str, Any]] = None
            if not getattr(self.settings, "retail_advisor_function_calling", False):
                try:
                    (
                        domain_block,
                        retail_analytics_data,
                    ) = await ToolExecutionService.build_domain_analytics_context(
                        context
                    )
                    if domain_block:
                        system_prompt = f"{system_prompt}\n\n{domain_block}"
                        logger.info("Domain analytics context injected into prompt")
                except Exception as domain_exc:  # noqa: BLE001 — no romper el stream
                    logger.warning(
                        "Domain tool augmentation failed", error=str(domain_exc)
                    )

            # ISSUE-004: Implement backpressure with producer-consumer pattern
            # Queue with maxsize=10 provides backpressure when client is slow
            event_queue: Queue = Queue(maxsize=10)

            # REFACTOR-001 Phase 6: Use ChatStreamProducer service
            producer = ChatStreamProducer()
            producer_context = ProducerContext(
                event_queue=event_queue,
                context=context,
                chat_session=chat_session,
                user_message=user_message,
                saptiva_client=saptiva_client,
                chat_service=chat_service,
                system_prompt=system_prompt,
                model_params=model_params,
                document_context=document_context,
            )

            producer_task = create_task(producer.produce(producer_context))

            try:
                # Consumer loop: yield events from queue
                while True:
                    event = await event_queue.get()

                    if event is None:  # End signal
                        break

                    yield event

            finally:
                # REFACTOR-001 Phase 9: Use StreamResponseFinalizer for cleanup
                finalizer_ctx = FinalizerContext(
                    context=context,
                    chat_session=chat_session,
                    chat_service=chat_service,
                    cache=cache,
                    doc_warnings=doc_warnings,
                    start_time=stream_start_time,  # For latency tracking
                    retail_analytics=retail_analytics_data,
                )

                result = await StreamResponseFinalizer.finalize(
                    producer_task=producer_task,
                    ctx=finalizer_ctx,
                )

                if result.error:
                    raise result.error

                # Emit fallback chunk if response was empty
                if result.fallback_chunk:
                    yield result.fallback_chunk

                yield result.done_event

        # FIX-001: Catch all streaming errors and propagate to frontend
        except Exception as stream_exc:
            logger.error(
                "Streaming chat failed",
                error=str(stream_exc),
                model=context.model,
                user_id=context.user_id,
                exc_info=True,
            )

            # REFACTOR-001 Phase 3: Use MessagePersistenceService for error handling
            error_content = MessagePersistenceService.build_error_content(stream_exc)
            error_metadata = MessagePersistenceService.build_error_metadata(stream_exc)
            try:
                await chat_service.add_assistant_message(
                    chat_session=chat_session,
                    content=error_content,
                    model=context.model,
                    metadata=error_metadata,
                )
            except Exception as save_exc:
                logger.error(
                    "Failed to save error message to database",
                    error=str(save_exc),
                    exc_info=True,
                )

            # Yield error event to frontend
            yield MessagePersistenceService.build_error_event(
                error_message=str(stream_exc),
                error_type=type(stream_exc).__name__,
                recoverable=True,
            )
