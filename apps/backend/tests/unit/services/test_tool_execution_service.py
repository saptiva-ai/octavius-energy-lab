"""Unit tests for the MCP tool execution orchestration service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import RedisError

from src.core.constants import TOOL_NAME_EXCEL
from src.services.tool_execution_service import (
    TOOL_CACHE_TTL,
    ToolExecutionService,
)

pytestmark = [pytest.mark.unit]


def _context(
    *,
    tools_enabled: dict[str, bool] | None = None,
    document_ids: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        message="Compara el faltante por tienda",
        tools_enabled=tools_enabled or {},
        document_ids=document_ids,
    )


class TestBuildDomainAnalyticsContext:
    @pytest.mark.asyncio
    async def test_skips_when_retail_tool_is_disabled(self):
        result = await ToolExecutionService.build_domain_analytics_context(
            _context(tools_enabled={"other_tool": True})
        )

        assert result == (None, None)

    @pytest.mark.asyncio
    async def test_returns_formatted_block_and_raw_analytics(self):
        analytics = {
            "metric_name": "faltante",
            "visualization": {"task": "comparison"},
        }

        with patch(
            "src.mcp_integration.clients.domain_tools.DomainToolProvider"
        ) as provider_class:
            provider_class.return_value.fetch_analytics = AsyncMock(
                return_value=analytics
            )
            provider_class.format_analytics_block.return_value = "## Analytics"

            result = await ToolExecutionService.build_domain_analytics_context(
                _context(tools_enabled={"retail-advisor": True})
            )

        assert result == ("## Analytics", analytics)
        # El ámbito del perfil viaja en cada llamada de datos desde T3; sin
        # usuario resuelto es None y la consulta corre sin restricción.
        provider_class.return_value.fetch_analytics.assert_awaited_once_with(
            "Compara el faltante por tienda", ambito=None
        )
        provider_class.format_analytics_block.assert_called_once_with(analytics)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("analytics", [None, {"error": "sin datos"}])
    async def test_returns_empty_context_when_provider_has_no_usable_data(
        self, analytics
    ):
        with patch(
            "src.mcp_integration.clients.domain_tools.DomainToolProvider"
        ) as provider_class:
            provider_class.return_value.fetch_analytics = AsyncMock(
                return_value=analytics
            )

            result = await ToolExecutionService.build_domain_analytics_context(
                _context(tools_enabled={"retail_advisor": True})
            )

        assert result == (None, None)

    @pytest.mark.asyncio
    async def test_fails_safe_when_provider_is_unavailable(self):
        with patch(
            "src.mcp_integration.clients.domain_tools.DomainToolProvider"
        ) as provider_class:
            provider_class.return_value.fetch_analytics = AsyncMock(
                side_effect=RuntimeError("unavailable")
            )

            result = await ToolExecutionService.build_domain_analytics_context(
                _context(tools_enabled={"retail_advisor": True})
            )

        assert result == (None, None)


class TestExecuteToolWithCache:
    def test_cache_key_is_deterministic_and_parameter_sensitive(self):
        first = ToolExecutionService._generate_cache_key(
            "tool", "doc-1", {"b": 2, "a": 1}
        )
        same = ToolExecutionService._generate_cache_key(
            "tool", "doc-1", {"a": 1, "b": 2}
        )

        assert first == same
        assert first != ToolExecutionService._generate_cache_key("tool", "doc-1")

    @pytest.mark.asyncio
    async def test_returns_cached_result_without_invoking_tool(self):
        cache = AsyncMock()
        cache.get.return_value = {"cached": True}
        adapter = MagicMock()
        adapter.execute_tool = AsyncMock()

        result = await ToolExecutionService._execute_tool_with_cache(
            tool_name=TOOL_NAME_EXCEL,
            doc_id="doc-1",
            user_id="user-1",
            payload={},
            cache_params={"operations": ["stats"]},
            tool_map={TOOL_NAME_EXCEL: object()},
            mcp_adapter=adapter,
            cache=cache,
        )

        assert result == {"cached": True}
        adapter.execute_tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_executes_and_caches_result_after_cache_miss(self):
        cache = AsyncMock()
        cache.get.return_value = None
        adapter = MagicMock()
        adapter.execute_tool = AsyncMock(return_value={"rows": 3})
        tool_impl = object()

        result = await ToolExecutionService._execute_tool_with_cache(
            tool_name=TOOL_NAME_EXCEL,
            doc_id="doc-1",
            user_id="user-1",
            payload={},
            cache_params={"operations": ["stats", "preview"]},
            tool_map={TOOL_NAME_EXCEL: tool_impl},
            mcp_adapter=adapter,
            cache=cache,
        )

        assert result == {"rows": 3}
        adapter.execute_tool.assert_awaited_once_with(
            tool_name=TOOL_NAME_EXCEL,
            tool_impl=tool_impl,
            payload={
                "doc_id": "doc-1",
                "user_id": "user-1",
                "policy_id": "auto",
            },
            context=None,
        )
        cache.set.assert_awaited_once()
        assert cache.set.await_args.kwargs["expire"] == TOOL_CACHE_TTL[TOOL_NAME_EXCEL]

    @pytest.mark.asyncio
    async def test_redis_failures_do_not_block_tool_execution(self):
        cache = AsyncMock()
        cache.get.side_effect = RedisError("read failed")
        cache.set.side_effect = RedisError("write failed")
        adapter = MagicMock()
        adapter.execute_tool = AsyncMock(return_value={"rows": 1})

        result = await ToolExecutionService._execute_tool_with_cache(
            tool_name="custom_tool",
            doc_id="doc-1",
            user_id="user-1",
            payload={},
            cache_params={},
            tool_map={"custom_tool": object()},
            mcp_adapter=adapter,
            cache=cache,
        )

        assert result == {"rows": 1}
        assert cache.set.await_args.kwargs["expire"] == 3600

    @pytest.mark.asyncio
    async def test_returns_none_when_tool_execution_fails(self):
        adapter = MagicMock()
        adapter.execute_tool = AsyncMock(side_effect=RuntimeError("tool failed"))

        result = await ToolExecutionService._execute_tool_with_cache(
            tool_name="custom_tool",
            doc_id="doc-1",
            user_id="user-1",
            payload={},
            cache_params={},
            tool_map={"custom_tool": object()},
            mcp_adapter=adapter,
            cache=None,
        )

        assert result is None


class TestInvokeRelevantTools:
    @pytest.mark.asyncio
    async def test_skips_when_no_tools_are_enabled(self):
        with patch(
            "src.services.tool_execution_service.get_redis_cache",
            new=AsyncMock(side_effect=RedisError("offline")),
        ):
            result = await ToolExecutionService.invoke_relevant_tools(
                _context(document_ids=["doc-1"]), "user-1"
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_processes_owned_excel_documents_in_parallel(self):
        cache = AsyncMock()
        adapter = MagicMock()
        adapter.get_tool_map = AsyncMock(return_value={TOOL_NAME_EXCEL: object()})
        document = SimpleNamespace(
            user_id="user-1",
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

        with (
            patch(
                "src.services.tool_execution_service.get_redis_cache",
                new=AsyncMock(return_value=cache),
            ),
            patch(
                "src.services.tool_execution_service.get_mcp_adapter",
                return_value=adapter,
            ),
            patch(
                "src.models.document.Document.get",
                new=AsyncMock(return_value=document),
            ),
            patch.object(
                ToolExecutionService,
                "_execute_tool_with_cache",
                new=AsyncMock(return_value={"summary": "ok"}),
            ) as execute,
        ):
            result = await ToolExecutionService.invoke_relevant_tools(
                _context(
                    tools_enabled={TOOL_NAME_EXCEL: True},
                    document_ids=["doc-1"],
                ),
                "user-1",
            )

        assert result == {f"{TOOL_NAME_EXCEL}_doc-1": {"summary": "ok"}}
        execute.assert_awaited_once()
