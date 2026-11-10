"""Utilities to persist SSE stream events into the unified history."""

from datetime import datetime
from typing import Any, Optional

import structlog

from .history_service import HistoryService

logger = structlog.get_logger(__name__)


PROGRESS_EVENT_TYPES = {
    "progress",
    "progress_update",
    "research_progress",
    "task_progress",
}
COMPLETED_EVENT_TYPES = {"task_completed", "research_completed", "completion"}
FAILED_EVENT_TYPES = {"task_failed", "research_failed", "error", "failure"}
SOURCE_EVENT_TYPES = {"source_found", "source_discovered", "source"}


def _to_float(value: Optional[Any]) -> Optional[float]:
    """Attempt to convert event values to float."""
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


async def persist_history_from_stream(event: Any, task: Any):
    """Persist research lifecycle events into unified history."""

    if not getattr(task, "chat_id", None):
        return

    event_key = (getattr(event, "event_type", "") or "").lower()
    data = getattr(event, "data", {}) or {}

    metadata = {
        "sequence": getattr(event, "sequence", None),
        "raw_event_type": getattr(event, "event_type", None),
        "stream_timestamp": (
            event.timestamp.isoformat()
            if isinstance(event.timestamp, datetime)
            else None
        ),
    }

    try:
        if event_key in PROGRESS_EVENT_TYPES:
            progress_value = _to_float(data.get("progress"))

            if progress_value is None and data.get("step") and data.get("total_steps"):
                step = _to_float(data.get("step"))
                total_steps = _to_float(data.get("total_steps"))
                if step is not None and total_steps not in (None, 0):
                    progress_value = (step / total_steps) * 100

            current_step = (
                data.get("current_step")
                or data.get("phase")
                or data.get("message")
                or "progress"
            )

            sources_found = data.get("sources_found")
            if sources_found is None and isinstance(data.get("sources"), list):
                sources_found = len(data.get("sources", []))

            iterations_completed = data.get("iterations_completed") or data.get(
                "iterations"
            )

            await HistoryService.record_research_progress(
                chat_id=task.chat_id,
                user_id=task.user_id,
                task_id=task.id,
                progress=progress_value if progress_value is not None else 0.0,
                current_step=str(current_step),
                sources_found=(
                    int(sources_found)
                    if isinstance(sources_found, (int, float))
                    else None
                ),
                iterations_completed=(
                    int(iterations_completed)
                    if isinstance(iterations_completed, (int, float))
                    else None
                ),
                metadata={**metadata, "stream_event": data},
            )

        elif event_key in COMPLETED_EVENT_TYPES:
            sources_found = data.get("sources_found")
            if sources_found is None and isinstance(data.get("sources"), list):
                sources_found = len(data["sources"])
            if sources_found is None:
                sources_found = data.get("total_sources")

            iterations = data.get("iterations_completed") or data.get("iterations")

            await HistoryService.record_research_completed(
                chat_id=task.chat_id,
                user_id=task.user_id,
                task=task,
                sources_found=(
                    int(sources_found) if isinstance(sources_found, (int, float)) else 0
                ),
                iterations_completed=(
                    int(iterations) if isinstance(iterations, (int, float)) else 0
                ),
                result_metadata={**metadata, "stream_event": data},
            )

        elif event_key in FAILED_EVENT_TYPES:
            error_message = (
                data.get("error")
                or data.get("error_message")
                or data.get("message")
                or "Research task failed"
            )
            progress_value = _to_float(data.get("progress"))
            current_step = (
                data.get("current_step") or data.get("phase") or data.get("stage")
            )

            await HistoryService.record_research_failed(
                chat_id=task.chat_id,
                user_id=task.user_id,
                task_id=task.id,
                error_message=str(error_message),
                progress=progress_value,
                current_step=current_step,
                metadata={**metadata, "stream_event": data},
            )

        elif event_key in SOURCE_EVENT_TYPES:
            source_payload = data.get("source") or data
            source_id = (
                source_payload.get("source_id")
                or source_payload.get("id")
                or source_payload.get("url")
            )
            url = source_payload.get("url")
            title = source_payload.get("title") or source_payload.get("name")

            if source_id and url and title:
                relevance = (
                    _to_float(
                        source_payload.get("relevance_score")
                        or source_payload.get("relevance")
                        or source_payload.get("score")
                        or 0.0
                    )
                    or 0.0
                )
                credibility = (
                    _to_float(
                        source_payload.get("credibility_score")
                        or source_payload.get("credibility")
                        or 0.0
                    )
                    or 0.0
                )

                await HistoryService.record_source_discovery(
                    chat_id=task.chat_id,
                    user_id=task.user_id,
                    task_id=task.id,
                    source_id=str(source_id),
                    url=str(url),
                    title=str(title),
                    relevance_score=float(relevance),
                    credibility_score=float(credibility),
                    metadata={**metadata, "stream_event": data},
                )

    except Exception as history_error:  # pragma: no cover - defensive logging
        logger.warning(
            "Failed to persist stream event in history",
            chat_id=task.chat_id,
            task_id=task.id,
            error=str(history_error),
            event_type=getattr(event, "event_type", None),
        )


__all__ = [
    "persist_history_from_stream",
    "PROGRESS_EVENT_TYPES",
    "COMPLETED_EVENT_TYPES",
    "FAILED_EVENT_TYPES",
    "SOURCE_EVENT_TYPES",
]
