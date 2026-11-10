"""
Deep Research Tool - Aletheia Integration.

Performs multi-step research using the Aletheia service for comprehensive
information gathering and synthesis.
"""

from typing import Any, Dict, Optional

import structlog

from ...models.task import TaskStatus
from ...services.deep_research_service import create_research_task
from ..protocol import ToolCapability, ToolCategory, ToolSpec
from ..tool import Tool

logger = structlog.get_logger(__name__)


class DeepResearchTool(Tool):
    """
    Deep Research Tool - Multi-step research with Aletheia.

    Performs comprehensive research by:
    - Breaking down complex queries into sub-questions
    - Gathering information from multiple sources
    - Synthesizing findings into coherent reports
    - Tracking research progress and iterations

    Integrates with existing Aletheia service and research orchestration.
    """

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="deep_research",
            version="1.0.0",
            display_name="Deep Research (Aletheia)",
            description=(
                "Performs multi-step research using Aletheia. Breaks down complex queries, "
                "gathers information from multiple sources, and synthesizes findings into "
                "comprehensive reports. Ideal for market research, competitive analysis, "
                "and in-depth topic exploration."
            ),
            category=ToolCategory.RESEARCH,
            capabilities=[
                ToolCapability.ASYNC,
                ToolCapability.STREAMING,
                ToolCapability.STATEFUL,
            ],
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Research question or topic to investigate",
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["shallow", "medium", "deep"],
                        "default": "medium",
                        "description": (
                            "Research depth: shallow (1-2 iterations), "
                            "medium (3-4 iterations), deep (5+ iterations)"
                        ),
                    },
                    "focus_areas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific areas to focus research on (optional)",
                    },
                    "max_iterations": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 3,
                        "description": "Maximum research iterations (overrides depth setting)",
                    },
                    "include_sources": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include source citations in report",
                    },
                },
                "required": ["query"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Research task ID for tracking progress",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "running", "completed", "failed"],
                        "description": "Current task status",
                    },
                    "query": {
                        "type": "string",
                        "description": "Original research query",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Executive summary of findings (when completed)",
                    },
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "topic": {"type": "string"},
                                "content": {"type": "string"},
                                "sources": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "confidence": {"type": "number"},
                            },
                        },
                        "description": "Detailed research findings",
                    },
                    "iterations_completed": {
                        "type": "integer",
                        "description": "Number of research iterations completed",
                    },
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string"},
                                "title": {"type": "string"},
                                "relevance": {"type": "number"},
                            },
                        },
                        "description": "All sources consulted",
                    },
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "started_at": {"type": "string", "format": "date-time"},
                            "completed_at": {"type": "string", "format": "date-time"},
                            "total_duration_ms": {"type": "number"},
                            "tokens_used": {"type": "integer"},
                        },
                    },
                },
            },
            tags=["research", "aletheia", "web_search", "analysis", "synthesis"],
            requires_auth=True,
            rate_limit={"calls_per_minute": 5},  # Research is expensive
            timeout_ms=300000,  # 5 minutes for deep research
            max_payload_size_kb=50,
        )

    async def validate_input(self, payload: Dict[str, Any]) -> None:
        """Validate input payload."""
        if "query" not in payload:
            raise ValueError("Missing required field: query")

        if not isinstance(payload["query"], str):
            raise ValueError("query must be a string")

        if not payload["query"].strip():
            raise ValueError("query cannot be empty")

        # Validate depth enum if provided
        if "depth" in payload:
            valid_depths = ["shallow", "medium", "deep"]
            if payload["depth"] not in valid_depths:
                raise ValueError(f"Invalid depth. Must be one of: {valid_depths}")

        # Validate max_iterations if provided
        if "max_iterations" in payload:
            max_iter = payload["max_iterations"]
            if not isinstance(max_iter, int) or max_iter < 1 or max_iter > 10:
                raise ValueError("max_iterations must be an integer between 1 and 10")

    async def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute deep research task.

        Args:
            payload: {
                "query": "What are the latest trends in renewable energy?",
                "depth": "medium",
                "focus_areas": ["solar", "wind", "battery storage"],
                "max_iterations": 3,
                "include_sources": True
            }
            context: {
                "user_id": "user_456",
                "chat_id": "chat_789"
            }

        Returns:
            Research task with status and findings (if completed)
        """
        query = payload["query"]
        depth = payload.get("depth", "medium")
        focus_areas = payload.get("focus_areas", [])
        max_iterations = payload.get("max_iterations")
        include_sources = payload.get("include_sources", True)
        user_id = context.get("user_id") if context else None
        chat_id = context.get("chat_id") if context else None

        # Map depth to iterations if not explicitly provided
        if max_iterations is None:
            depth_to_iterations = {
                "shallow": 2,
                "medium": 3,
                "deep": 5,
            }
            max_iterations = depth_to_iterations.get(depth, 3)

        logger.info(
            "Deep research tool execution started",
            query=query,
            depth=depth,
            max_iterations=max_iterations,
            focus_areas=focus_areas,
            user_id=user_id,
            chat_id=chat_id,
        )

        # Create research task using existing service
        task = await create_research_task(
            query=query,
            user_id=user_id,
            chat_id=chat_id,
            max_iterations=max_iterations,
            focus_areas=focus_areas,
        )

        logger.info(
            "Research task created",
            task_id=str(task.id),
            status=task.status,
        )

        # Build response
        result = {
            "task_id": str(task.id),
            "status": (
                task.status.value if hasattr(task.status, "value") else task.status
            ),
            "query": query,
            "iterations_completed": 0,
            "metadata": {
                "started_at": task.created_at.isoformat() if task.created_at else None,
                "max_iterations": max_iterations,
                "depth": depth,
            },
        }

        # If task is already completed (unlikely, but possible for cached results)
        if task.status == TaskStatus.COMPLETED and task.result:
            result.update(
                {
                    "summary": task.result.get("summary", ""),
                    "findings": task.result.get("findings", []),
                    "sources": (
                        task.result.get("sources", []) if include_sources else []
                    ),
                    "iterations_completed": task.result.get("iterations_completed", 0),
                    "metadata": {
                        **result["metadata"],
                        "completed_at": (
                            task.completed_at.isoformat() if task.completed_at else None
                        ),
                        "total_duration_ms": task.result.get("total_duration_ms", 0),
                        "tokens_used": task.result.get("tokens_used", 0),
                    },
                }
            )
        elif task.status == TaskStatus.FAILED:
            result["error"] = task.error_message or "Research task failed"

        return result
