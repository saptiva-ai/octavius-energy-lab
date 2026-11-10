"""
Chat Response Builder - Builder Pattern Implementation.

Provides a fluent API for constructing complex chat responses
with all required metadata and optional fields.
"""

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi.responses import JSONResponse

from ..schemas.audit import AuditReportResponse
from ..services.audit_utils import summarize_audit_for_message
from .chat_context import ChatProcessingResult


def sanitize_floats(obj: Any) -> Any:
    """
    Recursively sanitize NaN/Infinity float values for JSON serialization.

    Converts NaN and Infinity to None to prevent JSON serialization errors.

    Args:
        obj: Object to sanitize (dict, list, float, or other)

    Returns:
        Sanitized object with NaN/Infinity replaced by None
    """
    if isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_floats(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


class ChatResponseBuilder:
    """
    Builder for constructing ChatResponse JSON.

    Uses Builder Pattern to provide fluent API for complex object construction.

    Example:
        response = (ChatResponseBuilder()
            .with_chat_id("chat-123")
            .with_message("AI response here")
            .with_model("Saptiva Turbo")
            .with_latency(234.5)
            .build())
    """

    def __init__(self):
        self._data: Dict[str, Any] = {
            "type": "chat",
            "content": "",  # Fixed: Use "content" to match ChatResponse schema
            "chat_id": None,
            "message_id": None,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._metadata: Dict[str, Any] = {}
        self._headers: Dict[str, str] = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }

    def with_chat_id(self, chat_id: str) -> "ChatResponseBuilder":
        """Set chat ID."""
        self._data["chat_id"] = chat_id
        return self

    def with_message(
        self, content: str, sanitized: bool = True
    ) -> "ChatResponseBuilder":
        """Set message content."""
        self._data["content"] = (
            content  # Fixed: Use "content" to match ChatResponse schema
        )
        if sanitized:
            self._data["sanitized"] = True
        return self

    def with_message_id(self, message_id: str) -> "ChatResponseBuilder":
        """Set message ID."""
        self._data["message_id"] = message_id
        return self

    def with_model(self, model: str) -> "ChatResponseBuilder":
        """Set model used."""
        self._data["model"] = model
        return self

    def with_tokens(
        self, prompt_tokens: int, completion_tokens: int
    ) -> "ChatResponseBuilder":
        """Set token usage."""
        self._data["tokens"] = {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": prompt_tokens + completion_tokens,
        }
        return self

    def with_latency(self, latency_ms: float) -> "ChatResponseBuilder":
        """Set processing latency."""
        self._data["latency_ms"] = round(latency_ms, 2)
        return self

    def with_decision(self, decision: Dict[str, Any]) -> "ChatResponseBuilder":
        """Set decision metadata (for coordinated responses)."""
        self._data["decision"] = decision
        return self

    def with_artifact(self, artifact: Dict[str, Any]) -> "ChatResponseBuilder":
        """Attach structured artifact (e.g., audit report) for frontend rendering."""
        self._data["artifact"] = artifact
        return self

    def with_research_task(self, task_id: str) -> "ChatResponseBuilder":
        """Set research task ID."""
        self._data["task_id"] = task_id
        self._data["research_triggered"] = True
        return self

    def with_session_title(self, title: str) -> "ChatResponseBuilder":
        """Set session title (for auto-titling)."""
        self._data["session_title"] = title
        return self

    def with_metadata(self, key: str, value: Any) -> "ChatResponseBuilder":
        """Add custom metadata."""
        self._metadata[key] = value
        return self

    def with_error(
        self, error_message: str, error_code: Optional[str] = None
    ) -> "ChatResponseBuilder":
        """Set error information."""
        self._data["error"] = error_message
        if error_code:
            self._data["error_code"] = error_code
        return self

    def from_processing_result(
        self, result: ChatProcessingResult
    ) -> "ChatResponseBuilder":
        """
        Populate builder from a ChatProcessingResult.

        Convenience method to build response from domain model.
        """
        import structlog

        logger = structlog.get_logger(__name__)

        logger.info(
            "🐛 [DEBUG] ChatResponseBuilder.from_processing_result",
            sanitized_content_length=(
                len(result.sanitized_content) if result.sanitized_content else 0
            ),
            content_length=len(result.content) if result.content else 0,
            sanitized_preview=(
                result.sanitized_content[:100] if result.sanitized_content else "(NONE)"
            ),
        )

        self.with_chat_id(result.metadata.chat_id)
        # If audit artifact exists, avoid dumping full markdown and use a concise message
        audit_artifact_local = (
            result.metadata.decision_metadata.get("audit_artifact")
            if result.metadata and result.metadata.decision_metadata
            else None
        )

        audit_summary_msg = None
        if audit_artifact_local:
            try:
                artifact_obj = AuditReportResponse.model_validate(audit_artifact_local)
                audit_summary_msg = summarize_audit_for_message(
                    doc_name=artifact_obj.doc_name or "el documento",
                    artifact=artifact_obj,
                    summary_raw=(
                        artifact_obj.metadata.get("summary")
                        if artifact_obj.metadata
                        else None
                    ),
                )
            except Exception:
                audit_summary_msg = None

        if audit_summary_msg:
            # Prefer semantic summary built from the artifact (top findings + next steps)
            self.with_message(audit_summary_msg, sanitized=True)
        elif audit_artifact_local:
            # Fallback: if artifact exists but summary couldn't be built, keep existing sanitized content or a generic message
            self.with_message(
                result.sanitized_content
                or "He generado el reporte de auditoría. Puedes ver los detalles a continuación.",
                sanitized=True,
            )
        else:
            self.with_message(result.sanitized_content, sanitized=True)
        self.with_message_id(result.metadata.assistant_message_id or "")
        self.with_model(result.metadata.model_used)
        self.with_latency(result.processing_time_ms)

        if result.metadata.tokens_used:
            tokens = result.metadata.tokens_used
            self.with_tokens(tokens.get("prompt", 0), tokens.get("completion", 0))

        if result.metadata.decision_metadata:
            self.with_decision(result.metadata.decision_metadata)
            tool_invocations = result.metadata.decision_metadata.get("tool_invocations")
            audit_artifact = result.metadata.decision_metadata.get("audit_artifact")
        else:
            tool_invocations = None
            audit_artifact = None

        if result.task_id:
            self.with_research_task(result.task_id)

        if result.session_title:
            self.with_session_title(result.session_title)

        if audit_artifact:
            self.with_artifact(audit_artifact)

        # Add processing metadata
        self.with_metadata("strategy_used", result.strategy_used)
        self.with_metadata("session_updated", result.session_updated)
        if tool_invocations:
            self.with_metadata("tool_invocations", tool_invocations)

        # Paridad con streaming: el frontend abre el chart del canvas leyendo
        # response.metadata.retail_analytics también en la ruta no-streaming.
        retail_analytics = (
            result.metadata.decision_metadata.get("retail_analytics")
            if result.metadata and result.metadata.decision_metadata
            else None
        )
        if retail_analytics:
            self.with_metadata("retail_analytics", retail_analytics)

        return self

    def build(self) -> JSONResponse:
        """
        Build final JSONResponse.

        Returns:
            JSONResponse with constructed data and headers.
        """
        import structlog

        logger = structlog.get_logger(__name__)

        # Merge metadata into response data
        if self._metadata:
            self._data["metadata"] = self._metadata

        logger.info(
            "🐛 [DEBUG] ChatResponseBuilder.build()",
            content_length=len(self._data.get("content", "")),
            content_preview=self._data.get("content", "")[:100],
            data_keys=list(self._data.keys()),
        )

        # Sanitize float values (NaN/Infinity) before JSON serialization
        # This prevents "Out of range float values are not JSON compliant" errors
        sanitized_data = sanitize_floats(self._data)

        return JSONResponse(
            content=sanitized_data, headers=self._headers, status_code=200
        )

    def build_error(self, status_code: int = 500) -> JSONResponse:
        """
        Build error response.

        Args:
            status_code: HTTP status code for error.

        Returns:
            JSONResponse with error data.
        """
        return JSONResponse(
            content={
                "error": self._data.get("error", "Unknown error"),
                "error_code": self._data.get("error_code"),
                "timestamp": self._data["timestamp"],
            },
            headers=self._headers,
            status_code=status_code,
        )


class StreamingResponseBuilder:
    """
    Builder for streaming responses.

    For future implementation of SSE (Server-Sent Events) streaming.
    """

    def __init__(self):
        self._events: List[Dict[str, Any]] = []

    def add_chunk(
        self, content: str, is_final: bool = False
    ) -> "StreamingResponseBuilder":
        """Add a content chunk."""
        self._events.append({"type": "content", "data": content, "is_final": is_final})
        return self

    def add_metadata(self, metadata: Dict[str, Any]) -> "StreamingResponseBuilder":
        """Add metadata event."""
        self._events.append({"type": "metadata", "data": metadata})
        return self

    def build(self):
        """Build streaming response (placeholder for future SSE implementation)."""
        # Future: Return StreamingResponse with SSE events
        raise NotImplementedError("Streaming responses not yet implemented")
