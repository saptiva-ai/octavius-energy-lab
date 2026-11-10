"""
Review schemas for API requests and responses.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReviewStartRequest(BaseModel):
    """Request to start document review"""

    doc_id: str = Field(..., description="Document ID to review")
    model: str = Field(default="Saptiva Turbo", description="LLM model")
    rewrite_policy: str = Field(default="conservative", description="Rewrite policy")
    summary: bool = Field(default=True, description="Generate summary")
    color_audit: bool = Field(default=True, description="Run accessibility audit")


class ReviewStartResponse(BaseModel):
    """Response from review start"""

    job_id: str
    status: str


class ReviewStatusResponse(BaseModel):
    """Review status response"""

    job_id: str
    status: str
    progress: float
    current_stage: Optional[str] = None
    error_message: Optional[str] = None


class SpellingFindingResponse(BaseModel):
    """Spelling finding response"""

    page: int
    span: str
    suggestions: List[str]


class GrammarFindingResponse(BaseModel):
    """Grammar finding response"""

    page: int
    span: str
    rule: str
    explain: str
    suggestions: List[str]


class StyleNoteResponse(BaseModel):
    """Style note response"""

    page: int
    issue: str
    advice: str
    span: Optional[str] = None


class SuggestedRewriteResponse(BaseModel):
    """Suggested rewrite response"""

    page: int
    block_id: str
    original: str
    proposal: str
    rationale: str


class SummaryBulletResponse(BaseModel):
    """Summary bullet response"""

    page: int
    bullets: List[str]


class ColorPairResponse(BaseModel):
    """Color pair response"""

    fg: str
    bg: str
    ratio: float
    wcag: str
    location: Optional[str] = None


class ColorAuditResponse(BaseModel):
    """Color audit response"""

    pairs: List[ColorPairResponse]
    pass_count: int
    fail_count: int


class ReviewWarningResponse(BaseModel):
    """Review warning response"""

    stage: str
    code: str
    message: str


class ReviewReportResponse(BaseModel):
    """Complete review report response"""

    doc_id: str
    job_id: str
    summary: List[SummaryBulletResponse]
    spelling: List[SpellingFindingResponse]
    grammar: List[GrammarFindingResponse]
    style_notes: List[StyleNoteResponse]
    suggested_rewrites: List[SuggestedRewriteResponse]
    color_audit: ColorAuditResponse
    artifacts: Dict[str, Any]
    metrics: Dict[str, Any]
    created_at: str
    completed_at: Optional[str] = None
    warnings: List[ReviewWarningResponse] = []
    llm_status: str = "ok"  # "ok" | "degraded" | "failed"


class ReviewEventData(BaseModel):
    """SSE event data"""

    job_id: str
    status: str
    progress: float
    current_stage: Optional[str] = None
    message: Optional[str] = None
    trace_id: Optional[str] = None
    timestamp: str
