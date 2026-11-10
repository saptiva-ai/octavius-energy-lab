"""
Chat Service - Business Logic Layer

Extracts business logic from chat router for better separation of concerns.
Handles chat session management, message processing, and AI response generation.
"""

import json
import time
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import structlog
from fastapi import HTTPException, status
from pymongo.errors import PyMongoError

from ..core.config import Settings
from ..core.exceptions import ChatServiceError
from ..core.redis_cache import get_redis_cache
from ..core.telemetry import trace_span
from ..models.artifact import Artifact, ArtifactType
from ..models.chat import (
    ChatMessage as ChatMessageModel,
)
from ..models.chat import (
    ChatSession as ChatSessionModel,
)
from ..models.chat import (
    MessageRole,
)
from ..services.saptiva_client import SaptivaClient, build_payload
from ..services.tools import normalize_tools_state
from .memory.memory_service import get_memory_service

logger = structlog.get_logger(__name__)


def _narracion_agoto_presupuesto(response: Any) -> bool:
    """¿La respuesta vino VACÍA con `finish_reason=length`?

    Es la firma de un modelo de razonamiento (qwen3.6) que gastó TODO el
    max_tokens pensando sin emitir contenido visible (medido en vivo:
    completion_tokens == max_tokens y content == ""). Distinta de un vacío
    genuino (finish_reason=stop), que NO se reintenta.
    """
    choices = getattr(response, "choices", None) or []
    if not choices or not isinstance(choices[0], dict):
        return False
    message = choices[0].get("message") or {}
    if not isinstance(message, dict):
        return False
    content = (message.get("content") or "").strip()
    reasoning = (message.get("reasoning_content") or "").strip()
    agotado = choices[0].get("finish_reason") == "length"
    return not content and not reasoning and agotado


class ChatService:
    """Service for chat operations.

    Args:
        settings: Application settings
        saptiva_client: Optional SaptivaClient instance. If not provided,
            creates a new instance. Pass an instance for dependency injection
            in tests or when using FastAPI's Depends().
    """

    def __init__(
        self,
        settings: Settings,
        saptiva_client: Optional[SaptivaClient] = None,
    ):
        self.settings = settings
        self.saptiva_client = saptiva_client or SaptivaClient()

    async def _handle_tool_invocation(
        self,
        name: str,
        args: Dict[str, Any],
        user_id: str,
        chat_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Execute supported tool calls emitted by the LLM.

        Currently supports:
            - create_artifact: persists an artifact and returns minimal metadata.
        """
        if name != "create_artifact":
            return None

        try:
            title = args.get("title") or "Documento sin título"
            raw_type = args.get("type") or ArtifactType.MARKDOWN.value
            try:
                artifact_type = ArtifactType(raw_type)
            except ValueError:
                artifact_type = ArtifactType.MARKDOWN

            content = args.get("content", "")

            artifact = Artifact(
                user_id=user_id,
                chat_session_id=chat_id,
                title=title,
                type=artifact_type,
                content=content,
                versions=[],
            )
            artifact.add_version(content)
            await artifact.insert()

            return {
                "id": str(artifact.id),
                "title": artifact.title,
                "type": artifact.type.value,
            }
        except PyMongoError as db_err:
            # Database errors are logged but don't fail the main chat flow
            logger.warning(
                "Tool invocation failed (database)",
                tool=name,
                error=str(db_err),
                error_type=type(db_err).__name__,
                user_id=user_id,
                chat_id=chat_id,
            )
            return None
        except Exception as exc:
            # Best-effort tool execution: failures return None instead of breaking chat
            # This is intentional - tool invocation is optional and shouldn't block responses
            logger.warning(
                "Tool invocation failed (unexpected)",
                tool=name,
                error=str(exc),
                error_type=type(exc).__name__,
                user_id=user_id,
                chat_id=chat_id,
            )
            return None

    async def get_or_create_session(
        self,
        chat_id: Optional[str],
        user_id: str,
        first_message: str,
        tools_enabled: Dict[str, bool],
    ) -> ChatSessionModel:
        """
        Get existing chat session or create new one.

        Args:
            chat_id: Optional existing chat ID
            user_id: User ID
            first_message: First message content (for new session title)
            tools_enabled: Tools configuration

        Returns:
            ChatSession model

        Raises:
            HTTPException: If chat not found or access denied
        """
        tools_map = normalize_tools_state(tools_enabled)

        if chat_id:
            # Get existing session
            chat_session = await ChatSessionModel.get(chat_id)
            if not chat_session:
                # Fallback: create a new session if the provided chat_id is stale
                logger.warning(
                    "Chat session not found, creating a new one instead",
                    chat_id=chat_id,
                    user_id=user_id,
                )
                title = (
                    first_message[:50] + "..."
                    if len(first_message) > 50
                    else first_message
                )
                chat_session = ChatSessionModel(
                    title=title, user_id=user_id, tools_enabled=tools_map
                )
                await chat_session.insert()
                return chat_session

            if chat_session.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to chat session",
                )

            # Update tools if changed
            existing_tools = normalize_tools_state(
                getattr(chat_session, "tools_enabled", None)
            )
            if existing_tools != tools_map:
                await chat_session.update(
                    {
                        "$set": {
                            "tools_enabled": tools_map,
                            "updated_at": datetime.utcnow(),
                        }
                    }
                )
                chat_session.tools_enabled = tools_map

            return chat_session
        else:
            # Create new session
            title = (
                first_message[:50] + "..." if len(first_message) > 50 else first_message
            )
            chat_session = ChatSessionModel(
                title=title, user_id=user_id, tools_enabled=tools_map
            )
            await chat_session.insert()
            logger.info(
                "Created new chat session", chat_id=chat_session.id, user_id=user_id
            )
            return chat_session

    async def build_message_context(
        self,
        chat_session: ChatSessionModel,
        current_message: str,
        provided_context: Optional[List[Dict]] = None,
    ) -> List[Dict[str, str]]:
        """
        Build conversation context for AI.

        Args:
            chat_session: Chat session
            current_message: Current user message
            provided_context: Optional explicit context

        Returns:
            List of message dicts with role and content
        """
        message_history = []

        if provided_context and len(provided_context) > 0:
            # Use provided context
            for ctx_msg in provided_context:
                message_history.append(
                    {
                        "role": ctx_msg.get("role", "user"),
                        "content": ctx_msg.get("content", ""),
                    }
                )
        else:
            # Get recent messages from session (increased to 20 to fix context amnesia)
            recent_messages = (
                await ChatMessageModel.find(ChatMessageModel.chat_id == chat_session.id)
                .sort(-ChatMessageModel.created_at)
                .limit(20)
                .to_list()
            )

            # Reverse to chronological order
            for msg in reversed(recent_messages):
                message_history.append({"role": msg.role.value, "content": msg.content})

        # Add current message
        message_history.append({"role": "user", "content": current_message})

        return message_history

    async def build_message_context_with_memory(
        self,
        chat_session: ChatSessionModel,
        current_message: str,
        system_prompt: str = "",
        provided_context: Optional[List[Dict]] = None,
    ) -> List[Dict[str, str]]:
        """
        Build context with memory facts.

        Enhances LLM context with extracted facts from conversation history.
        Falls back to original behavior if memory is disabled or on error.

        Args:
            chat_session: Chat session model
            current_message: Current user message
            system_prompt: Optional system prompt to prepend
            provided_context: Optional explicit context (bypasses memory)

        Returns:
            List of message dicts with role and content
        """
        # If explicit context provided, use original behavior
        if provided_context:
            return await self.build_message_context(
                chat_session, current_message, provided_context
            )

        # Fallback if memory disabled
        if not getattr(self.settings, "memory_enabled", False):
            return await self.build_message_context(chat_session, current_message)

        try:
            memory_service = get_memory_service()

            # 1. Extract CONTEXT from user message (bank, period they're asking about)
            # NOTE: We extract CONTEXT here, not FACTS. Users ask questions, they don't provide data.
            # FACTS are extracted from AI responses in add_assistant_message().
            # Example: User asks about an entity/period → context: {entity, period}
            await memory_service.process_message(
                session_id=str(chat_session.id), message=current_message
            )

            # 2. Build context with memory
            context = await memory_service.get_context_for_llm(
                session_id=str(chat_session.id), system_prompt=system_prompt
            )

            # 3. Add current message
            context.append({"role": "user", "content": current_message})

            logger.debug(
                "memory.context_built",
                chat_id=chat_session.id,
                message_count=len(context),
                has_system_prompt=bool(system_prompt),
            )

            return context

        except Exception as e:
            # Intentional catch-all: memory system failures fall back to legacy context
            # This ensures chat always works even if the memory service is down
            logger.warning(
                "memory.fallback",
                error=str(e),
                error_type=type(e).__name__,
                chat_id=chat_session.id,
            )
            return await self.build_message_context(chat_session, current_message)

    async def process_with_saptiva(
        self,
        message: str,
        model: str,
        user_id: str,
        chat_id: str,
        tools_enabled: Dict[str, bool],
        channel: str = "chat",
        user_context: Optional[Dict] = None,
        document_context: Optional[str] = None,
        session_tools_enabled: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Any]:
        """
        Process message using Saptiva (kill switch path).

        Args:
            message: User message
            model: Model name
            user_id: User ID
            chat_id: Chat ID
            tools_enabled: Tools configuration (request-level)
            channel: Chat channel
            user_context: Additional context
            document_context: Document content for RAG (formatted string)
            session_tools_enabled: Tools persistidas en la sesión; se mezclan
                con las del request para decidir el function-calling nativo
                (el frontend solo manda tools_enabled al activar el pill)

        Returns:
            Coordinated response format (incluye `retail_analytics` si el
            function-calling nativo ejecutó una tool de datos en este turno)
        """
        async with trace_span(
            "saptiva_simple_chat",
            {
                "chat.id": chat_id,
                "chat.message_length": len(message),
                "chat.model": model,
                "chat.channel": channel,
            },
        ):
            # Build context
            context = user_context or {}
            context["chat_id"] = chat_id
            context["user_id"] = user_id

            tool_invocations: List[Dict[str, Any]] = []

            # Build payload using prompt registry (with conversation history)
            payload_data, metadata = await build_payload(
                model=model,
                user_prompt=message,
                user_context=context,
                tools_enabled=tools_enabled,
                channel=channel,
                chat_id=chat_id if chat_id else None,
                # Bloque RAG solo con adjuntos: sin él, follow-ups como
                # "explícame" escribían get_relevant_segments(...) como texto.
                has_documents=document_context is not None,
            )

            # Add document context as system message if provided
            if document_context:
                # Check if context contains images (identified by 📷 emoji)
                has_images = "📷" in document_context
                has_pdfs = "📄" in document_context

                if has_images and not has_pdfs:
                    # Only images - be very explicit
                    system_prompt = (
                        f"El usuario ha adjuntado una o más IMÁGENES. "
                        f"Tienes acceso al TEXTO EXTRAÍDO de estas imágenes mediante OCR (reconocimiento óptico de caracteres). "
                        f"IMPORTANTE: Aunque no puedes 'ver' las imágenes, SÍ puedes analizar, leer y responder preguntas sobre el texto que contienen.\n\n"
                        f"Contenido de las imágenes:\n\n{document_context}\n\n"
                        f"Usa esta información para responder las preguntas del usuario sobre las imágenes."
                    )
                elif has_images and has_pdfs:
                    # Mixed content
                    system_prompt = (
                        f"El usuario ha adjuntado documentos (PDFs e imágenes). "
                        f"Para las imágenes, tienes el texto extraído con OCR. "
                        f"Usa toda esta información para responder las preguntas:\n\n{document_context}"
                    )
                else:
                    # Only PDFs - enhanced prompt for robustness
                    system_prompt = (
                        f"El usuario ha adjuntado documentos para tu referencia. "
                        f"Usa esta información para responder sus preguntas.\n"
                        f"INSTRUCCIONES:\n"
                        f"1. Si encuentras la respuesta en el contexto, cítala.\n"
                        f"2. Si la información es parcial, úsala y menciona qué falta.\n"
                        f"3. Si no encuentras NADA relevante, dilo explícitamente, pero no digas 'el documento no lo menciona' a menos que estés seguro.\n"
                        f"4. Normaliza fechas (ej: Q1 = Primer Trimestre, 2T = Segundo Trimestre) al interpretar el texto.\n\n"
                        f"CONTEXTO DEL DOCUMENTO:\n{document_context}"
                    )

                system_message = {"role": "system", "content": system_prompt}

                # Prefer to enrich the existing system prompt so downstream
                # callers (and tests) see the document context in the first
                # system message.
                if (
                    payload_data["messages"]
                    and payload_data["messages"][0]["role"] == "system"
                ):
                    payload_data["messages"][0]["content"] = (
                        f"{payload_data['messages'][0]['content']}\n\n{system_prompt}"
                    )
                else:
                    payload_data["messages"].insert(0, system_message)

                logger.info(
                    "Added document context to prompt",
                    context_length=len(document_context),
                    has_images=has_images,
                    has_pdfs=has_pdfs,
                    chat_id=chat_id,
                )

            # Log telemetry
            logger.info(
                "Saptiva request metadata",
                request_id=metadata.get("request_id"),
                system_hash=metadata.get("system_hash"),
                prompt_version=metadata.get("prompt_version"),
                model=model,
                channel=channel,
                has_tools=metadata.get("has_tools", False),
            )

            # Spy log to confirm tool/document context is reaching the LLM payload
            try:
                # Generate detailed message summary for debugging context issues
                msg_summary = []
                for m in payload_data.get("messages", []):
                    content_preview = str(m.get("content", ""))[:80].replace(
                        "\n", "\\n"
                    )
                    msg_summary.append(f"{m.get('role')}: {content_preview}...")

                # Check for injected date in system prompt
                injected_date = "Not found"
                if (
                    payload_data.get("messages")
                    and payload_data["messages"][0]["role"] == "system"
                ):
                    sys_content = payload_data["messages"][0]["content"]
                    # Simple heuristic to find date-like strings or "Hoy es"
                    import re

                    date_match = re.search(
                        r"(\d{4}-\d{2}-\d{2}|Hoy es [^\n]+)", sys_content
                    )
                    if date_match:
                        injected_date = date_match.group(0)

                logger.info(
                    "🕵️ [LLM PROMPT SPY]",
                    chat_id=chat_id,
                    message_count=len(payload_data.get("messages", [])),
                    injected_date=injected_date,
                    messages_preview=msg_summary,
                    tools_enabled=list(tools_enabled.keys()) if tools_enabled else [],
                )
            except Exception as spy_exc:
                logger.warning("Failed to emit LLM prompt spy log", error=str(spy_exc))

            # Call Saptiva
            start_time = time.time()
            # Ensure message payload is always string-based to avoid 400s from upstream
            safe_messages: List[Dict[str, str]] = []
            for msg in payload_data["messages"]:
                content = msg.get("content", "")
                if not isinstance(content, str):
                    try:
                        content = json.dumps(content, ensure_ascii=False)
                    except Exception:
                        content = str(content)
                role = msg.get("role", "user")
                safe_messages.append({"role": role, "content": content})

            # Function-calling nativo también en la ruta NO-streaming: mismo
            # ciclo decide → tool → narración que la de streaming, reutilizando
            # el paso compartido. Sin esto, apagar el streaming apagaba en
            # silencio las tools de datos y el modelo respondía de memoria con
            # el pill encendido (paridad de transporte, card
            # function-calling-fuera-del-streaming).
            from .streaming.function_calling import (
                augmentar_con_tools_de_dominio,
                modelo_para_narrar,
                narracion_directa_del_plugin,
                respuesta_con_ambito,
            )

            mensajes_pre_tools = safe_messages
            (
                safe_messages,
                retail_analytics,
                fc_status,
            ) = await augmentar_con_tools_de_dominio(
                settings=self.settings,
                saptiva_client=self.saptiva_client,
                messages=safe_messages,
                model=model,
                request_tools=tools_enabled,
                session_tools=session_tools_enabled,
                # Perfil del usuario → ámbito en cada tool de datos. Sin esto
                # la ruta que usa la web (POST /api/chat) corría sin ámbito y
                # el gerente recibía `tienda_requerida` (visto 2026-09-02).
                user_id=user_id,
                conversacion_id=str(chat_id) if chat_id else None,
            )
            logger.info(
                "Non-streaming function calling step",
                status=fc_status,
                got_data=retail_analytics is not None,
                chat_id=chat_id,
            )

            # Narración directa: con UNA tool de datos y `response_text`
            # confiable del contrato genérico, re-narrar con el LLM solo
            # parafrasea las mismas cifras (~15-30 s extra con modelos
            # razonadores — card latencia-chat-retail-prediccion).
            texto_directo = narracion_directa_del_plugin(
                mensajes_pre_tools,
                safe_messages,
                retail_analytics,
                settings=self.settings,
            )
            if texto_directo is not None:
                logger.info(
                    "narracion.directa_plugin",
                    chat_id=chat_id,
                    response_length=len(texto_directo),
                )
                saptiva_response = SimpleNamespace(
                    choices=[{"message": {"content": texto_directo}}]
                )
            else:
                # Paridad con streaming: cuando el function-calling nativo está
                # activo, la NARRACIÓN no ofrece tools (la de streaming nunca
                # las manda). Ofrecer aquí el pseudo-tool legacy de
                # build_payload hace que modelos ansiosos respondan con otro
                # tool_call y contenido VACÍO en vez de narrar (visto en vivo
                # con qwen3.6-35b).
                narration_tools = (
                    payload_data.get("tools") if fc_status == "disabled" else None
                )
                presupuesto_llm = payload_data.get("max_tokens", 1024)
                modelo_narracion = modelo_para_narrar(self.settings, model, fc_status)

                saptiva_response = await self.saptiva_client.chat_completion(
                    messages=safe_messages,
                    model=modelo_narracion,
                    temperature=payload_data.get("temperature", 0.7),
                    max_tokens=presupuesto_llm,
                    stream=False,
                    tools=narration_tools,
                )

                if _narracion_agoto_presupuesto(saptiva_response):
                    # qwen3.6 piensa ANTES de escribir y ese consumo cuenta
                    # contra max_tokens; en follow-ups con contexto de tools
                    # puede agotar TODO el presupuesto y devolver content
                    # vacío con finish_reason=length. InferNode no permite
                    # apagar el thinking (chat_template_kwargs → 422;
                    # /no_think no lo honra qwen3.6), así que el remedio es
                    # UN reintento con presupuesto doblado.
                    logger.warning(
                        "narracion.presupuesto_agotado_reintento",
                        max_tokens=presupuesto_llm,
                        modelo=modelo_narracion,
                        chat_id=chat_id,
                    )
                    saptiva_response = await self.saptiva_client.chat_completion(
                        messages=safe_messages,
                        model=modelo_narracion,
                        temperature=payload_data.get("temperature", 0.7),
                        max_tokens=presupuesto_llm * 2,
                        stream=False,
                        tools=narration_tools,
                    )

            # Handle tool calls returned by the model (function-calling style)
            try:
                choices = getattr(saptiva_response, "choices", []) or []
                if choices:
                    first_choice = choices[0]
                    message_obj = (
                        first_choice.get("message", {})
                        if isinstance(first_choice, dict)
                        else {}
                    )
                    raw_tool_calls = []

                    if isinstance(message_obj, dict):
                        if message_obj.get("tool_calls"):
                            raw_tool_calls = message_obj.get("tool_calls") or []
                        elif message_obj.get("function_call"):
                            raw_tool_calls = [
                                {
                                    "type": "function",
                                    "function": message_obj.get("function_call"),
                                }
                            ]

                    for call in raw_tool_calls:
                        func = call.get("function") if isinstance(call, dict) else None
                        if not isinstance(func, dict):
                            continue

                        name = func.get("name")
                        raw_args = func.get("arguments")

                        parsed_args: Dict[str, Any] = {}
                        if isinstance(raw_args, str):
                            try:
                                parsed_args = json.loads(raw_args)
                            except json.JSONDecodeError:
                                parsed_args = {}
                        elif isinstance(raw_args, dict):
                            parsed_args = raw_args

                        if name:
                            result = await self._handle_tool_invocation(
                                name=name,
                                args=parsed_args,
                                user_id=user_id,
                                chat_id=chat_id or None,
                            )
                            if result:
                                tool_invocations.append(
                                    {
                                        "tool_name": name,
                                        "arguments": parsed_args,
                                        "result": result,
                                    }
                                )

            except Exception as parse_exc:  # pragma: no cover - defensive parsing
                logger.warning(
                    "Failed to parse or execute tool calls",
                    error=str(parse_exc),
                    user_id=user_id,
                    chat_id=chat_id,
                )

            # Línea de ámbito del plugin, por código y tras la narración.
            if retail_analytics:
                respuesta_con_ambito(saptiva_response, retail_analytics)

            # Format as coordinated response
            return {
                "type": "chat",
                "response": saptiva_response,
                "decision": {
                    "complexity": {"score": 0.0, "requires_research": False},
                    "reason": "Kill switch active - simple inference only",
                },
                "tool_invocations": tool_invocations,
                # AnalyticsResponse crudo del plugin si el function-calling
                # nativo ejecutó una tool de datos (paridad con el streaming).
                "retail_analytics": retail_analytics,
                "function_calling_status": fc_status,
                "escalation_available": False,
                "processing_time_ms": (time.time() - start_time) * 1000,
                "_metadata": metadata,
            }

    async def add_user_message(
        self,
        chat_session: ChatSessionModel,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChatMessageModel:
        """
        Add user message to session with explicit file metadata validation.

        Uses Pydantic models for type-safe metadata instead of Dict[str, Any].

        Args:
            chat_session: Chat session model
            content: Message content
            metadata: Optional metadata dict with 'file_ids' and 'files' keys

        Returns:
            Created ChatMessage with validated file metadata

        Raises:
            ValidationError: If file metadata structure is invalid
            Exception: If database insertion fails
        """
        from fastapi.encoders import jsonable_encoder
        from pydantic import ValidationError

        from ..models.chat import FileMetadata

        try:
            # Extract and validate file metadata using explicit Pydantic models
            file_ids = []
            files = []

            if metadata:
                # Extract file_ids (list of strings)
                file_ids = metadata.get("file_ids", [])

                # Validate and parse files using FileMetadata model
                raw_files = metadata.get("files", [])
                if raw_files:
                    try:
                        files = [FileMetadata.model_validate(f) for f in raw_files]
                        logger.debug(
                            "Validated file metadata",
                            chat_id=chat_session.id,
                            file_count=len(files),
                            filenames=[f.filename for f in files],
                        )
                    except ValidationError as ve:
                        logger.error(
                            "File metadata validation failed (Pydantic)",
                            chat_id=chat_session.id,
                            validation_errors=ve.errors(),
                            raw_files_preview=str(raw_files)[:200],
                            exc_info=True,
                        )
                        # Fallback: save only file_ids without rich metadata
                        files = []

            # FIX ISSUE-003: Clean metadata to prevent duplication
            # Remove file_ids and files from metadata since they're stored in explicit fields
            clean_metadata = {"source": "api"}
            if metadata:
                clean_metadata = {
                    k: v for k, v in metadata.items() if k not in ("file_ids", "files")
                }
                clean_metadata["source"] = "api"

            # Create message with explicit typed fields
            user_message = ChatMessageModel(
                chat_id=chat_session.id,
                role=MessageRole.USER,
                content=content,
                file_ids=file_ids,
                files=files,
                schema_version=2,
                # Legacy metadata for backwards compatibility (cleaned)
                metadata=clean_metadata,
            )

            # Ensure BSON/JSON serializability before insertion
            try:
                _probe = jsonable_encoder(user_message, by_alias=True)
                logger.debug(
                    "Message is serializable",
                    chat_id=chat_session.id,
                    file_ids_count=len(file_ids),
                    files_count=len(files),
                )
            except Exception as enc_err:
                logger.error(
                    "Message encoding failed (BSON compatibility)",
                    error=str(enc_err),
                    chat_id=chat_session.id,
                    exc_info=True,
                )
                raise

            # Persist to MongoDB
            await user_message.insert()

            # Update session stats (message_count, timestamps)
            chat_session.message_count += 1
            chat_session.updated_at = datetime.utcnow()
            chat_session.last_message_at = datetime.utcnow()
            if chat_session.message_count == 1:
                chat_session.first_message_at = datetime.utcnow()
            await chat_session.save()

            logger.info(
                "Added user message with validated files",
                message_id=user_message.id,
                chat_id=chat_session.id,
                file_count=len(files),
                schema_version=2,
            )

            # CRITICAL: Record in unified history (so message appears after refresh)
            try:
                from ..services.history_service import HistoryService

                await HistoryService.record_chat_message(
                    chat_id=chat_session.id,
                    user_id=chat_session.user_id,
                    message=user_message,
                )
                logger.debug(
                    "Recorded user message in history",
                    message_id=user_message.id,
                    chat_id=chat_session.id,
                )
            except Exception as hist_err:
                # Don't fail message creation if history fails, but log it
                logger.error(
                    "Failed to record user message in history",
                    error=str(hist_err),
                    message_id=user_message.id,
                    chat_id=chat_session.id,
                    exc_info=True,
                )

            # Invalidate cache
            cache = await get_redis_cache()
            await cache.invalidate_chat_history(chat_session.id)

            return user_message

        except ValidationError as ve:
            logger.error(
                "Pydantic validation failed for user message",
                error=str(ve),
                validation_errors=ve.errors(),
                chat_id=chat_session.id,
                exc_info=True,
            )
            raise

        except PyMongoError as db_err:
            logger.error(
                "Database error adding user message",
                error=str(db_err),
                error_type=type(db_err).__name__,
                chat_id=chat_session.id,
                has_metadata=bool(metadata),
                exc_info=True,
            )
            raise ChatServiceError(
                f"Failed to save user message: {db_err}", cause=db_err
            ) from db_err

        except Exception as e:
            # Catch-all for unexpected errors - log and wrap
            logger.error(
                "Unexpected error adding user message",
                error=str(e),
                error_type=type(e).__name__,
                chat_id=chat_session.id,
                has_metadata=bool(metadata),
                exc_info=True,
            )
            raise ChatServiceError(
                f"Unexpected error saving message: {e}", cause=e
            ) from e

    async def add_assistant_message(
        self,
        chat_session: ChatSessionModel,
        content: str,
        model: str,
        task_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tokens: Optional[Dict] = None,
        latency_ms: Optional[int] = None,
    ) -> ChatMessageModel:
        """Add assistant message to session and record in unified history."""
        # FIX ISSUE-003: Clean metadata to prevent duplication (defensive)
        # Although assistant messages typically don't have file_ids, clean metadata to be safe
        clean_metadata = {}
        if metadata:
            clean_metadata = {
                k: v for k, v in metadata.items() if k not in ("file_ids", "files")
            }

        ai_message = await chat_session.add_message(
            role=MessageRole.ASSISTANT,
            content=content,
            model=model,
            task_id=task_id,
            metadata=clean_metadata,
            tokens=tokens,
            latency_ms=latency_ms,
        )

        # MEMORY: Extract FACTS from AI response
        # ⚠️ IMPORTANT: Facts come from AI responses, NOT user messages!
        # Users ASK questions - they don't have the data.
        # AI PROVIDES data - from DB queries, RAG, NL2SQL, etc.
        # This was a bug we caught during implementation - don't change this logic!
        if getattr(self.settings, "memory_enabled", False):
            try:
                memory_service = get_memory_service()
                await memory_service.process_message(
                    session_id=str(chat_session.id), message=content
                )
            except Exception as e:
                logger.warning(
                    "memory.extraction_failed", error=str(e), chat_id=chat_session.id
                )

        # NOTE: History recording is handled by chat_session.add_message() (chat.py:236)
        # No need to call HistoryService.record_chat_message() here

        # Invalidate cache
        cache = await get_redis_cache()
        await cache.invalidate_chat_history(chat_session.id)
        if task_id:
            await cache.invalidate_research_tasks(chat_session.id)

        return ai_message
