"""
Internal API router for cross-service operations.

Protected by X-Internal-Key header — not exposed to end users.
Used by MCP kanban-sync to update feedback statuses in MongoDB,
and by triage automation scripts to query feedback data.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..core.database import Database
from ..models.feedback import MessageFeedback

logger = structlog.get_logger(__name__)

router = APIRouter()

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")


async def verify_internal_key(
    x_internal_key: Optional[str] = Header(None),
) -> None:
    """Validate X-Internal-Key header against env var."""
    if not INTERNAL_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Internal API not configured (INTERNAL_API_KEY missing)",
        )
    if x_internal_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal key")


# --- Schemas ---


class TicketStatusUpdate(BaseModel):
    ticket_id: str
    status: str  # "Open", "Backlog", "In Progress", "Review", "Done", "Closed"


class TicketStatusUpdateResponse(BaseModel):
    ticket_id: str
    status: str
    modified_count: int


class TicketStatusQuery(BaseModel):
    ticket_ids: List[str]


class TicketStatusInfo(BaseModel):
    ticket_id: str
    status: str
    count: int


# --- Triage Schemas ---


class FeedbackQuery(BaseModel):
    """Query parameters for filtering feedback records."""

    date_from: Optional[datetime] = Field(None, description="Start of date range (UTC)")
    date_to: Optional[datetime] = Field(None, description="End of date range (UTC)")
    rating: Optional[str] = Field(None, description="Filter by rating: 'up' or 'down'")
    status: Optional[str] = Field(None, description="Filter by feedback status")
    ticket_id: Optional[str] = Field(None, description="Filter by ticket_id")
    feedback_ids: Optional[List[str]] = Field(
        None, description="Filter by specific feedback_ids (FDBK-XXXX)"
    )
    limit: int = Field(100, ge=1, le=1000, description="Max records to return")


class FeedbackRecord(BaseModel):
    """Feedback record with full context for triage."""

    feedback_id: Optional[str] = None
    rating: str
    reason: Optional[str] = None
    created_at: datetime
    conversation_id: str
    message_id: str
    user_id: str
    context: Optional[Dict[str, Any]] = None
    ticket_id: Optional[str] = None
    status: str


class ConversationQuery(BaseModel):
    """Query conversations by ID with optional artifact inclusion."""

    conversation_ids: List[str] = Field(
        ..., min_length=1, max_length=20, description="Conversation IDs to fetch"
    )
    include_artifacts: bool = Field(True, description="Include associated artifacts")


# --- Endpoints ---


@router.patch(
    "/feedback/ticket-status",
    response_model=TicketStatusUpdateResponse,
    dependencies=[Depends(verify_internal_key)],
)
async def update_ticket_status(
    payload: TicketStatusUpdate,
) -> TicketStatusUpdateResponse:
    """Update status of all feedbacks linked to a ticket_id."""
    result = await MessageFeedback.find(
        MessageFeedback.ticket_id == payload.ticket_id
    ).update_many({"$set": {"status": payload.status}})

    modified = result.modified_count if result else 0
    logger.info(
        "internal.ticket_status_updated",
        ticket_id=payload.ticket_id,
        status=payload.status,
        modified_count=modified,
    )
    return TicketStatusUpdateResponse(
        ticket_id=payload.ticket_id,
        status=payload.status,
        modified_count=modified,
    )


@router.post(
    "/feedback/ticket-status/batch",
    response_model=List[TicketStatusInfo],
    dependencies=[Depends(verify_internal_key)],
)
async def get_ticket_statuses(payload: TicketStatusQuery) -> List[TicketStatusInfo]:
    """Query feedback status grouped by ticket_id."""
    pipeline = [
        {"$match": {"ticket_id": {"$in": payload.ticket_ids}}},
        {
            "$group": {
                "_id": "$ticket_id",
                "status": {"$first": "$status"},
                "count": {"$sum": 1},
            }
        },
    ]
    db = Database.database
    collection = db["message_feedback"]
    cursor = collection.aggregate(pipeline)
    results = await cursor.to_list(length=None)
    return [
        TicketStatusInfo(
            ticket_id=doc["_id"],
            status=doc["status"],
            count=doc["count"],
        )
        for doc in results
    ]


@router.get(
    "/feedback/stats",
    dependencies=[Depends(verify_internal_key)],
)
async def get_feedback_stats() -> dict:
    """Diagnostic: feedback collection stats for drift detection."""
    db = Database.database
    collection = db["message_feedback"]

    total = await collection.count_documents({})
    with_ticket = await collection.count_documents({"ticket_id": {"$ne": None}})

    status_cursor = collection.aggregate(
        [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    )
    statuses = {doc["_id"]: doc["count"] async for doc in status_cursor}

    ticket_cursor = collection.aggregate(
        [
            {"$match": {"ticket_id": {"$ne": None}}},
            {
                "$group": {
                    "_id": "$ticket_id",
                    "status": {"$first": "$status"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": 30},
        ]
    )
    tickets = [
        {"ticket_id": doc["_id"], "status": doc["status"], "count": doc["count"]}
        async for doc in ticket_cursor
    ]

    return {
        "total_feedbacks": total,
        "with_ticket_id": with_ticket,
        "without_ticket_id": total - with_ticket,
        "by_status": statuses,
        "top_tickets": tickets,
    }


# --- Triage Endpoints ---


@router.post(
    "/feedback/query",
    response_model=List[FeedbackRecord],
    dependencies=[Depends(verify_internal_key)],
)
async def query_feedback(payload: FeedbackQuery) -> List[FeedbackRecord]:
    """Query feedback records with filters for triage automation."""
    match_filter: Dict[str, Any] = {}

    if payload.date_from or payload.date_to:
        date_filter: Dict[str, Any] = {}
        if payload.date_from:
            date_filter["$gte"] = payload.date_from
        if payload.date_to:
            date_filter["$lte"] = payload.date_to
        match_filter["created_at"] = date_filter

    if payload.rating:
        match_filter["rating"] = payload.rating

    if payload.status:
        match_filter["status"] = payload.status

    if payload.ticket_id:
        match_filter["ticket_id"] = payload.ticket_id

    if payload.feedback_ids:
        match_filter["feedback_id"] = {"$in": payload.feedback_ids}

    db = Database.database
    collection = db["message_feedback"]
    cursor = collection.find(match_filter).sort("created_at", -1).limit(payload.limit)
    docs = await cursor.to_list(length=payload.limit)

    logger.info(
        "internal.feedback_query",
        filters=list(match_filter.keys()),
        results=len(docs),
    )

    return [
        FeedbackRecord(
            feedback_id=doc.get("feedback_id"),
            rating=doc.get("rating", ""),
            reason=doc.get("reason"),
            created_at=doc.get("created_at", datetime.utcnow()),
            conversation_id=doc.get("conversation_id", ""),
            message_id=doc.get("message_id", ""),
            user_id=doc.get("user_id", ""),
            context=doc.get("context"),
            ticket_id=doc.get("ticket_id"),
            status=doc.get("status", "new"),
        )
        for doc in docs
    ]


@router.post(
    "/feedback/conversations",
    dependencies=[Depends(verify_internal_key)],
)
async def get_conversations(payload: ConversationQuery) -> Dict[str, Any]:
    """Fetch full conversation threads (messages + artifacts) for triage."""
    db = Database.database
    messages_col = db["messages"]
    artifacts_col = db["artifacts"]

    result: Dict[str, Any] = {}

    for conv_id in payload.conversation_ids:
        # Fetch messages sorted chronologically
        msg_cursor = messages_col.find({"chat_id": conv_id}).sort("created_at", 1)
        messages = await msg_cursor.to_list(length=500)

        conv_data: Dict[str, Any] = {
            "messages": [
                {
                    "id": msg.get("_id", ""),
                    "role": msg.get("role", ""),
                    "content": msg.get("content", ""),
                    "created_at": (
                        msg["created_at"].isoformat()
                        if isinstance(msg.get("created_at"), datetime)
                        else str(msg.get("created_at", ""))
                    ),
                    "metadata": msg.get("metadata"),
                    "model": msg.get("model"),
                }
                for msg in messages
            ],
        }

        if payload.include_artifacts:
            art_cursor = artifacts_col.find({"chat_session_id": conv_id}).sort(
                "created_at", 1
            )
            artifacts = await art_cursor.to_list(length=100)

            conv_data["artifacts"] = [
                {
                    "id": art.get("_id", ""),
                    "type": art.get("type", ""),
                    "title": art.get("title", ""),
                    "content": art.get("content"),
                    "created_at": (
                        art["created_at"].isoformat()
                        if isinstance(art.get("created_at"), datetime)
                        else str(art.get("created_at", ""))
                    ),
                    "expires_at": (
                        art["expires_at"].isoformat()
                        if isinstance(art.get("expires_at"), datetime)
                        else str(art.get("expires_at", ""))
                        if art.get("expires_at")
                        else None
                    ),
                }
                for art in artifacts
            ]

        result[conv_id] = conv_data

    logger.info(
        "internal.conversations_fetched",
        conversation_count=len(payload.conversation_ids),
        total_messages=sum(len(v.get("messages", [])) for v in result.values()),
    )

    return result


# =========================================================================
# Cache Invalidation Endpoints
# =========================================================================


class CacheInvalidationRequest(BaseModel):
    """Request body for cache invalidation."""

    event: str = Field(
        ...,
        description="Invalidation event type: etl_complete, deploy_complete, handler_change",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata (e.g. periodo, handler name, tables loaded)",
    )


class CacheInvalidationResponse(BaseModel):
    status: str
    event: str
    receivers: int


@router.post(
    "/cache/invalidate",
    response_model=CacheInvalidationResponse,
    dependencies=[Depends(verify_internal_key)],
)
async def invalidate_cache(body: CacheInvalidationRequest):
    """Trigger cache invalidation from external sources (ETL, CI/CD).

    Protected by X-Internal-Key header.
    """
    from ..core.cache_invalidation import InvalidationEvent, publish_invalidation
    from ..core.redis_cache import get_redis_cache

    # Validate event type
    try:
        event = InvalidationEvent(body.event)
    except ValueError:
        valid = [e.value for e in InvalidationEvent]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event '{body.event}'. Valid: {valid}",
        )

    cache = await get_redis_cache()
    if not cache.client:
        raise HTTPException(status_code=503, detail="Redis not available")

    receivers = await publish_invalidation(cache.client, event, body.metadata)
    return CacheInvalidationResponse(
        status="published", event=event.value, receivers=receivers
    )


# =========================================================================
# Cache Purge Endpoints
# =========================================================================


class CachePurgeRequest(BaseModel):
    """Request body for manual cache purge."""

    target: str = Field(
        default="all",
        description="Purge target: expired, cold, version, all",
    )
    version_tag: Optional[str] = Field(
        default=None,
        description="Cache version to purge (required when target=version)",
    )


class CachePurgeResponse(BaseModel):
    status: str
    results: Dict[str, int]


@router.post(
    "/cache/purge",
    response_model=CachePurgeResponse,
    dependencies=[Depends(verify_internal_key)],
)
async def purge_cache(body: CachePurgeRequest):
    """Manual cache purge for LLM semantic cache.

    Targets:
    - expired: Remove entries past their TTL
    - cold: Remove zero-hit entries older than 15 days
    - version: Remove all entries for a specific cache version
    - all: Run expired + cold purge

    Protected by X-Internal-Key header.
    """
    import asyncio

    from ..services.llm_semantic_cache import get_llm_semantic_cache

    cache = get_llm_semantic_cache()
    if not cache:
        raise HTTPException(status_code=503, detail="LLM semantic cache not available")

    valid_targets = {"expired", "cold", "version", "all"}
    if body.target not in valid_targets:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target '{body.target}'. Valid: {sorted(valid_targets)}",
        )

    if body.target == "version" and not body.version_tag:
        raise HTTPException(
            status_code=400,
            detail="version_tag is required when target=version",
        )

    results: Dict[str, int] = {}

    if body.target in ("expired", "all"):
        results["expired"] = await asyncio.to_thread(cache.purge_expired)

    if body.target in ("cold", "all"):
        results["cold"] = await asyncio.to_thread(cache.purge_cold)

    if body.target == "version":
        results["version"] = await asyncio.to_thread(
            cache.purge_version, body.version_tag
        )

    logger.info("internal.cache_purge", target=body.target, results=results)
    return CachePurgeResponse(status="purged", results=results)


# =========================================================================
# Cache Stats Endpoint
# =========================================================================


@router.get(
    "/cache/stats",
    dependencies=[Depends(verify_internal_key)],
)
async def cache_stats() -> Dict[str, Any]:
    """Get cache statistics across all layers.

    Returns stats from:
    - extraction: Document extraction cache (Redis-backed, hit/miss counters)
    - mcp_tools: MCP tool result cache (Redis-backed, keyed by tool+document)
    - semantic: LLM semantic response cache (Weaviate-backed, embedding similarity)

    Protected by X-Internal-Key header.
    """
    import asyncio

    from ..services.extractors.cache import get_extraction_cache
    from ..services.llm_semantic_cache import get_llm_semantic_cache
    from ..services.mcp_cache import get_cache_stats

    stats: Dict[str, Any] = {}

    # Extraction cache (sync)
    try:
        extraction_cache = get_extraction_cache()
        stats["extraction"] = extraction_cache.get_metrics()
    except Exception as e:
        stats["extraction"] = {"status": "error", "error": str(e)}

    # MCP tool cache (async)
    try:
        stats["mcp_tools"] = await get_cache_stats()
    except Exception as e:
        stats["mcp_tools"] = {"status": "error", "error": str(e)}

    # LLM semantic cache (sync — run in thread)
    try:
        semantic_cache = get_llm_semantic_cache()
        if semantic_cache:
            stats["semantic"] = await asyncio.to_thread(semantic_cache.get_stats)
        else:
            stats["semantic"] = {"status": "unavailable"}
    except Exception as e:
        stats["semantic"] = {"status": "error", "error": str(e)}

    return stats
