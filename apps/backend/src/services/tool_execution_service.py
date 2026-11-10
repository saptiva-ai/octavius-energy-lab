"""
Tool Execution Service.

This service handles the orchestration and execution of MCP tools
with built-in Redis caching and error handling.

It abstracts the complexity of:
- Tool discovery
- Cache key generation
- TTL management
- Error resilience
"""

import asyncio
import hashlib
import json
from typing import Any, Dict, Optional, Tuple

import structlog
from redis.exceptions import RedisError

from ..core.constants import (
    TOOL_NAME_EXCEL,
    TOOL_NAME_EXTRACT,
    TOOL_NAME_RESEARCH,
)
from ..core.redis_cache import get_redis_cache
from ..domain.chat_context import ChatContext
from ..mcp_integration import get_mcp_adapter

logger = structlog.get_logger(__name__)

# TTL configuration for each tool (in seconds)
TOOL_CACHE_TTL = {
    TOOL_NAME_EXCEL: 1800,  # 30 min (data might update)
    TOOL_NAME_RESEARCH: 86400,  # 24 hours (research is expensive)
    TOOL_NAME_EXTRACT: 3600,  # 1 hour (text is stable)
}


class ToolExecutionService:
    """Service for executing MCP tools with caching strategies."""

    @classmethod
    async def build_domain_analytics_context(
        cls, context: ChatContext
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Pre-fetch genérico del plugin de dominio (retail-advisor) para el system prompt.

        Se activa cuando el request habilita el tool (`tools_enabled`). Reenvía el
        mensaje crudo al plugin, que resuelve el dominio (el backend no parsea — regla #1).
        Fail-safe: si el plugin no está disponible o no hay dato, devuelve (None, None) y
        el chat sigue normal.

        Returns:
            Tupla (bloque markdown para el system prompt, dict crudo AnalyticsResponse
            del plugin para adjuntar a metadata/canvas). Cualquiera puede ser None.
        """
        tools_enabled = context.tools_enabled or {}
        if not (
            tools_enabled.get("retail_advisor") or tools_enabled.get("retail-advisor")
        ):
            return None, None

        try:
            # Import perezoso para evitar coste/ciclos en import-time.
            from ..mcp_integration.clients.domain_tools import DomainToolProvider
            from .perfil_usuario import ambito_de_usuario

            provider = DomainToolProvider()
            data = await provider.fetch_analytics(
                context.message,
                ambito=await ambito_de_usuario(getattr(context, "user_id", None)),
            )
        except Exception as exc:  # noqa: BLE001 — fail-safe, no romper el chat
            logger.warning("domain_analytics.unavailable", error=str(exc))
            return None, None

        if not data or data.get("error"):
            logger.info(
                "domain_analytics.no_data",
                has_data=bool(data),
                error=(data or {}).get("error"),
            )
            return None, None

        return DomainToolProvider.format_analytics_block(data), data

    @staticmethod
    def _generate_cache_key(tool_name: str, doc_id: str, params: Dict = None) -> str:
        """
        Generate unique cache key for tool result.
        Format: mcp:tool:{tool_name}:{doc_id}:{params_hash}
        """
        if params:
            # Create deterministic hash of params
            params_str = json.dumps(params, sort_keys=True)
            params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
            return f"mcp:tool:{tool_name}:{doc_id}:{params_hash}"
        return f"mcp:tool:{tool_name}:{doc_id}"

    @classmethod
    async def _execute_tool_with_cache(
        cls,
        tool_name: str,
        doc_id: str,
        user_id: str,
        payload: Dict[str, Any],
        cache_params: Dict[str, Any],
        tool_map: Dict[str, Any],
        mcp_adapter: Any,
        cache: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Generic method to execute a tool with Redis caching.

        Args:
            tool_name: Name of the tool to execute
            doc_id: ID of the document being processed
            user_id: ID of the user invoking the tool
            payload: Full payload to send to the tool
            cache_params: Parameters used to generate the cache key
            tool_map: Map of available tools
            mcp_adapter: Adapter to execute the tool
            cache: Redis cache instance

        Returns:
            The tool result dict or None if execution failed
        """
        try:
            # Generate cache key
            cache_key = cls._generate_cache_key(tool_name, doc_id, cache_params)

            # Try to get from cache first
            cached_result = None
            if cache:
                try:
                    cached_result = await cache.get(cache_key)
                    if cached_result:
                        logger.info(
                            f"{tool_name} result loaded from cache",
                            doc_id=doc_id,
                            cache_hit=True,
                        )
                        return cached_result
                except RedisError as redis_err:
                    logger.warning(
                        "Failed to read from cache",
                        cache_key=cache_key,
                        error=str(redis_err),
                    )

            # Execute tool
            logger.info(
                f"Invoking {tool_name} tool",
                doc_id=doc_id,
                user_id=user_id,
                cache_hit=False,
            )

            tool_impl = tool_map[tool_name]
            result = await mcp_adapter.execute_tool(
                tool_name=tool_name,
                tool_impl=tool_impl,
                payload={
                    "doc_id": str(doc_id),
                    "user_id": str(user_id),
                    "policy_id": "auto",
                },
                context=None,
            )

            # Store in cache
            if cache:
                try:
                    ttl = TOOL_CACHE_TTL.get(tool_name, 3600)
                    await cache.set(cache_key, result, expire=ttl)
                    logger.debug(
                        f"Cached {tool_name} result", cache_key=cache_key, ttl=ttl
                    )
                except RedisError as redis_err:
                    logger.warning(
                        f"Failed to cache {tool_name} result",
                        cache_key=cache_key,
                        error=str(redis_err),
                    )

            return result

        except Exception as e:
            logger.warning(
                f"{tool_name} tool failed",
                doc_id=doc_id,
                error=str(e),
                exc_type=type(e).__name__,
            )
            return None

    @classmethod
    async def invoke_relevant_tools(cls, context: ChatContext, user_id: str) -> Dict:
        """
        Invoke relevant MCP tools based on context and return results.
        """
        results = {}

        # Get Redis cache
        try:
            cache = await get_redis_cache()
        except RedisError as redis_err:
            logger.warning(
                "Failed to get Redis cache for tool results",
                error=str(redis_err),
                exc_type=type(redis_err).__name__,
            )
            cache = None

        # Skip if no tools enabled
        if not context.tools_enabled or not any(context.tools_enabled.values()):
            logger.debug("No tools enabled, skipping tool invocation")
            return results

        # Skip if no documents attached
        if not context.document_ids:
            logger.debug("No documents attached, skipping tool invocation")
            return results

        try:
            # Get MCP adapter for internal tool invocation
            mcp_adapter = get_mcp_adapter()
            tool_map = await mcp_adapter.get_tool_map()

            logger.info(
                "Checking tool execution conditions",
                tools_enabled_keys=list(context.tools_enabled.keys()),
                tool_map_keys=list(tool_map.keys()),
                document_ids=context.document_ids,
            )

            # Excel Analyzer Tool - Parallel Execution
            # Uses asyncio.gather for 5-10x speedup on multi-document chats
            if (
                context.tools_enabled.get(TOOL_NAME_EXCEL, False)
                and TOOL_NAME_EXCEL in tool_map
            ):
                from ..models.document import Document

                async def process_excel_document(
                    doc_id: str,
                ) -> Tuple[str, Optional[Dict[str, Any]]]:
                    """
                    Process a single document for Excel analysis.

                    Returns tuple of (doc_id, result) where result is None if
                    document is not Excel or processing failed.
                    """
                    try:
                        doc = await Document.get(doc_id)
                        if not doc or str(doc.user_id) != user_id:
                            return (doc_id, None)

                        is_excel = doc.content_type in [
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            "application/vnd.ms-excel",
                        ]

                        if not is_excel:
                            return (doc_id, None)

                        excel_result = await cls._execute_tool_with_cache(
                            tool_name=TOOL_NAME_EXCEL,
                            doc_id=doc_id,
                            user_id=user_id,
                            payload={
                                "doc_id": doc_id,
                                "operations": ["stats", "preview"],
                                "user_id": user_id,
                            },
                            cache_params={"operations": ["stats", "preview"]},
                            tool_map=tool_map,
                            mcp_adapter=mcp_adapter,
                            cache=cache,
                        )

                        if excel_result:
                            logger.info(
                                f"{TOOL_NAME_EXCEL} tool succeeded", doc_id=doc_id
                            )
                            return (doc_id, excel_result)

                        return (doc_id, None)

                    except Exception as e:
                        logger.warning(
                            f"Error checking document for {TOOL_NAME_EXCEL}",
                            doc_id=doc_id,
                            error=str(e),
                        )
                        return (doc_id, None)

                # Execute all document checks in parallel
                parallel_results = await asyncio.gather(
                    *[
                        process_excel_document(doc_id)
                        for doc_id in context.document_ids
                    ],
                    return_exceptions=True,
                )

                # Collect successful results
                for result in parallel_results:
                    if isinstance(result, Exception):
                        logger.warning(
                            "Parallel excel processing error",
                            error=str(result),
                        )
                        continue
                    doc_id, excel_result = result
                    if excel_result:
                        results[f"{TOOL_NAME_EXCEL}_{doc_id}"] = excel_result

            logger.info(
                "Tool invocation completed",
                tools_executed=len(results),
                user_id=user_id,
            )

        except Exception as e:
            logger.error(
                "Failed to invoke tools",
                error=str(e),
                exc_type=type(e).__name__,
                exc_info=True,
            )
            # Return empty results on error

        return results
