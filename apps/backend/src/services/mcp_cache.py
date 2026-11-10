"""
MCP Tool Results Cache Management.

Provides utilities for caching and invalidating MCP tool results in Redis.

Features:
- Cache key generation
- Cache invalidation by document, tool, or pattern
- Bulk cache operations
- TTL configuration per tool

Usage:
    from src.services.mcp_cache import invalidate_tool_cache, invalidate_document_tool_cache

    # Invalidate all tool results for a document
    await invalidate_document_tool_cache("doc_123")

    # Invalidate specific tool results for a document
    await invalidate_tool_cache("audit_file", "doc_123")
"""

import hashlib
import json
from typing import List, Optional

import structlog

from ..core.redis_cache import get_redis_cache

logger = structlog.get_logger(__name__)

# TTL configuration for each tool (in seconds)
TOOL_CACHE_TTL = {
    "audit_file": 3600,  # 1 hour (findings don't change frequently)
    "excel_analyzer": 1800,  # 30 min (data might update)
    "deep_research": 86400,  # 24 hours (research is expensive)
    "extract_document_text": 3600,  # 1 hour (text is stable)
}


def generate_cache_key(
    tool_name: str, doc_id: str, params: Optional[dict] = None
) -> str:
    """
    Generate unique cache key for tool result.

    Args:
        tool_name: Name of the MCP tool
        doc_id: Document ID
        params: Optional parameters dict (will be hashed)

    Returns:
        Cache key in format: mcp:tool:{tool_name}:{doc_id}[:{params_hash}]

    Examples:
        >>> generate_cache_key("audit_file", "doc_123")
        'mcp:tool:audit_file:doc_123'

        >>> generate_cache_key("audit_file", "doc_123", {"policy_id": "auto"})
        'mcp:tool:audit_file:doc_123:a1b2c3d4'
    """
    if params:
        # Create deterministic hash of params
        params_str = json.dumps(params, sort_keys=True)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
        return f"mcp:tool:{tool_name}:{doc_id}:{params_hash}"
    return f"mcp:tool:{tool_name}:{doc_id}"


async def invalidate_tool_cache(
    tool_name: str, doc_id: str, params: Optional[dict] = None
) -> bool:
    """
    Invalidate cache for a specific tool result.

    Args:
        tool_name: Name of the MCP tool
        doc_id: Document ID
        params: Optional parameters (must match original params)

    Returns:
        True if cache was invalidated, False otherwise

    Example:
        >>> await invalidate_tool_cache("audit_file", "doc_123", {"policy_id": "auto"})
        True
    """
    try:
        cache = await get_redis_cache()
        cache_key = generate_cache_key(tool_name, doc_id, params)

        deleted = await cache.client.delete(cache_key)

        if deleted:
            logger.info(
                "Invalidated tool cache",
                tool_name=tool_name,
                doc_id=doc_id,
                cache_key=cache_key,
            )
        else:
            logger.debug(
                "No cache to invalidate",
                tool_name=tool_name,
                doc_id=doc_id,
                cache_key=cache_key,
            )

        return bool(deleted)

    except Exception as e:
        logger.error(
            "Failed to invalidate tool cache",
            tool_name=tool_name,
            doc_id=doc_id,
            error=str(e),
            exc_type=type(e).__name__,
            exc_info=True,
        )
        return False


async def invalidate_document_tool_cache(
    doc_id: str, tool_name: Optional[str] = None
) -> int:
    """
    Invalidate all tool caches for a document (or specific tool).

    Args:
        doc_id: Document ID
        tool_name: Optional tool name (if None, invalidates all tools for document)

    Returns:
        Number of cache keys deleted

    Example:
        >>> # Invalidate all tool results for a document
        >>> await invalidate_document_tool_cache("doc_123")
        3  # deleted audit_file, excel_analyzer, and extract_document_text caches

        >>> # Invalidate only audit_file results
        >>> await invalidate_document_tool_cache("doc_123", "audit_file")
        1
    """
    try:
        cache = await get_redis_cache()

        # Build pattern for scan
        if tool_name:
            pattern = f"mcp:tool:{tool_name}:{doc_id}*"
        else:
            pattern = f"mcp:tool:*:{doc_id}*"

        # Scan for matching keys and delete
        keys = await cache._scan_keys(pattern)
        deleted_count = 0
        if keys:
            deleted_count = await cache.client.delete(*keys)

        if deleted_count > 0:
            logger.info(
                "Invalidated document tool caches",
                doc_id=doc_id,
                tool_name=tool_name or "all",
                deleted_count=deleted_count,
            )
        else:
            logger.debug(
                "No document tool caches to invalidate",
                doc_id=doc_id,
                tool_name=tool_name or "all",
            )

        return deleted_count

    except Exception as e:
        logger.error(
            "Failed to invalidate document tool caches",
            doc_id=doc_id,
            tool_name=tool_name,
            error=str(e),
            exc_type=type(e).__name__,
            exc_info=True,
        )
        return 0


async def invalidate_all_tool_caches(tool_name: Optional[str] = None) -> int:
    """
    Invalidate all tool caches (optionally for a specific tool).

    WARNING: This is a destructive operation. Use with caution.

    Args:
        tool_name: Optional tool name (if None, invalidates ALL tool caches)

    Returns:
        Number of cache keys deleted

    Example:
        >>> # Invalidate all audit_file caches across all documents
        >>> await invalidate_all_tool_caches("audit_file")
        42

        >>> # Invalidate ALL tool caches (DANGEROUS!)
        >>> await invalidate_all_tool_caches()
        150
    """
    try:
        cache = await get_redis_cache()

        # Build pattern for scan
        if tool_name:
            pattern = f"mcp:tool:{tool_name}:*"
        else:
            pattern = "mcp:tool:*"

        # Use RedisCache._scan_keys + client.delete (delete_pattern doesn't return count)
        keys = await cache._scan_keys(pattern)
        deleted_count = 0
        if keys:
            deleted_count = await cache.client.delete(*keys)

        logger.warning(
            "Invalidated all tool caches",
            tool_name=tool_name or "all",
            deleted_count=deleted_count,
        )

        return deleted_count

    except Exception as e:
        logger.error(
            "Failed to invalidate all tool caches",
            tool_name=tool_name,
            error=str(e),
            exc_type=type(e).__name__,
            exc_info=True,
        )
        return 0


async def get_cache_stats(doc_id: Optional[str] = None) -> dict:
    """
    Get statistics about tool result caches.

    Args:
        doc_id: Optional document ID to filter stats

    Returns:
        Dict with cache statistics:
        {
            "total_keys": 42,
            "by_tool": {"audit_file": 15, "excel_analyzer": 10, ...},
            "by_document": {"doc_123": 3, "doc_456": 2, ...}
        }
    """
    try:
        cache = await get_redis_cache()

        # Build pattern
        if doc_id:
            pattern = f"mcp:tool:*:{doc_id}*"
        else:
            pattern = "mcp:tool:*"

        # Scan for keys
        keys = await cache._scan_keys(pattern)

        # Parse keys to extract tool and document info
        by_tool = {}
        by_document = {}

        for key in keys:
            # Key format: mcp:tool:{tool_name}:{doc_id}[:{params_hash}]
            parts = key.split(":")
            if len(parts) >= 4:
                tool_name = parts[2]
                doc_id_part = parts[3]

                # Count by tool
                by_tool[tool_name] = by_tool.get(tool_name, 0) + 1

                # Count by document
                by_document[doc_id_part] = by_document.get(doc_id_part, 0) + 1

        stats = {
            "total_keys": len(keys),
            "by_tool": by_tool,
            "by_document": by_document,
        }

        logger.debug("Retrieved cache stats", **stats)

        return stats

    except Exception as e:
        logger.error(
            "Failed to get cache stats", error=str(e), exc_type=type(e).__name__
        )
        return {"total_keys": 0, "by_tool": {}, "by_document": {}, "error": str(e)}


async def warmup_tool_cache(
    tool_name: str, doc_ids: List[str], user_id: str, params: Optional[dict] = None
) -> dict:
    """
    Pre-populate cache with tool results for multiple documents.

    Useful for batch processing or background jobs.

    Args:
        tool_name: Name of the MCP tool
        doc_ids: List of document IDs
        user_id: User ID for tool execution
        params: Optional parameters for tool

    Returns:
        Dict with results:
        {
            "cached": 5,
            "failed": 1,
            "errors": ["doc_789: Tool execution failed"]
        }
    """
    from ..mcp_integration import get_mcp_adapter

    results = {"cached": 0, "failed": 0, "errors": []}

    try:
        cache = await get_redis_cache()
        mcp_adapter = get_mcp_adapter()
        tool_map = await mcp_adapter.get_tool_map()

        if tool_name not in tool_map:
            raise ValueError(f"Tool '{tool_name}' not found in registry")

        tool_impl = tool_map[tool_name]

        for doc_id in doc_ids:
            try:
                # Generate cache key
                cache_key = generate_cache_key(tool_name, doc_id, params)

                # Check if already cached
                existing = await cache.get(cache_key)
                if existing:
                    logger.debug(
                        "Tool result already cached, skipping",
                        tool_name=tool_name,
                        doc_id=doc_id,
                    )
                    results["cached"] += 1
                    continue

                # Execute tool
                payload = {"doc_id": doc_id, "user_id": user_id, **(params or {})}
                tool_result = await mcp_adapter.execute_tool(
                    tool_name=tool_name, tool_impl=tool_impl, payload=payload
                )

                # Store in cache
                ttl = TOOL_CACHE_TTL.get(tool_name, 3600)
                await cache.set(cache_key, tool_result, expire=ttl)

                results["cached"] += 1
                logger.info(
                    "Warmed up tool cache",
                    tool_name=tool_name,
                    doc_id=doc_id,
                    cache_key=cache_key,
                )

            except Exception as e:
                results["failed"] += 1
                error_msg = f"{doc_id}: {str(e)}"
                results["errors"].append(error_msg)
                logger.warning(
                    "Failed to warmup cache for document",
                    tool_name=tool_name,
                    doc_id=doc_id,
                    error=str(e),
                )

    except Exception as e:
        logger.error(
            "Cache warmup failed",
            tool_name=tool_name,
            error=str(e),
            exc_type=type(e).__name__,
            exc_info=True,
        )
        results["errors"].append(f"Warmup failed: {str(e)}")

    return results
