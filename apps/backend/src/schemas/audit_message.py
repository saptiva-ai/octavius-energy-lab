"""
Audit Message Schemas for COPILOTO-AUDIT.

Defines the structure of audit results and findings.
These are response schemas only - audit logic is in un plugin privado de auditoría.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Category = Literal[
    "compliance",
    "format",
    "typography",
    "logo",
    "color_palette",
    "entity_consistency",
    "semantic_consistency",
    "linguistic",
]
Severity = Literal["low", "medium", "high", "critical"]


class FindingLocation(BaseModel):
    """Location of a finding within the document."""

    page: Optional[int] = Field(None, description="Page number (1-indexed)")
    bbox: Optional[List[float]] = Field(
        None, description="Bounding box [x0, y0, x1, y1]"
    )
    fragment_id: Optional[str] = Field(None, description="Fragment ID")
    text_snippet: Optional[str] = Field(None, description="Excerpt of text")


class Finding(BaseModel):
    """Validation finding from COPILOTO-AUDIT auditors."""

    id: str = Field(..., description="Unique finding identifier")
    category: str = Field(..., description="Finding category")
    rule: str = Field(..., description="Rule that triggered the finding")
    issue: str = Field(..., description="Human-readable description")
    severity: str = Field(..., description="Finding severity")
    location: Optional[FindingLocation] = Field(None, description="Location metadata")
    suggestion: Optional[str] = Field(None, description="Suggested remediation")


class ValidationReportResponse(BaseModel):
    """Response schema for validation coordinator."""

    job_id: str = Field(..., description="Unique validation job ID")
    status: str = Field(..., description="completed | error")
    findings: List[Finding] = Field(
        default_factory=list, description="All validation findings"
    )
    summary: Dict[str, Any] = Field(default_factory=dict, description="Summary metrics")
    attachments: Dict[str, Any] = Field(
        default_factory=dict, description="Optional attachments"
    )
    fragments_count: int = Field(default=0, description="Number of fragments analyzed")
