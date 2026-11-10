"""
Deep Research Service - Business Logic Layer

Extracts business logic from deep_research router for better separation of concerns.
Handles research task lifecycle, Aletheia orchestrator integration, and progress tracking.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import structlog
from fastapi import HTTPException, status

from ..core.config import Settings, get_settings
from ..core.telemetry import metrics_collector, trace_span
from ..models.history import HistoryEventType
from ..models.task import Task as TaskModel
from ..models.task import TaskStatus
from ..schemas.research import (
    DeepResearchParams,
    DeepResearchRequest,
    DeepResearchResult,
    ResearchMetrics,
    ResearchType,
)
from ..services.aletheia_client import get_aletheia_client
from ..services.history_service import HistoryService

logger = structlog.get_logger(__name__)


class DeepResearchService:
    """Service for deep research operations"""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def validate_research_request(
        self, request: DeepResearchRequest, user_id: str
    ) -> None:
        """
        Validate deep research request against kill switches and feature flags.

        Args:
            request: Deep research request
            user_id: User ID for logging

        Raises:
            HTTPException: If validation fails
        """
        # P0-DR-KILL-001: Global Kill Switch
        if self.settings.deep_research_kill_switch:
            logger.warning(
                "research_blocked",
                message="Deep Research request blocked by kill switch",
                user_id=user_id,
                kill_switch=True,
            )
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={
                    "error": "Deep Research feature is not available",
                    "error_code": "DEEP_RESEARCH_DISABLED",
                    "message": "This feature has been disabled. Please use standard chat instead.",
                    "kill_switch": True,
                },
            )

        # Fallback check: Respect enabled flag
        if not self.settings.deep_research_enabled:
            logger.warning(
                "Deep Research request rejected - feature is disabled",
                event="research_blocked",
                user_id=user_id,
                deep_research_enabled=self.settings.deep_research_enabled,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "Deep Research is temporarily unavailable",
                    "error_code": "DEEP_RESEARCH_UNAVAILABLE",
                    "message": "This feature is temporarily disabled. Please try again later.",
                    "enabled": False,
                },
            )

        # P0-DR-001: Require explicit flag
        if not request.explicit:
            logger.warning(
                "Deep Research request rejected - missing explicit flag",
                user_id=user_id,
                has_explicit_flag=request.explicit,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Deep Research requires explicit user action",
                    "code": "EXPLICIT_FLAG_REQUIRED",
                    "message": "Deep Research must be explicitly triggered by the user. Set 'explicit=true' in the request.",
                    "enabled": True,
                    "explicit_required": True,
                },
            )

        logger.info(
            "Deep Research request accepted",
            enabled=self.settings.deep_research_enabled,
            explicit=request.explicit,
            complexity_threshold=self.settings.deep_research_complexity_threshold,
            user_id=user_id,
        )

    def check_kill_switch(self, user_id: str) -> None:
        """
        Check if kill switch is active and raise exception if so.

        Args:
            user_id: User ID for logging

        Raises:
            HTTPException: If kill switch is active
        """
        if self.settings.deep_research_kill_switch:
            logger.warning(
                "research_blocked",
                message="Research access blocked by kill switch",
                user_id=user_id,
                kill_switch=True,
            )
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={
                    "error": "Deep Research feature is not available",
                    "error_code": "DEEP_RESEARCH_DISABLED",
                    "message": "This feature has been disabled.",
                    "kill_switch": True,
                },
            )

    async def create_research_task(
        self, request: DeepResearchRequest, user_id: str
    ) -> TaskModel:
        """
        Create a new research task record.

        Args:
            request: Deep research request
            user_id: User ID

        Returns:
            Created task model
        """
        task_id = str(uuid4())
        task = TaskModel(
            id=task_id,
            user_id=user_id,
            task_type="deep_research",
            status=TaskStatus.PENDING,
            input_data={
                "query": request.query,
                "research_type": request.research_type.value,
                "params": request.params.model_dump() if request.params else None,
                "stream": request.stream,
                "context": request.context,
            },
            chat_id=request.chat_id,
            created_at=datetime.utcnow(),
        )
        await task.insert()

        # Record unified history event
        if request.chat_id:
            try:
                await HistoryService.record_research_started(
                    chat_id=request.chat_id,
                    user_id=user_id,
                    task=task,
                    query=request.query,
                    params=request.params.model_dump() if request.params else None,
                )
            except Exception as history_error:
                logger.warning(
                    "Failed to persist research start in history",
                    error=str(history_error),
                    chat_id=request.chat_id,
                    task_id=task_id,
                )

        logger.info(
            "Created deep research task",
            task_id=task_id,
            query=request.query,
            user_id=user_id,
            chat_id=request.chat_id,
        )

        return task

    async def start_aletheia_research(
        self, task: TaskModel, request: DeepResearchRequest, user_id: str
    ) -> None:
        """
        Submit research task to Aletheia orchestrator.

        Args:
            task: Task model
            request: Research request
            user_id: User ID

        Raises:
            HTTPException: If Aletheia returns error
        """
        try:
            async with trace_span(
                "start_aletheia_research",
                {
                    "task.id": task.id,
                    "research.query_length": len(request.query),
                    "research.type": request.research_type or "deep_research",
                },
            ):
                aletheia_client = await get_aletheia_client()
                aletheia_response = await aletheia_client.start_deep_research(
                    query=request.query,
                    task_id=task.id,
                    user_id=user_id,
                    params=request.params.model_dump() if request.params else None,
                    context=request.context,
                )

            if aletheia_response.status == "error":
                task.status = TaskStatus.FAILED
                task.error_message = aletheia_response.error
                await task.save()

                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to start research: {aletheia_response.error}",
                )
            else:
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.utcnow()
                await task.save()

        except HTTPException:
            raise
        except Exception as e:
            # Fallback to mock mode if Aletheia is unavailable
            logger.warning("Aletheia unavailable, using mock mode", error=str(e))
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            await task.save()

    async def get_task_with_permission_check(
        self, task_id: str, user_id: str
    ) -> TaskModel:
        """
        Retrieve task and verify user has access.

        Args:
            task_id: Task ID
            user_id: User ID

        Returns:
            Task model

        Raises:
            HTTPException: If task not found or access denied
        """
        task = await TaskModel.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )

        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to task"
            )

        return task

    async def build_research_result(
        self, task: TaskModel
    ) -> Optional[DeepResearchResult]:
        """
        Build research result from task and Aletheia data.

        Args:
            task: Task model

        Returns:
            Research result or None if not completed
        """
        if task.status != TaskStatus.COMPLETED or not task.result_data:
            return None

        # Try to get real results from Aletheia
        try:
            aletheia_client = await get_aletheia_client()
            aletheia_status = await aletheia_client.get_task_status(task.id)

            if aletheia_status.status == "completed" and aletheia_status.data:
                # Parse real Aletheia results
                aletheia_data = aletheia_status.data
                return DeepResearchResult(
                    id=task.id,
                    query=task.input_data.get("query", ""),
                    summary=aletheia_data.get("summary", "Research completed"),
                    key_findings=aletheia_data.get("key_findings", []),
                    sources=aletheia_data.get("sources", []),
                    evidence=aletheia_data.get("evidence", []),
                    metrics=self._build_research_metrics(
                        aletheia_data.get("metrics", {})
                    ),
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                )
        except Exception as aletheia_error:
            logger.warning(
                "Failed to get Aletheia results, using stored data",
                task_id=task.id,
                error=str(aletheia_error),
            )

        # Fallback to stored result data
        return DeepResearchResult(
            id=task.id,
            query=task.input_data.get("query", ""),
            summary=task.result_data.get("summary", "Research completed"),
            key_findings=task.result_data.get("key_findings", []),
            sources=task.result_data.get("sources", []),
            evidence=task.result_data.get("evidence", []),
            metrics=self._build_research_metrics(task.result_data.get("metrics", {})),
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    def _build_research_metrics(self, metrics_data: Dict[str, Any]) -> ResearchMetrics:
        """Build ResearchMetrics from metrics data."""
        return ResearchMetrics(
            total_sources=metrics_data.get("total_sources", 0),
            sources_processed=metrics_data.get("sources_processed", 0),
            iterations_completed=metrics_data.get("iterations", 1),
            processing_time_seconds=metrics_data.get("processing_time", 60.0),
            tokens_used=metrics_data.get("tokens_used", 1000),
            cost_estimate=metrics_data.get("cost", 0.01),
        )

    async def calculate_progress(
        self, task: TaskModel
    ) -> Tuple[Optional[float], Optional[str]]:
        """
        Calculate task progress and estimated completion.

        Args:
            task: Task model

        Returns:
            Tuple of (progress, estimated_completion)
        """
        progress = None
        estimated_completion = None

        if task.status == TaskStatus.RUNNING:
            try:
                aletheia_client = await get_aletheia_client()
                aletheia_status = await aletheia_client.get_task_status(task.id)

                if aletheia_status.data and "progress" in aletheia_status.data:
                    progress = float(aletheia_status.data["progress"])
                    if "estimated_completion" in aletheia_status.data:
                        estimated_completion = aletheia_status.data[
                            "estimated_completion"
                        ]
                else:
                    # Fallback to time-based estimation
                    progress = self._estimate_progress_from_time(task)
            except Exception:
                # Fallback to time-based estimation
                progress = self._estimate_progress_from_time(task)

        elif task.status == TaskStatus.COMPLETED:
            progress = 1.0
            # Record metrics for completed research
            if task.completed_at:
                duration = (task.completed_at - task.created_at).total_seconds()
                metrics_collector.record_research_task(
                    task_type="deep_research", status="completed", duration=duration
                )
        elif task.status == TaskStatus.FAILED:
            progress = 0.0
            # Record metrics for failed research
            duration = (datetime.utcnow() - task.created_at).total_seconds()
            metrics_collector.record_research_task(
                task_type="deep_research", status="failed", duration=duration
            )
        else:
            progress = 0.0

        return progress, estimated_completion

    def _estimate_progress_from_time(self, task: TaskModel) -> float:
        """Estimate progress based on elapsed time."""
        elapsed = (
            (datetime.utcnow() - task.started_at).total_seconds()
            if task.started_at
            else 0
        )
        return min(elapsed / 300.0, 0.95)  # Max 95% until completed

    async def sync_history_events(self, task: TaskModel, user_id: str) -> None:
        """
        Synchronize history events for task status changes.

        Args:
            task: Task model
            user_id: User ID
        """
        if not task.chat_id:
            return

        try:
            latest_history_event = await HistoryService.get_latest_research_status(
                task.chat_id, task.id
            )

            if task.status == TaskStatus.COMPLETED:
                needs_completion_event = (
                    latest_history_event is None
                    or latest_history_event.event_type
                    != HistoryEventType.RESEARCH_COMPLETED
                )
                if needs_completion_event:
                    metrics_data = (
                        task.result_data.get("metrics", {}) if task.result_data else {}
                    )
                    sources_found = (
                        metrics_data.get("total_sources")
                        or metrics_data.get("sources_processed")
                        or 0
                    )
                    iterations_completed = (
                        metrics_data.get("iterations_completed")
                        or metrics_data.get("iterations")
                        or 0
                    )

                    await HistoryService.record_research_completed(
                        chat_id=task.chat_id,
                        user_id=user_id,
                        task=task,
                        sources_found=int(sources_found) if sources_found else 0,
                        iterations_completed=(
                            int(iterations_completed) if iterations_completed else 0
                        ),
                        result_metadata={
                            "source": "sync_history_events",
                            "result_synced": bool(task.result_data),
                        },
                    )

            elif task.status == TaskStatus.FAILED:
                needs_failure_event = (
                    latest_history_event is None
                    or latest_history_event.event_type
                    != HistoryEventType.RESEARCH_FAILED
                )
                if needs_failure_event:
                    await HistoryService.record_research_failed(
                        chat_id=task.chat_id,
                        user_id=user_id,
                        task_id=task.id,
                        error_message=task.error_message or "Research task failed",
                        progress=task.progress,
                        current_step=task.current_step,
                        metadata={
                            "source": "sync_history_events",
                            "result_synced": bool(task.result_data),
                        },
                    )
        except Exception as history_error:
            logger.warning(
                "Failed to sync research history",
                task_id=task.id,
                chat_id=task.chat_id,
                error=str(history_error),
            )

    async def cancel_task(self, task: TaskModel, reason: Optional[str] = None) -> None:
        """
        Cancel a running research task.

        Args:
            task: Task model
            reason: Cancellation reason

        Raises:
            HTTPException: If task cannot be cancelled
        """
        # Check if task can be cancelled
        if task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel task with status: {task.status.value}",
            )

        # Update task status
        task.status = TaskStatus.CANCELLED
        task.error_message = reason or "Cancelled by user"
        task.completed_at = datetime.utcnow()
        await task.save()

        # Cancel task in Aletheia orchestrator
        try:
            aletheia_client = await get_aletheia_client()
            await aletheia_client.cancel_task(task.id, reason=reason)
            logger.info("Cancelled task in Aletheia", task_id=task.id)
        except Exception as aletheia_error:
            logger.warning(
                "Failed to cancel task in Aletheia",
                task_id=task.id,
                error=str(aletheia_error),
            )

        logger.info(
            "Cancelled research task",
            task_id=task.id,
            user_id=task.user_id,
            reason=reason,
        )

    async def get_research_artifacts(
        self, task: TaskModel, format: str = "json"
    ) -> Dict[str, Any]:
        """
        Get research artifacts/reports for a completed task.

        Args:
            task: Task model
            format: Desired format (json, markdown, html, pdf)

        Returns:
            Artifact information

        Raises:
            HTTPException: If task not completed or artifacts unavailable
        """
        # Check if task is completed
        if task.status != TaskStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot download artifacts for task with status: {task.status.value}",
            )

        # Get artifacts from Aletheia
        try:
            aletheia_client = await get_aletheia_client()
            artifacts = await aletheia_client.get_report_artifacts(task.id)

            if not artifacts:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No artifacts available for this task",
                )

            # Return appropriate artifact based on format
            if format in artifacts:
                artifact_url = artifacts[format]
                # Calculate expiration: 7 days after task completion
                expires_at = None
                if task.completed_at:
                    from datetime import timedelta

                    expires_at = task.completed_at + timedelta(days=7)

                return {
                    "task_id": task.id,
                    "format": format,
                    "download_url": artifact_url,
                    "available_formats": list(artifacts.keys()),
                    "expires_at": expires_at.isoformat() if expires_at else None,
                }
            else:
                return {
                    "task_id": task.id,
                    "format": format,
                    "error": f"Format '{format}' not available",
                    "available_formats": list(artifacts.keys()),
                }

        except Exception as aletheia_error:
            logger.warning(
                "Failed to get artifacts from Aletheia",
                task_id=task.id,
                error=str(aletheia_error),
            )

            # Fallback to mock artifacts
            return {
                "task_id": task.id,
                "format": format,
                "download_url": f"/api/mock/artifacts/{task.id}.{format}",
                "available_formats": ["json", "markdown", "html"],
                "error": "Using mock artifacts - Aletheia unavailable",
            }

    async def get_user_tasks(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        status_filter: Optional[TaskStatus] = None,
    ) -> Dict[str, Any]:
        """
        Get research tasks for a user with pagination.

        Args:
            user_id: User ID
            limit: Maximum number of tasks to return
            offset: Number of tasks to skip
            status_filter: Optional status filter

        Returns:
            Dict with tasks, total_count, and has_more
        """
        # Build query
        query = TaskModel.find(TaskModel.user_id == user_id)

        if status_filter:
            query = query.find(TaskModel.status == status_filter)

        # Get total count
        total_count = await query.count()

        # Get tasks with pagination
        tasks = (
            await query.sort(-TaskModel.created_at).skip(offset).limit(limit).to_list()
        )

        # Convert to response format
        task_responses = []
        for task in tasks:
            task_responses.append(
                {
                    "task_id": task.id,
                    "status": task.status.value,
                    "task_type": task.task_type,
                    "query": task.input_data.get("query", ""),
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "chat_id": task.chat_id,
                    "error_message": task.error_message,
                }
            )

        logger.info(
            "Retrieved user tasks",
            user_id=user_id,
            task_count=len(tasks),
            total_count=total_count,
        )

        return {
            "tasks": task_responses,
            "total_count": total_count,
            "has_more": offset + len(tasks) < total_count,
        }


async def create_research_task(
    *,
    query: str,
    user_id: str,
    chat_id: Optional[str],
    max_iterations: int,
    focus_areas: Optional[List[str]] = None,
) -> TaskModel:
    """Helper used by MCP tool to create a deep-research task."""

    settings = get_settings()
    service = DeepResearchService(settings)

    params = DeepResearchParams(
        max_iterations=max_iterations,
        focus_areas=focus_areas or None,
    )
    request = DeepResearchRequest(
        query=query,
        chat_id=chat_id,
        params=params,
        research_type=ResearchType.DEEP_RESEARCH,
        stream=True,
        explicit=True,
    )

    await service.validate_research_request(request, user_id)
    return await service.create_research_task(request, user_id)
