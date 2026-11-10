"""
Audit report schema (presentation-agnostic).

These are response schemas for UI consumption - audit logic is in un plugin privado de auditoría.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AuditStats(BaseModel):
    """Aggregated counts by severity."""

    critical: int = Field(0, description="Critical findings count")
    high: int = Field(0, description="High findings count")
    medium: int = Field(0, description="Medium findings count")
    low: int = Field(0, description="Low findings count")
    total: int = Field(0, description="Total findings count")


class AuditFinding(BaseModel):
    """Normalized finding for UI consumption."""

    id: Optional[str] = Field(None, description="Unique finding identifier")
    category: str = Field(..., description="Finding category")
    severity: str = Field(..., description="Severity level (critical/high/medium/low)")
    message: str = Field(..., description="Human-readable issue description")
    page: Optional[int] = Field(None, description="Page number (1-indexed)")
    suggestion: Optional[str] = Field(None, description="Suggested remediation")
    rule: Optional[str] = Field(
        None, description="Rule/check that triggered the finding"
    )
    raw: Dict[str, Any] = Field(
        default_factory=dict, description="Original finding payload"
    )


class AuditReportResponse(BaseModel):
    """Presentation-agnostic audit result for frontend rendering."""

    doc_name: str = Field(..., description="Document name or label")
    stats: AuditStats = Field(..., description="Severity counters")
    categories: Dict[str, List[AuditFinding]] = Field(
        default_factory=dict, description="Findings grouped by category"
    )
    actions: List[str] = Field(
        default_factory=list, description="Suggested follow-up actions"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
