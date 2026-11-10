"""Unified files router (upload, events, management)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import AsyncGenerator, List, Optional
from uuid import uuid4

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sse_starlette.sse import EventSourceResponse

from ..core.auth import get_current_user, get_current_user_sse
from ..core.config import get_settings
from ..core.redis_cache import get_redis_cache
from ..models.document import Document, DocumentStatus
from ..models.user import User
from ..schemas.files import (
    FileError,
    FileEventPayload,
    FileEventPhase,
    FileIngestBulkResponse,
    FileIngestResponse,
    FileStatus,
)
from ..services.file_events import file_event_bus
from ..services.file_ingest import file_ingest_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/files", tags=["files"])

# V1 Rate limiting config
RATE_LIMIT_UPLOADS_PER_MINUTE = 10  # Increased for testing
RATE_LIMIT_WINDOW_SECONDS = 60


async def _check_rate_limit(user_id: str) -> None:
    """Simple Redis-based rate limiter: 10 uploads/min per user."""
    redis_cache = await get_redis_cache()
    redis_client = redis_cache.client
    key = f"rate_limit:upload:{user_id}"
    now = int(datetime.utcnow().timestamp())
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    # Sliding window: remove old entries, count recent ones
    await redis_client.zremrangebyscore(key, "-inf", window_start)
    count = await redis_client.zcard(key)

    if count >= RATE_LIMIT_UPLOADS_PER_MINUTE:
        logger.warning("Rate limit exceeded", user_id=user_id, count=count)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {RATE_LIMIT_UPLOADS_PER_MINUTE} uploads per minute",
        )

    # Add current request to window
    await redis_client.zadd(key, {str(now): now})
    await redis_client.expire(
        key, 300
    )  # TTL cleanup: 5 min for natural garbage collection


@router.post(
    "/upload",
    response_model=FileIngestBulkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_files(
    request: Request,
    files: List[UploadFile] = File(...),
    conversation_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    trace_id = (
        request.headers.get("x-trace-id")
        or request.headers.get("X-Trace-Id")
        or request.query_params.get("trace_id")
        or uuid4_hex()
    )
    request.state.trace_id = trace_id
    base_idempotency_key = request.headers.get("Idempotency-Key")

    # V1 Rate limiting: 5 uploads/minute per user (simple Redis sliding window)
    await _check_rate_limit(current_user.id)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided"
        )

    responses: List[FileIngestResponse] = []
    for upload in files:
        try:
            response = await file_ingest_service.ingest_file(
                user_id=str(current_user.id),
                upload=upload,
                trace_id=trace_id,
                conversation_id=conversation_id,
                idempotency_key=base_idempotency_key,
            )
            responses.append(response)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "File upload failed",
                error=str(exc),
                filename=upload.filename,
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="File processing failed",
            ) from exc

    return FileIngestBulkResponse(files=responses)


@router.get("/events/{file_id}")
async def file_events(
    file_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_sse),
):
    document = await Document.get(file_id)
    if not document or document.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    trace_id = request.query_params.get("t") or uuid4_hex()
    request.state.trace_id = trace_id

    settings = get_settings()
    origin = request.headers.get("origin") or request.headers.get("referer")
    allowed_origins = set(settings.parsed_cors_origins or [])
    if (
        origin
        and allowed_origins
        and not any(origin.startswith(o) for o in allowed_origins)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden origin"
        )

    async def event_stream() -> AsyncGenerator[dict, None]:
        async with file_event_bus.subscribe(file_id) as queue:
            # Always emit initial snapshot
            if document.status == DocumentStatus.READY:
                current_status = FileStatus.READY
            elif document.status == DocumentStatus.FAILED:
                current_status = FileStatus.FAILED
            else:
                current_status = FileStatus.PROCESSING
            initial = FileEventPayload(
                file_id=file_id,
                trace_id=trace_id,
                phase=FileEventPhase.UPLOAD,
                pct=0.0,
                status=current_status,
            )
            yield {"event": "meta", "data": initial.model_dump_json()}

            if current_status == FileStatus.READY:
                ready_payload = FileEventPayload(
                    file_id=file_id,
                    trace_id=trace_id,
                    phase=FileEventPhase.COMPLETE,
                    pct=100.0,
                    status=FileStatus.READY,
                    mimetype=document.content_type,
                    pages=document.total_pages,
                )
                yield {"event": "ready", "data": ready_payload.model_dump_json()}
                return
            if current_status == FileStatus.FAILED:
                failed_payload = FileEventPayload(
                    file_id=file_id,
                    trace_id=trace_id,
                    phase=FileEventPhase.COMPLETE,
                    pct=100.0,
                    status=FileStatus.FAILED,
                    error=FileError(code="FAILED", detail="File processing failed"),
                )
                yield {"event": "failed", "data": failed_payload.model_dump_json()}
                return

            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    # Keep connection alive
                    heartbeat = FileEventPayload(
                        file_id=file_id,
                        trace_id=trace_id,
                        phase=FileEventPhase.UPLOAD,
                        pct=0.0,
                        status=current_status,
                    )
                    yield {"event": "heartbeat", "data": heartbeat.model_dump_json()}
                    continue

                event_name = "progress"
                if payload.status == FileStatus.READY:
                    event_name = "ready"
                elif payload.status == FileStatus.FAILED:
                    event_name = "failed"

                yield {"event": event_name, "data": payload.model_dump_json()}
                if payload.status:
                    current_status = payload.status

                if payload.status in {FileStatus.READY, FileStatus.FAILED}:
                    break

    return EventSourceResponse(event_stream())


def uuid4_hex() -> str:
    return uuid4().hex
