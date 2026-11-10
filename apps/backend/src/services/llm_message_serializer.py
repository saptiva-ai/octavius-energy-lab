"""
LLM Message Serializer - Converts DB messages to LLM API format

Política de adjuntos: un mensaje guarda exactamente los adjuntos enviados en su payload.
No existe "herencia" de adjuntos desde turnos previos.
El adaptador al LLM serializa solo el content del último turno del usuario, con sus imágenes.

OBS-3: Logs en punto 3 (adaptador→LLM) - justo antes de llamar al LLM
"""

from typing import Any, Dict, List, Optional

import structlog

from ..models.chat import ChatMessage
from .files_presign import presign_file_url, url_fingerprint

logger = structlog.get_logger(__name__)


async def serialize_message_for_llm(
    message: ChatMessage, user_id: str, include_images: bool = True
) -> Dict[str, Any]:
    """
    Serialize a ChatMessage to LLM API format.

    Política: Las imágenes SOLO viven en el turno donde entraron.
    No se heredan adjuntos de mensajes previos.

    Args:
        message: ChatMessage from database
        user_id: User ID for ownership validation (presign)
        include_images: Whether to include file_ids as images (default: True)

    Returns:
        Dict with keys: role, content
        - For text-only: {"role": "user", "content": "text"}
        - For multimodal: {"role": "user", "content": [{"type": "text", ...}, {"type": "input_image", ...}]}

    Example:
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "¿Qué dice esta imagen?"},
                {"type": "input_image", "image_url": "https://...?hash=abc123"}
            ]
        }
    """
    # Text content
    text_content = message.content or ""

    # If no images or images disabled, return simple text message
    if not include_images or not message.file_ids:
        return {"role": message.role.value, "content": text_content}

    # Multimodal content: text + images
    content_parts = []

    # Add text first (if exists)
    if text_content.strip():
        content_parts.append({"type": "text", "text": text_content})

    # Presign file URLs and add as images
    for file_id in message.file_ids:
        presigned_url = await presign_file_url(file_id, user_id)

        if presigned_url:
            content_parts.append({"type": "input_image", "image_url": presigned_url})
            logger.debug(
                "llm_message_image_added",
                file_id=file_id,
                url_fingerprint=url_fingerprint(presigned_url),
            )
        else:
            logger.warning(
                "llm_message_image_presign_failed", file_id=file_id, user_id=user_id
            )

    # Return multimodal format
    return {"role": message.role.value, "content": content_parts}


async def build_llm_messages_from_history(
    messages: List[ChatMessage], user_id: str, include_images: bool = True
) -> List[Dict[str, Any]]:
    """
    Build LLM messages array from chat history.

    Política: Cada mensaje lleva SOLO sus propios adjuntos.
    No hay herencia de adjuntos entre turnos.

    Args:
        messages: List of ChatMessage objects (chronological order)
        user_id: User ID for presign ownership validation
        include_images: Whether to serialize file_ids as images

    Returns:
        List of LLM-format messages

    Example:
        [
            {"role": "user", "content": [{"type": "text", ...}, {"type": "input_image", ...}]},
            {"role": "assistant", "content": "Veo un gato en la imagen..."},
            {"role": "user", "content": [{"type": "text", ...}]}  # No images in second turn
        ]
    """
    llm_messages = []

    for msg in messages:
        serialized = await serialize_message_for_llm(msg, user_id, include_images)
        llm_messages.append(serialized)

    # OBS-3: Log payload tail before sending to LLM
    if llm_messages:
        last_user_msg = next(
            (m for m in reversed(llm_messages) if m["role"] == "user"), None
        )

        if last_user_msg:
            content = last_user_msg.get("content", "")
            if isinstance(content, list):
                # Multimodal content
                text_parts = [p for p in content if p.get("type") == "text"]
                image_parts = [p for p in content if p.get("type") == "input_image"]

                image_url_hashes = [
                    url_fingerprint(p["image_url"]) for p in image_parts
                ]

                logger.info(
                    "llm_payload_tail",
                    last_user_content_parts=len(content),
                    text_parts=len(text_parts),
                    image_parts=len(image_parts),
                    image_url_hashes=image_url_hashes,
                )
            else:
                # Text-only content
                logger.info(
                    "llm_payload_tail",
                    last_user_content_len=(
                        len(content) if isinstance(content, str) else 0
                    ),
                    image_url_hashes=[],
                )

    return llm_messages


async def build_llm_payload_with_images(
    messages: List[ChatMessage],
    user_id: str,
    model: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    include_images: bool = True,
) -> Dict[str, Any]:
    """
    Build complete LLM payload with messages from history.

    Args:
        messages: Chat history messages
        user_id: User ID for presign
        model: Model name
        temperature: Optional temperature override
        max_tokens: Optional max tokens override
        include_images: Whether to serialize file_ids as images

    Returns:
        Complete LLM API payload

    Example:
        {
            "model": "Saptiva Turbo",
            "messages": [...],
            "temperature": 0.7,
            "max_tokens": 1024
        }
    """
    llm_messages = await build_llm_messages_from_history(
        messages, user_id, include_images=include_images
    )

    payload = {"model": model, "messages": llm_messages}

    if temperature is not None:
        payload["temperature"] = temperature

    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    return payload
