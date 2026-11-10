"""
Task document models for deep research and other async operations
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from beanie import Document, Indexed
from pydantic import Field


class TaskStatus(str, Enum):
    """Task status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(Document):
    """Generic task document model"""

    id: str = Field(default_factory=lambda: str(uuid4()), alias="_id")
    task_type: str = Field(..., description="Task type")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Task status")
    user_id: Indexed(str) = Field(..., description="User ID")
    chat_id: Optional[str] = Field(None, description="Associated chat ID")
    progress: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Progress percentage"
    )
    current_step: Optional[str] = Field(None, description="Current step description")
    total_steps: int = Field(default=1, description="Total number of steps")

    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )
    started_at: Optional[datetime] = Field(None, description="Start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")

    error_message: Optional[str] = Field(None, description="Error message if failed")
    result_data: Optional[Dict[str, Any]] = Field(None, description="Task result data")
    input_data: Dict[str, Any] = Field(
        default_factory=dict, description="Task input data"
    )
    metadata: Optional[Dict[str, Any]] = Field(None, description="Task metadata")

    class Settings:
        name = "tasks"
        indexes = [
            "user_id",
            "chat_id",
            "status",
            "task_type",
            "created_at",
            [("user_id", 1), ("created_at", -1)],  # User's recent tasks
        ]

    def __str__(self) -> str:
        return f"Task(id={self.id}, task_type={self.task_type}, status={self.status})"


class DeepResearchTask(Task):
    """Deep research specific task model"""

    query: str = Field(..., description="Research query")
    params: Dict[str, Any] = Field(..., description="Research parameters")

    # Research specific fields
    sources_found: int = Field(default=0, description="Number of sources found")
    iterations_completed: int = Field(default=0, description="Iterations completed")
    budget_used: float = Field(default=0.0, description="Budget used")

    # Artifacts
    report_url: Optional[str] = Field(None, description="Report file URL")
    sources_bib_url: Optional[str] = Field(None, description="Sources bibliography URL")
    raw_data_url: Optional[str] = Field(None, description="Raw data URL")

    class Settings:
        name = "deep_research_tasks"
        indexes = [
            "user_id",
            "query",
            "status",
            "created_at",
        ]
