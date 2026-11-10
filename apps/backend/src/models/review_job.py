"""
Review job model for document revision tracking.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from beanie import Document
from pydantic import Field


class ReviewStatus(str, Enum):
    """Review job status"""

    QUEUED = "QUEUED"
    RECEIVED = "RECEIVED"
    EXTRACT = "EXTRACT"
    LT_GRAMMAR = "LT_GRAMMAR"
    LLM_SUGGEST = "LLM_SUGGEST"
    SUMMARY = "SUMMARY"
    COLOR_AUDIT = "COLOR_AUDIT"
    READY = "READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RewritePolicy(str, Enum):
    """Rewrite policy for suggestions"""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class SpellingFinding(Document):
    """Spelling error finding"""

    page: int
    span: str
    suggestions: List[str]
    offset: int
    length: int


class GrammarFinding(Document):
    """Grammar error finding"""

    page: int
    span: str
    rule: str
    explain: str
    suggestions: List[str]
    offset: int
    length: int


class StyleNote(Document):
    """Style improvement note"""

    page: int
    issue: str
    advice: str
    span: Optional[str] = None


class SuggestedRewrite(Document):
    """LLM-suggested rewrite"""

    page: int
    block_id: str
    original: str
    proposal: str
    rationale: str


class SummaryBullet(Document):
    """Summary bullet point"""

    page: int
    bullets: List[str]


class ColorPair(Document):
    """Color contrast pair for accessibility"""

    fg: str  # Hex color
    bg: str  # Hex color
    ratio: float
    wcag: str  # "pass" | "fail"
    location: Optional[str] = None  # Page or section


class ReviewWarning(Document):
    """Warning about partial or degraded processing"""

    stage: str  # "LT_GRAMMAR" | "LLM_SUGGEST" | etc.
    code: str  # "LT_TIMEOUT" | "LLM_DEGRADED" | etc.
    message: str


class ReviewReport(Document):
    """Review report with all findings"""

    summary: List[SummaryBullet] = Field(default_factory=list)
    spelling: List[SpellingFinding] = Field(default_factory=list)
    grammar: List[GrammarFinding] = Field(default_factory=list)
    style_notes: List[StyleNote] = Field(default_factory=list)
    suggested_rewrites: List[SuggestedRewrite] = Field(default_factory=list)
    color_audit: Dict[str, Any] = Field(default_factory=dict)
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[ReviewWarning] = Field(default_factory=list)
    llm_status: str = Field(default="ok")  # "ok" | "degraded" | "failed"


class ReviewJob(Document):
    """Review job tracking"""

    # Identification
    job_id: str = Field(..., description="Unique job ID")
    doc_id: str = Field(..., description="Document ID being reviewed")
    user_id: str = Field(..., description="Owner user ID")

    # Configuration
    model: str = Field(default="Saptiva Turbo", description="LLM model")
    rewrite_policy: RewritePolicy = Field(
        default=RewritePolicy.CONSERVATIVE, description="Rewrite policy"
    )
    summary: bool = Field(default=True, description="Generate summary")
    color_audit: bool = Field(default=True, description="Run color audit")

    # Status
    status: ReviewStatus = Field(default=ReviewStatus.QUEUED)
    current_stage: Optional[str] = Field(None, description="Current stage description")
    progress: float = Field(default=0.0, description="Progress 0-100")
    error_message: Optional[str] = Field(None)

    # Results
    report: Optional[ReviewReport] = Field(None, description="Final report")

    # Metrics
    lt_findings_count: int = Field(default=0, description="LanguageTool findings count")
    llm_calls_count: int = Field(default=0, description="LLM API calls count")
    tokens_in: int = Field(default=0, description="Approximate input tokens")
    tokens_out: int = Field(default=0, description="Approximate output tokens")
    processing_time_ms: Optional[int] = Field(None, description="Total processing time")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)

    class Settings:
        name = "review_jobs"
        indexes = [
            "job_id",
            "doc_id",
            "user_id",
            "status",
            [("user_id", 1), ("created_at", -1)],
        ]
