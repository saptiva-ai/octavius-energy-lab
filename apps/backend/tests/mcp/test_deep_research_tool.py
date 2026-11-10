"""Tests for DeepResearchTool (MCP)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import os

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MCP_DEEP_RESEARCH", "false").lower() != "true",
    reason="MCP deep research tests deshabilitados por defecto (requires full stack)",
)

from src.mcp_integration.tools.deep_research_tool import DeepResearchTool
from src.mcp_integration.protocol import ToolCategory, ToolCapability


@pytest.fixture
def deep_research_tool():
    """Create DeepResearchTool instance."""
    return DeepResearchTool()


class TestDeepResearchToolSpec:
    """Test tool specification."""

    def test_get_spec(self, deep_research_tool):
        """Test tool specification structure."""
        spec = deep_research_tool.get_spec()

        assert spec.name == "deep_research"
        assert spec.version == "1.0.0"
        assert spec.category == ToolCategory.RESEARCH
        assert ToolCapability.ASYNC in spec.capabilities
        assert ToolCapability.STREAMING in spec.capabilities
        assert spec.requires_auth is True
        assert spec.timeout_ms == 300000  # 5 minutes

    def test_input_schema(self, deep_research_tool):
        """Test input schema structure."""
        spec = deep_research_tool.get_spec()
        schema = spec.input_schema

        assert schema["type"] == "object"
        assert "query" in schema["required"]
        assert "query" in schema["properties"]
        assert "depth" in schema["properties"]
        assert "max_iterations" in schema["properties"]

    def test_output_schema(self, deep_research_tool):
        """Test output schema structure."""
        spec = deep_research_tool.get_spec()
        schema = spec.output_schema

        assert schema["type"] == "object"
        assert "task_id" in schema["properties"]
        assert "status" in schema["properties"]
        assert "summary" in schema["properties"]
        assert "findings" in schema["properties"]


class TestDeepResearchToolValidation:
    """Test input validation."""

    @pytest.mark.asyncio
    async def test_validate_input_success(self, deep_research_tool):
        """Test successful input validation."""
        payload = {
            "query": "What are the latest trends in AI?",
            "depth": "medium",
        }

        # Should not raise
        await deep_research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_validate_input_missing_query(self, deep_research_tool):
        """Test validation fails when query is missing."""
        payload = {"depth": "medium"}

        with pytest.raises(ValueError, match="Missing required field: query"):
            await deep_research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_validate_input_empty_query(self, deep_research_tool):
        """Test validation fails when query is empty."""
        payload = {"query": "   "}

        with pytest.raises(ValueError, match="query cannot be empty"):
            await deep_research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_validate_input_invalid_depth(self, deep_research_tool):
        """Test validation fails with invalid depth."""
        payload = {
            "query": "Test query",
            "depth": "invalid",
        }

        with pytest.raises(ValueError, match="Invalid depth"):
            await deep_research_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_validate_input_invalid_max_iterations(self, deep_research_tool):
        """Test validation fails with invalid max_iterations."""
        payload = {
            "query": "Test query",
            "max_iterations": 15,  # Max is 10
        }

        with pytest.raises(ValueError, match="max_iterations must be an integer between 1 and 10"):
            await deep_research_tool.validate_input(payload)


class TestDeepResearchToolExecution:
    """Test tool execution."""

    @pytest.mark.asyncio
    async def test_execute_success(self, deep_research_tool):
        """Test successful execution creates research task."""
        payload = {
            "query": "Latest trends in renewable energy",
            "depth": "medium",
            "focus_areas": ["solar", "wind"],
        }
        context = {"user_id": "user_123"}

        # Mock the create_research_task function
        mock_task = MagicMock()
        mock_task.id = "task_123"
        mock_task.status = MagicMock(value="pending")
        mock_task.created_at = datetime.now()
        mock_task.result = None

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task,
        ):
            result = await deep_research_tool.execute(payload, context)

            assert result["task_id"] == "task_123"
            assert result["status"] == "pending"
            assert result["query"] == "Latest trends in renewable energy"
            assert result["iterations_completed"] == 0
            assert "metadata" in result
            assert result["metadata"]["depth"] == "medium"
            assert result["metadata"]["max_iterations"] == 3  # medium = 3

    @pytest.mark.asyncio
    async def test_execute_with_max_iterations(self, deep_research_tool):
        """Test execution with explicit max_iterations."""
        payload = {
            "query": "Test query",
            "max_iterations": 5,
        }
        context = {"user_id": "user_123"}

        mock_task = MagicMock()
        mock_task.id = "task_456"
        mock_task.status = MagicMock(value="pending")
        mock_task.created_at = datetime.now()

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task,
        ) as mock_create:
            result = await deep_research_tool.execute(payload, context)

            # Verify create_research_task was called with correct max_iterations
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["max_iterations"] == 5

            assert result["metadata"]["max_iterations"] == 5

    @pytest.mark.asyncio
    async def test_execute_completed_task(self, deep_research_tool):
        """Test execution with already completed task."""
        payload = {"query": "Test query"}
        context = {"user_id": "user_123"}

        mock_task = MagicMock()
        mock_task.id = "task_789"
        mock_task.status = MagicMock(value="completed")
        mock_task.created_at = datetime.now()
        mock_task.completed_at = datetime.now()
        mock_task.result = {
            "summary": "Test summary",
            "findings": [{"topic": "Test", "content": "Test content"}],
            "sources": [{"url": "https://test.com"}],
            "iterations_completed": 3,
            "total_duration_ms": 5000,
            "tokens_used": 1500,
        }

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task,
        ):
            result = await deep_research_tool.execute(payload, context)

            assert result["status"] == "completed"
            assert result["summary"] == "Test summary"
            assert len(result["findings"]) == 1
            assert len(result["sources"]) == 1
            assert result["iterations_completed"] == 3
            assert result["metadata"]["total_duration_ms"] == 5000
            assert result["metadata"]["tokens_used"] == 1500

    @pytest.mark.asyncio
    async def test_execute_depth_mapping(self, deep_research_tool):
        """Test depth to iterations mapping."""
        test_cases = [
            ("shallow", 2),
            ("medium", 3),
            ("deep", 5),
        ]

        for depth, expected_iterations in test_cases:
            payload = {"query": "Test query", "depth": depth}
            context = {}

            mock_task = MagicMock()
            mock_task.id = f"task_{depth}"
            mock_task.status = MagicMock(value="pending")
            mock_task.created_at = datetime.now()

            with patch(
                "src.mcp_integration.tools.deep_research_tool.create_research_task",
                new_callable=AsyncMock,
                return_value=mock_task,
            ) as mock_create:
                result = await deep_research_tool.execute(payload, context)

                # Verify correct iterations
                call_kwargs = mock_create.call_args[1]
                assert call_kwargs["max_iterations"] == expected_iterations

    @pytest.mark.asyncio
    async def test_execute_without_sources(self, deep_research_tool):
        """Test execution with include_sources=False."""
        payload = {
            "query": "Test query",
            "include_sources": False,
        }
        context = {}

        mock_task = MagicMock()
        mock_task.id = "task_nosources"
        mock_task.status = MagicMock(value="completed")
        mock_task.created_at = datetime.now()
        mock_task.completed_at = datetime.now()
        mock_task.result = {
            "summary": "Test",
            "findings": [],
            "sources": [{"url": "https://test.com"}],
            "iterations_completed": 1,
        }

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task,
        ):
            result = await deep_research_tool.execute(payload, context)

            assert result["status"] == "completed"
            assert "sources" in result
            assert len(result["sources"]) == 0  # Sources excluded


class TestDeepResearchToolInvoke:
    """Test full invocation lifecycle."""

    @pytest.mark.asyncio
    async def test_invoke_success(self, deep_research_tool):
        """Test successful tool invocation."""
        payload = {
            "query": "AI trends 2025",
            "depth": "medium",
        }

        mock_task = MagicMock()
        mock_task.id = "task_invoke"
        mock_task.status = MagicMock(value="pending")
        mock_task.created_at = datetime.now()

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            return_value=mock_task,
        ):
            response = await deep_research_tool.invoke(payload, context={"user_id": "user_123"})

            assert response.success is True
            assert response.tool == "deep_research"
            assert response.version == "1.0.0"
            assert response.result is not None
            assert response.error is None
            assert response.duration_ms > 0

    @pytest.mark.asyncio
    async def test_invoke_validation_error(self, deep_research_tool):
        """Test invocation with validation error."""
        payload = {"depth": "medium"}  # Missing query

        response = await deep_research_tool.invoke(payload)

        assert response.success is False
        assert response.error is not None
        assert response.error.code == "INVALID_INPUT"
        assert "query" in response.error.message

    @pytest.mark.asyncio
    async def test_invoke_execution_error(self, deep_research_tool):
        """Test invocation with execution error."""
        payload = {"query": "Test query"}

        with patch(
            "src.mcp_integration.tools.deep_research_tool.create_research_task",
            new_callable=AsyncMock,
            side_effect=Exception("Service unavailable"),
        ):
            response = await deep_research_tool.invoke(payload)

            assert response.success is False
            assert response.error is not None
            assert response.error.code == "EXECUTION_ERROR"
            assert "Service unavailable" in response.error.message
