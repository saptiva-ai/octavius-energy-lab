"""
MCP Admin Routes - Cache management and tool administration.

Provides endpoints for:
- Cache invalidation (by document, tool, or all)
- Cache statistics
- Cache warmup (pre-population)
"""

from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.auth import get_current_user
from ..models.user import User
from ..services.mcp_cache import (
    get_cache_stats,
    invalidate_all_tool_caches,
    invalidate_document_tool_cache,
    invalidate_tool_cache,
    warmup_tool_cache,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.delete("/cache/tool/{tool_name}/{doc_id}", tags=["mcp-admin"])
async def invalidate_specific_tool_cache(
    tool_name: str, doc_id: str, current_user: User = Depends(get_current_user)
):
    """
    Invalidate cache for a specific tool and document.

    Args:
        tool_name: Name of the MCP tool (e.g., "audit_file")
        doc_id: Document ID

    Returns:
        Success status
    """
    logger.info(
        "Cache invalidation requested",
        tool_name=tool_name,
        doc_id=doc_id,
        user_id=str(current_user.id),
    )

    deleted = await invalidate_tool_cache(tool_name, doc_id)

    return {
        "success": True,
        "message": f"Cache invalidated for {tool_name} on {doc_id}",
        "deleted": deleted,
    }


@router.delete("/cache/document/{doc_id}", tags=["mcp-admin"])
async def invalidate_document_cache(
    doc_id: str,
    tool_name: Optional[str] = Query(None, description="Optional tool name filter"),
    current_user: User = Depends(get_current_user),
):
    """
    Invalidate all tool caches for a document.

    Args:
        doc_id: Document ID
        tool_name: Optional tool name to filter (if None, invalidates all tools)

    Returns:
        Number of cache keys deleted
    """
    logger.info(
        "Document cache invalidation requested",
        doc_id=doc_id,
        tool_name=tool_name,
        user_id=str(current_user.id),
    )

    deleted_count = await invalidate_document_tool_cache(doc_id, tool_name)

    return {
        "success": True,
        "message": f"Invalidated {deleted_count} cache entries for document {doc_id}",
        "deleted_count": deleted_count,
    }


@router.delete("/cache/all", tags=["mcp-admin"])
async def invalidate_all_cache(
    tool_name: Optional[str] = Query(None, description="Optional tool name filter"),
    confirm: bool = Query(False, description="Confirmation required for safety"),
    current_user: User = Depends(get_current_user),
):
    """
    Invalidate all tool caches (DESTRUCTIVE - requires confirmation).

    Args:
        tool_name: Optional tool name to filter (if None, invalidates ALL caches)
        confirm: Must be true to execute (safety check)

    Returns:
        Number of cache keys deleted
    """
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required. Set confirm=true to proceed.",
        )

    logger.warning(
        "All cache invalidation requested",
        tool_name=tool_name,
        user_id=str(current_user.id),
    )

    deleted_count = await invalidate_all_tool_caches(tool_name)

    return {
        "success": True,
        "message": f"Invalidated {deleted_count} cache entries",
        "deleted_count": deleted_count,
        "tool_name": tool_name or "all",
    }


@router.get("/cache/stats", tags=["mcp-admin"])
async def get_cache_statistics(
    doc_id: Optional[str] = Query(None, description="Optional document ID filter"),
    current_user: User = Depends(get_current_user),
):
    """
    Get statistics about tool result caches.

    Args:
        doc_id: Optional document ID to filter stats

    Returns:
        Cache statistics with counts by tool and document
    """
    stats = await get_cache_stats(doc_id)

    return {"success": True, "stats": stats}


@router.post("/cache/warmup", tags=["mcp-admin"])
async def warmup_cache(
    tool_name: str = Query(..., description="Tool name to execute"),
    doc_ids: List[str] = Query(..., description="List of document IDs"),
    current_user: User = Depends(get_current_user),
):
    """
    Pre-populate cache with tool results for multiple documents.

    Useful for batch processing or preparing for high-traffic periods.

    Args:
        tool_name: Name of the MCP tool
        doc_ids: List of document IDs to process

    Returns:
        Summary of cached and failed documents
    """
    logger.info(
        "Cache warmup requested",
        tool_name=tool_name,
        doc_count=len(doc_ids),
        user_id=str(current_user.id),
    )

    results = await warmup_tool_cache(
        tool_name=tool_name, doc_ids=doc_ids, user_id=str(current_user.id)
    )

    return {
        "success": True,
        "message": f"Warmed up cache for {results['cached']} documents",
        "results": results,
    }
