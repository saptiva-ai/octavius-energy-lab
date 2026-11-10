"""
Unit tests for DeepResearchTool - Aletheia Integration.

Tests multi-step research task creation and management.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.mcp_integration.tools.deep_research_tool import DeepResearchTool
from src.mcp_integration.protocol import ToolCategory, ToolCapability


@pytest.fixture
def research_tool():
    """Create DeepResearchTool instance."""
    return DeepResearchTool()


class TestDeepResearchToolSpec:
    """Tests for DeepResearchTool specification."""

    def test_get_spec_returns_tool_spec(self, research_tool):
        """Test get_spec returns valid ToolSpec."""
        spec = research_tool.get_spec()

        assert spec.name == "deep_research"
        assert spec.version == "1.0.0"
        assert spec.display_name == "Deep Research (Aletheia)"
        assert spec.category == ToolCategory.RESEARCH

    def test_spec_capabilities(self, research_tool):
        """Test tool capabilities are correct."""
        spec = research_tool.get_spec()

        assert ToolCapability.ASYNC in spec.capabilities
        assert ToolCapability.STREAMING in spec.capabilities
        assert ToolCapability.STATEFUL in spec.capabilities

    def test_spec_input_schema(self, research_tool):
        """Test input schema structure."""
        spec = research_tool.get_spec()
        schema = spec.input_schema

        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "depth" in schema["properties"]
        assert "focus_areas" in schema["properties"]
        assert "max_iterations" in schema["properties"]
        assert "query" in schema["required"]

    def test_spec_depth_options(self, research_tool):
        """Test depth enum values."""
        spec = research_tool.get_spec()
        depth_enum = spec.input_schema["properties"]["depth"]["enum"]

        assert "shallow" in depth_enum
        assert "medium" in depth_enum
        assert "deep" in depth_enum

    def test_spec_rate_limit(self, research_tool):
        """Test rate limit is conservative (research is expensive)."""
        spec = research_tool.get_spec()

        assert spec.rate_limit["calls_per_minute"] == 5

    def test_spec_timeout(self, research_tool):
        """Test timeout is 5 minutes for deep research."""
        spec = research_tool.get_spec()

        assert spec.timeout_ms == 300000

    def test_spec_output_schema(self, research_tool):
        """Test output schema contains expected fields."""
        spec = research_tool.get_spec()
        output = spec.output_schema

        assert "task_id" in output["properties"]
        assert "status" in output["properties"]
        assert "summary" in output["properties"]
        assert "findings" in output["properties"]
        assert "sources" in output["properties"]


class TestDeepResearchToolValidateInput:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_valid_input_minimal(self, research_tool):
        """Test valid input with only required field."""
        payload = {"query": "What is machine learning?"}

        # Should not raise
        await research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_valid_input_full(self, research_tool):
        """Test valid input with all fields."""
        payload = {
            "query": "Renewable energy trends",
            "depth": "deep",
            "focus_areas": ["solar", "wind"],
            "max_iterations": 5,
            "include_sources": True,
        }

        # Should not raise
        await research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_missing_query(self, research_tool):
        """Test validation fails without query."""
        payload = {"depth": "medium"}

        with pytest.raises(ValueError, match="Missing required field: query"):
            await research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_query_not_string(self, research_tool):
        """Test validation fails if query is not a string."""
        payload = {"query": 123}

        with pytest.raises(ValueError, match="query must be a string"):
            await research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_empty_query(self, research_tool):
        """Test validation fails for empty query."""
        payload = {"query": "   "}

        with pytest.raises(ValueError, match="query cannot be empty"):
            await research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_invalid_depth(self, research_tool):
        """Test validation fails for invalid depth."""
        payload = {"query": "Test", "depth": "invalid"}

        with pytest.raises(ValueError, match="Invalid depth"):
            await research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_max_iterations_not_integer(self, research_tool):
        """Test validation fails if max_iterations is not integer."""
        payload = {"query": "Test", "max_iterations": "five"}

        with pytest.raises(ValueError, match="max_iterations must be an integer"):
            await research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_max_iterations_too_low(self, research_tool):
        """Test validation fails if max_iterations < 1."""
        payload = {"query": "Test", "max_iterations": 0}

        with pytest.raises(ValueError, match="max_iterations must be an integer between 1 and 10"):
            await research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_max_iterations_too_high(self, research_tool):
        """Test validation fails if max_iterations > 10."""
        payload = {"query": "Test", "max_iterations": 15}

        with pytest.raises(ValueError, match="max_iterations must be an integer between 1 and 10"):
            await research_tool.validate_input(payload)


class TestDeepResearchToolExecute:
    """Tests for tool execution."""

    @pytest.fixture
    def mock_task_pending(self):
        """Create mock pending task."""
        from src.models.task import TaskStatus

        task = MagicMock()
        task.id = "task-123"
        task.status = TaskStatus.PENDING
        task.created_at = datetime(2025, 1, 15, 10, 0, 0)
        task.completed_at = None
        task.result = None
        task.error_message = None
        return task

    @pytest.fixture
    def mock_task_completed(self):
        """Create mock completed task."""
        from src.models.task import TaskStatus

        task = MagicMock()
        task.id = "task-456"
        task.status = TaskStatus.COMPLETED
        task.created_at = datetime(2025, 1, 15, 10, 0, 0)
        task.completed_at = datetime(2025, 1, 15, 10, 5, 0)
        task.result = {
            "summary": "Research summary here",
            "findings": [
                {"topic": "Topic 1", "content": "Finding 1", "confidence": 0.9}
            ],
            "sources": [
                {"url": "https://example.com", "title": "Source 1", "relevance": 0.8}
            ],
            "iterations_completed": 3,
            "total_duration_ms": 300000,
            "tokens_used": 5000,
        }
        task.error_message = None
        return task

    @pytest.fixture
    def mock_task_failed(self):
        """Create mock failed task."""
        from src.models.task import TaskStatus

        task = MagicMock()
        task.id = "task-789"
        task.status = TaskStatus.FAILED
        task.created_at = datetime(2025, 1, 15, 10, 0, 0)
        task.completed_at = None
        task.result = None
        task.error_message = "API rate limit exceeded"
        return task

    @pytest.mark.asyncio
    async def test_execute_creates_pending_task(self, research_tool, mock_task_pending):
        """Test execution creates research task."""
        payload = {"query": "What are AI trends?"}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task_pending,
        ):
            result = await research_tool.execute(
                payload, context={"user_id": "user-123", "chat_id": "chat-456"}
            )

        assert result["task_id"] == "task-123"
        assert result["status"] == "pending"
        assert result["query"] == "What are AI trends?"
        assert result["iterations_completed"] == 0
        assert result["metadata"]["max_iterations"] == 3  # Default medium depth

    @pytest.mark.asyncio
    async def test_execute_depth_shallow(self, research_tool, mock_task_pending):
        """Test shallow depth maps to 2 iterations."""
        payload = {"query": "Quick research", "depth": "shallow"}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task_pending,
        ) as mock_create:
            await research_tool.execute(payload, context={})

            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["max_iterations"] == 2

    @pytest.mark.asyncio
    async def test_execute_depth_medium(self, research_tool, mock_task_pending):
        """Test medium depth maps to 3 iterations."""
        payload = {"query": "Medium research", "depth": "medium"}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task_pending,
        ) as mock_create:
            await research_tool.execute(payload, context={})

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["max_iterations"] == 3

    @pytest.mark.asyncio
    async def test_execute_depth_deep(self, research_tool, mock_task_pending):
        """Test deep depth maps to 5 iterations."""
        payload = {"query": "Deep research", "depth": "deep"}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task_pending,
        ) as mock_create:
            await research_tool.execute(payload, context={})

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["max_iterations"] == 5

    @pytest.mark.asyncio
    async def test_execute_explicit_max_iterations_overrides_depth(
        self, research_tool, mock_task_pending
    ):
        """Test max_iterations overrides depth setting."""
        payload = {"query": "Research", "depth": "shallow", "max_iterations": 7}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task_pending,
        ) as mock_create:
            await research_tool.execute(payload, context={})

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["max_iterations"] == 7

    @pytest.mark.asyncio
    async def test_execute_with_focus_areas(self, research_tool, mock_task_pending):
        """Test focus areas are passed to service."""
        payload = {
            "query": "Energy research",
            "focus_areas": ["solar", "wind", "storage"],
        }

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task_pending,
        ) as mock_create:
            await research_tool.execute(payload, context={})

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["focus_areas"] == ["solar", "wind", "storage"]

    @pytest.mark.asyncio
    async def test_execute_completed_task_includes_results(
        self, research_tool, mock_task_completed
    ):
        """Test completed task includes summary and findings."""
        payload = {"query": "Completed research"}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task_completed,
        ):
            result = await research_tool.execute(payload, context={})

        assert result["task_id"] == "task-456"
        assert result["status"] == "completed"
        assert result["summary"] == "Research summary here"
        assert len(result["findings"]) == 1
        assert len(result["sources"]) == 1
        assert result["iterations_completed"] == 3
        assert result["metadata"]["total_duration_ms"] == 300000
        assert result["metadata"]["tokens_used"] == 5000

    @pytest.mark.asyncio
    async def test_execute_completed_without_sources(
        self, research_tool, mock_task_completed
    ):
        """Test completed task excludes sources when include_sources=False."""
        payload = {"query": "No sources", "include_sources": False}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task_completed,
        ):
            result = await research_tool.execute(payload, context={})

        assert result["sources"] == []

    @pytest.mark.asyncio
    async def test_execute_failed_task_includes_error(
        self, research_tool, mock_task_failed
    ):
        """Test failed task includes error message."""
        payload = {"query": "Failed research"}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task_failed,
        ):
            result = await research_tool.execute(payload, context={})

        assert result["task_id"] == "task-789"
        assert result["status"] == "failed"
        assert result["error"] == "API rate limit exceeded"

    @pytest.mark.asyncio
    async def test_execute_failed_task_default_error(self, research_tool):
        """Test failed task with no error message uses default."""
        from src.models.task import TaskStatus

        mock_task = MagicMock()
        mock_task.id = "task-000"
        mock_task.status = TaskStatus.FAILED
        mock_task.created_at = datetime.now()
        mock_task.completed_at = None
        mock_task.result = None
        mock_task.error_message = None

        payload = {"query": "Failed without message"}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task,
        ):
            result = await research_tool.execute(payload, context={})

        assert result["error"] == "Research task failed"

    @pytest.mark.asyncio
    async def test_execute_passes_user_and_chat_id(
        self, research_tool, mock_task_pending
    ):
        """Test user_id and chat_id are passed to service."""
        payload = {"query": "User research"}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task_pending,
        ) as mock_create:
            await research_tool.execute(
                payload, context={"user_id": "user-abc", "chat_id": "chat-xyz"}
            )

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["user_id"] == "user-abc"
            assert call_kwargs["chat_id"] == "chat-xyz"

    @pytest.mark.asyncio
    async def test_execute_no_context(self, research_tool, mock_task_pending):
        """Test execution without context."""
        payload = {"query": "No context research"}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task_pending,
        ) as mock_create:
            result = await research_tool.execute(payload, context=None)

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["user_id"] is None
            assert call_kwargs["chat_id"] is None
            assert result["task_id"] == "task-123"
