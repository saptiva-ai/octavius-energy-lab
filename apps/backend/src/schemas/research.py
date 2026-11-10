"""
Deep Research API schemas
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    """Task status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchType(str, Enum):
    """Research type enumeration"""

    WEB_SEARCH = "web_search"
    DEEP_RESEARCH = "deep_research"


class DeepResearchParams(BaseModel):
    """Deep research parameters"""

    budget: Optional[float] = Field(None, ge=0.0, description="Research budget limit")
    max_iterations: Optional[int] = Field(
        None, ge=1, le=20, description="Max research iterations"
    )
    scope: Optional[str] = Field(None, description="Research scope definition")
    sources_limit: Optional[int] = Field(
        None, ge=1, le=50, description="Maximum sources to use"
    )
    depth_level: Optional[str] = Field(
        None, pattern="^(shallow|medium|deep)$", description="Research depth level"
    )
    focus_areas: Optional[List[str]] = Field(
        None, description="Specific areas to focus on"
    )
    language: str = Field(default="en", description="Research language")
    include_citations: bool = Field(
        default=True, description="Include citations in results"
    )


class DeepResearchRequest(BaseModel):
    """Deep research request schema"""

    query: str = Field(..., min_length=1, max_length=2000, description="Research query")
    research_type: ResearchType = Field(
        default=ResearchType.DEEP_RESEARCH, description="Type of research"
    )
    chat_id: Optional[str] = Field(None, description="Associated chat session ID")
    params: Optional[DeepResearchParams] = Field(
        None, description="Research parameters"
    )
    stream: bool = Field(default=True, description="Enable streaming updates")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")

    # P0-DR-001: Explicit flag required to prevent auto-triggering
    explicit: bool = Field(
        default=False,
        description="Explicit user action required - must be True to trigger Deep Research",
    )

    @field_validator("query")
    @classmethod
    def validate_query_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Query cannot be empty")
        return v.strip()


class ResearchSource(BaseModel):
    """Research source schema"""

    id: str = Field(..., description="Source ID")
    title: str = Field(..., description="Source title")
    url: str = Field(..., description="Source URL")
    content: str = Field(..., description="Source content")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance score")
    reliability_score: float = Field(
        ..., ge=0.0, le=1.0, description="Reliability score"
    )
    publish_date: Optional[datetime] = Field(None, description="Publication date")
    author: Optional[str] = Field(None, description="Author")
    domain: str = Field(..., description="Source domain")
    type: str = Field(..., description="Source type (web, academic, news, etc.)")


class Evidence(BaseModel):
    """Evidence schema"""

    id: str = Field(..., description="Evidence ID")
    claim: str = Field(..., description="Claim or statement")
    evidence_text: str = Field(..., description="Supporting evidence text")
    source_ids: List[str] = Field(..., description="Supporting source IDs")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    evidence_type: str = Field(..., description="Type of evidence")
    created_at: datetime = Field(..., description="Creation timestamp")


class ResearchMetrics(BaseModel):
    """Research metrics schema"""

    total_sources: int = Field(..., description="Total sources found")
    sources_processed: int = Field(..., description="Sources processed")
    iterations_completed: int = Field(..., description="Research iterations completed")
    processing_time_seconds: float = Field(..., description="Total processing time")
    tokens_used: int = Field(..., description="Total tokens used")
    cost_estimate: Optional[float] = Field(None, description="Estimated cost")
    quality_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Overall quality score"
    )


class DeepResearchResult(BaseModel):
    """Deep research result schema"""

    id: str = Field(..., description="Result ID")
    query: str = Field(..., description="Original query")
    summary: str = Field(..., description="Research summary")
    key_findings: List[str] = Field(..., description="Key findings")
    sources: List[ResearchSource] = Field(..., description="Sources used")
    evidence: List[Evidence] = Field(..., description="Evidence collected")
    metrics: ResearchMetrics = Field(..., description="Research metrics")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class DeepResearchResponse(BaseModel):
    """Deep research response schema"""

    task_id: str = Field(..., description="Research task ID")
    status: TaskStatus = Field(..., description="Task status")
    message: str = Field(..., description="Status message")
    result: Optional[DeepResearchResult] = Field(None, description="Research result")
    progress: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Progress percentage"
    )
    estimated_completion: Optional[datetime] = Field(
        None, description="Estimated completion time"
    )
    created_at: datetime = Field(..., description="Task creation timestamp")
    stream_url: Optional[str] = Field(
        None, description="Streaming URL for real-time updates"
    )


class StreamEvent(BaseModel):
    """Stream event schema for SSE"""

    event_type: str = Field(..., description="Event type")
    task_id: str = Field(..., description="Task ID")
    timestamp: datetime = Field(..., description="Event timestamp")
    data: Dict[str, Any] = Field(..., description="Event data")
    progress: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Progress percentage"
    )


class TaskStatusRequest(BaseModel):
    """Task status request schema"""

    task_id: str = Field(..., description="Task ID to query")


class TaskCancelRequest(BaseModel):
    """Task cancellation request schema"""

    task_id: str = Field(..., description="Task ID to cancel")
    reason: Optional[str] = Field(None, description="Cancellation reason")
