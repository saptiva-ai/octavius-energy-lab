"""
Chat Stream Producer - Encapsulates LLM streaming producer logic.

Domain-agnostic streaming producer. Handles:
- Metadata event emission
- Message context building with memory system
- Token budget management
- Standard LLM synthesis with RAG context (document-grounded)
- True streaming mode with SaptivaStreamer
"""

import json
from asyncio import CancelledError, Queue
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import structlog

from ...core.env_utils import entero_de_env
from ...domain import ChatContext
from ...models.chat import ChatMessage, ChatSession
from ...services.chat_service import ChatService
from ...services.empty_response_handler import (
    EmptyResponseScenario,
    ensure_non_empty_content,
)
from ...services.saptiva_client import SaptivaClient
from .chunk_emitter import ChunkEmitter
from .saptiva_streamer import SaptivaStreamer
from .token_budget import TokenBudgetManager

logger = structlog.get_logger(__name__)


@dataclass
class ProducerConfig:
    """Configuration for the ChatStreamProducer."""

    # Ventana de contexto del modelo. El 8192 histórico era el de Saptiva
    # Turbo; los modelos de InferNode reportan 256k en `/v1/models`. Como el
    # presupuesto de respuesta se calcula restando el prompt a este número, un
    # límite corto ahoga la respuesta: con el contexto real del chat quedaban
    # 1200 tokens, y los modelos de razonamiento necesitan más solo para
    # pensar (qwen usó 919 en una narración corta) y devolvían vacío.
    model_limit: int = field(
        default_factory=lambda: entero_de_env("CHAT_MODEL_CONTEXT_LIMIT", 8192)
    )
    min_tokens: int = field(
        default_factory=lambda: entero_de_env("CHAT_MIN_RESPONSE_TOKENS", 500)
    )
    default_max_tokens: int = field(
        default_factory=lambda: entero_de_env("CHAT_MAX_RESPONSE_TOKENS", 3000)
    )


@dataclass
class ProducerResult:
    """Result of producer execution."""

    full_response: str = ""
    error: Optional[Exception] = None
    completed: bool = False
    path_taken: str = ""  # "rag_context", "rag_context_streaming", "streaming"
    # AnalyticsResponse crudo del plugin de dominio, si el function-calling
    # nativo ejecutó una tool en este turno (ver FunctionCallingOrchestrator).
    retail_analytics: Optional[Dict[str, Any]] = None


@dataclass
class ProducerContext:
    """All context needed by the producer."""

    event_queue: Queue
    context: ChatContext
    chat_session: ChatSession
    user_message: ChatMessage
    saptiva_client: SaptivaClient
    chat_service: ChatService
    system_prompt: str
    model_params: Dict[str, Any]
    document_context: Optional[str] = None


class ChatStreamProducer:
    """
    Producer task for LLM streaming with backpressure support.

    Reads chunks from Saptiva and puts them in queue.
    If queue is full (slow consumer), put() will block, providing backpressure.
    This prevents unbounded memory growth on the server.
    """

    def __init__(self, config: Optional[ProducerConfig] = None):
        """Initialize producer with optional configuration."""
        self.config = config or ProducerConfig()

    async def produce(self, ctx: ProducerContext) -> ProducerResult:
        """
        Execute the producer logic.

        Args:
            ctx: All context needed for production

        Returns:
            ProducerResult with full_response, error, and path_taken
        """
        result = ProducerResult()

        try:
            logger.info(
                "Starting Saptiva stream (producer)",
                model=ctx.context.model,
                user_id=ctx.context.user_id,
                has_document_context=bool(ctx.document_context),
            )

            # Send metadata event first
            await self._emit_metadata_event(ctx)

            # Build message context with memory system
            messages_for_api = await ctx.chat_service.build_message_context_with_memory(
                chat_session=ctx.chat_session,
                current_message=ctx.context.message,
                system_prompt=ctx.system_prompt,
            )

            logger.info(
                "Chat context built with memory system",
                total_messages=len(messages_for_api),
                session_id=str(ctx.chat_session.id),
                memory_enabled=getattr(
                    ctx.chat_service.settings, "memory_enabled", False
                ),
            )

            # Native function-calling (opt-in): el LLM decide llamar las tools
            # del plugin de dominio y el path narra con grounding real. El paso
            # completo (condición de activación, avisos anti-alucinación) está
            # compartido con la ruta no-streaming en `function_calling`.
            from .function_calling import (
                anexo_de_ambito,
                augmentar_con_tools_de_dominio,
                modelo_para_narrar,
                narracion_directa_del_plugin,
            )

            mensajes_pre_tools = messages_for_api
            elegidas: list[dict[str, Any]] = []

            async def al_elegir(tools: list[dict[str, Any]]) -> None:
                elegidas[:] = tools
                await self._emit_status_event(ctx, tools)

            (
                messages_for_api,
                tool_result,
                _fc_status,
            ) = await augmentar_con_tools_de_dominio(
                settings=ctx.chat_service.settings,
                saptiva_client=ctx.saptiva_client,
                messages=messages_for_api,
                model=ctx.context.model,
                request_tools=getattr(ctx.context, "tools_enabled", None),
                session_tools=getattr(ctx.chat_session, "tools_enabled", None),
                # Perfil del usuario → ámbito en cada tool de datos (T3).
                user_id=getattr(ctx.context, "user_id", None),
                al_elegir=al_elegir,
                # Memoria de la conversación en el plugin (lo mostrado).
                conversacion_id=str(ctx.chat_session.id),
            )
            # Los datos ya están: la burbuja pasa a "redactando" con el mismo
            # tema mientras llega el primer texto.
            await self._emit_status_event(ctx, elegidas, fase="redactando")
            if tool_result:
                result.retail_analytics = tool_result

            # Narración directa: con UNA tool de datos y `response_text`
            # confiable del contrato genérico, re-narrar con el LLM solo
            # parafrasea las mismas cifras (~15-30 s extra con modelos
            # razonadores — card latencia-chat-retail-prediccion). El texto
            # del plugin se emite como chunks normales.
            texto_directo = narracion_directa_del_plugin(
                mensajes_pre_tools,
                messages_for_api,
                tool_result,
                settings=ctx.chat_service.settings,
            )
            if texto_directo is not None:
                logger.info(
                    "Producer direct plugin narration",
                    response_length=len(texto_directo),
                )
                await ChunkEmitter.emit_chunks(
                    text=texto_directo, queue=ctx.event_queue
                )
                result.full_response = texto_directo
                result.path_taken = "tool_direct"
            else:
                # Prepare token budget
                token_budget = TokenBudgetManager.prepare_messages_for_api(
                    messages=messages_for_api,
                    model_limit=self.config.model_limit,
                    min_tokens=self.config.min_tokens,
                    max_tokens=ctx.model_params.get(
                        "max_tokens", self.config.default_max_tokens
                    ),
                )
                dynamic_max_tokens = token_budget.max_tokens

                has_rag_context = bool(ctx.context.document_ids) or bool(
                    ctx.document_context
                )

                logger.info(
                    "Producer response path",
                    has_rag_context=has_rag_context,
                    document_count=(
                        len(ctx.context.document_ids) if ctx.context.document_ids else 0
                    ),
                )

                # Un turno que ya trae datos de las tools solo se redacta: con
                # un modelo dedicado sin thinking evita la respuesta vacía y
                # baja la latencia (mismo criterio que el paso decide).
                modelo_narracion = modelo_para_narrar(
                    ctx.chat_service.settings, ctx.context.model, _fc_status
                )

                # Execute appropriate response path
                if has_rag_context:
                    result = await self._handle_rag_context_path(
                        ctx,
                        result,
                        messages_for_api,
                        dynamic_max_tokens,
                        modelo=modelo_narracion,
                    )
                else:
                    result = await self._handle_streaming_path(
                        ctx,
                        result,
                        messages_for_api,
                        dynamic_max_tokens,
                        modelo=modelo_narracion,
                    )

            # Línea de ámbito del plugin, por código y tras la narración, en
            # las dos rutas (directa y LLM); una sola vez.
            anexo = anexo_de_ambito(result.full_response or "", tool_result)
            if anexo:
                await ChunkEmitter.emit_chunks(text=anexo, queue=ctx.event_queue)
                result.full_response = f"{result.full_response or ''}{anexo}"

            # Signal end of stream
            await ctx.event_queue.put(None)
            result.completed = True

            logger.info(
                "Producer completed successfully",
                response_length=len(result.full_response),
                path_taken=result.path_taken,
            )

        except CancelledError:
            logger.info("Producer cancelled by consumer")
            raise
        except Exception as e:
            logger.error("Producer error", error=str(e), exc_type=type(e).__name__)
            result.error = e
            # Signal error to consumer
            await ctx.event_queue.put(None)

        return result

    async def _emit_metadata_event(self, ctx: ProducerContext) -> None:
        """Emit the initial metadata SSE event."""
        await ctx.event_queue.put(
            {
                "event": "meta",
                "data": json.dumps(
                    {
                        "chat_id": str(ctx.chat_session.id),
                        "user_message_id": str(ctx.user_message.id),
                        "model": ctx.context.model,
                    }
                ),
            }
        )

    async def _emit_status_event(
        self,
        ctx: ProducerContext,
        tools: list[dict[str, Any]],
        fase: str = "consultando",
    ) -> None:
        """Avisa en qué paso va el turno: "consultando" cuando el decide eligió
        tools (antes de ejecutarlas) y "redactando" cuando ya hay datos. La web
        muestra los mensajes de ese paso, en orden, con el tema de la tool."""
        await ctx.event_queue.put(
            {
                "event": "status",
                "data": json.dumps({"fase": fase, "tools": tools}),
            }
        )

    async def _handle_rag_context_path(
        self,
        ctx: ProducerContext,
        result: ProducerResult,
        messages_for_api: list,
        dynamic_max_tokens: int,
        modelo: str | None = None,
    ) -> ProducerResult:
        """
        Handle LLM synthesis with RAG context.

        Prefer true streaming for lower TTFB, with non-streaming fallback
        when upstream streaming is unavailable.

        `modelo` permite narrar con el modelo dedicado cuando el turno ya trae
        resultados de tools; None conserva el de la sesión.
        """
        modelo = modelo or ctx.context.model
        # Prefer true streaming first to reduce time-to-first-token.
        streamed_chunk_count = 0
        streamed_response = ""
        try:
            async for chunk in ctx.saptiva_client.chat_completion_stream(
                messages=messages_for_api,
                model=modelo,
                temperature=ctx.model_params.get(
                    "temperature", ctx.context.temperature
                ),
                max_tokens=dynamic_max_tokens,
            ):
                content = SaptivaStreamer.extract_chunk_content(chunk)
                if content:
                    await ctx.event_queue.put(ChunkEmitter.build_chunk_event(content))
                    streamed_response += content
                    streamed_chunk_count += 1
        except Exception as stream_err:
            logger.warning(
                "RAG streaming unavailable, falling back to non-streaming",
                error=str(stream_err),
                error_type=type(stream_err).__name__,
            )
            streamed_chunk_count = 0
            streamed_response = ""

        if streamed_chunk_count > 0:
            result.full_response = ensure_non_empty_content(
                streamed_response,
                scenario=EmptyResponseScenario.API_EMPTY_CONTENT,
                model=ctx.context.model,
                has_documents=bool(ctx.context.document_ids),
                document_count=(
                    len(ctx.context.document_ids) if ctx.context.document_ids else 0
                ),
                user_id=ctx.context.user_id,
            )
            logger.info(
                "RAG streaming response extracted",
                chunk_count=streamed_chunk_count,
                response_length=len(result.full_response),
            )
            result.path_taken = "rag_context_streaming"
            return result

        response = await ctx.saptiva_client.chat_completion(
            messages=messages_for_api,
            model=modelo,
            temperature=ctx.model_params.get("temperature", ctx.context.temperature),
            max_tokens=dynamic_max_tokens,
        )

        # Extract content from response
        response_content, has_reasoning = SaptivaStreamer.extract_content_from_response(
            response
        )

        # Ensure non-empty response
        response_content = ensure_non_empty_content(
            response_content,
            scenario=EmptyResponseScenario.API_EMPTY_CONTENT,
            model=ctx.context.model,
            has_documents=bool(ctx.context.document_ids),
            document_count=(
                len(ctx.context.document_ids) if ctx.context.document_ids else 0
            ),
            user_id=ctx.context.user_id,
        )

        result.full_response = response_content

        logger.info(
            "Non-streaming response extracted",
            response_length=len(result.full_response),
            response_preview=(
                result.full_response[:100] if result.full_response else "(empty)"
            ),
            has_reasoning=has_reasoning,
        )

        # Emit as chunks for uniform frontend handling
        await ChunkEmitter.emit_chunks(
            text=result.full_response,
            queue=ctx.event_queue,
            log_progress=True,
        )

        result.path_taken = "rag_context"
        return result

    async def _handle_streaming_path(
        self,
        ctx: ProducerContext,
        result: ProducerResult,
        messages_for_api: list,
        dynamic_max_tokens: int,
        modelo: str | None = None,
    ) -> ProducerResult:
        """
        Handle true streaming mode with SaptivaStreamer.

        Streams chunks directly from LLM to queue with backpressure.

        `modelo` permite narrar con el modelo dedicado cuando el turno ya trae
        resultados de tools; None conserva el de la sesión.
        """
        modelo = modelo or ctx.context.model
        full_response = ""

        async for chunk in ctx.saptiva_client.chat_completion_stream(
            messages=messages_for_api,
            model=modelo,
            temperature=ctx.model_params.get("temperature", ctx.context.temperature),
            max_tokens=dynamic_max_tokens,
        ):
            # Use SaptivaStreamer for normalized chunk extraction
            content = SaptivaStreamer.extract_chunk_content(chunk)

            if content:
                # Backpressure: this blocks if queue is full (maxsize=10)
                await ctx.event_queue.put(ChunkEmitter.build_chunk_event(content))
                full_response += content

        result.full_response = full_response
        result.path_taken = "streaming"
        return result
