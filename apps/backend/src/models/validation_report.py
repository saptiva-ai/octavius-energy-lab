"""
ValidationReport model for storing Copiloto Audit validation results.

This model persists validation findings so they can be:
1. Retrieved later without re-running validation
2. Referenced in chat context (RAG + Validations)
3. Tracked over time for analytics
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from beanie import Document
from pydantic import Field


class ValidationReport(Document):
    """
    Persistent storage for validation reports.

    Linked to Document via document_id for context injection in chat.
    """

    # Link to document
    document_id: str = Field(..., description="Document ID that was validated")
    user_id: str = Field(..., description="User who requested validation")

    # Validation metadata
    job_id: str = Field(..., description="Unique validation job ID")
    status: str = Field(..., description="completed | error")
    client_name: Optional[str] = Field(
        None, description="Client name used for validation (e.g., BancoMuestra)"
    )

    # Auditor configuration
    auditors_enabled: Dict[str, bool] = Field(
        default_factory=lambda: {"disclaimer": True, "format": True, "logo": True},
        description="Which auditors were enabled for this validation",
    )

    # Results
    findings: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of Finding objects (serialized)"
    )

    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary metrics (total_findings, coverage, findings_by_severity)",
    )

    # Optional attachments
    attachments: Optional[Dict[str, Any]] = Field(
        None, description="Optional attachments like overlay_pdf"
    )

    # Error tracking
    error: Optional[str] = Field(None, description="Error message if status=error")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    validation_duration_ms: Optional[int] = Field(
        None, description="How long validation took"
    )

    class Settings:
        name = "validation_reports"
        indexes = [
            "document_id",
            "user_id",
            "created_at",
            [("document_id", 1), ("created_at", -1)],
        ]

    def get_findings_summary_for_prompt(self) -> str:
        """
        Format findings summary for LLM context injection.

        Returns concise text like:
        'Este documento tiene 3 findings: 2 críticos (disclaimer faltante en páginas 5,8),
        1 alto (color no permitido en página 3)'
        """
        if not self.findings:
            return "Este documento no tiene findings de validación de cumplimiento."

        total = len(self.findings)
        by_severity = self.summary.get("findings_by_severity", {})

        critical_count = by_severity.get("critical", 0)
        high_count = by_severity.get("high", 0)
        medium_count = by_severity.get("medium", 0)

        parts = [
            f"Este documento tiene {total} finding{'s' if total > 1 else ''} de validación de cumplimiento:"
        ]

        if critical_count > 0:
            parts.append(f"{critical_count} crítico{'s' if critical_count > 1 else ''}")
        if high_count > 0:
            parts.append(f"{high_count} alto{'s' if high_count > 1 else ''}")
        if medium_count > 0:
            parts.append(f"{medium_count} medio{'s' if medium_count > 1 else ''}")

        # Add specific issues
        critical_findings = [
            f for f in self.findings if f.get("severity") == "critical"
        ]
        if critical_findings:
            issues = []
            for finding in critical_findings[:2]:  # Max 2 for brevity
                issue = finding.get("issue", "")
                page = finding.get("location", {}).get("page")
                if page:
                    issues.append(f"{issue} (página {page})")
                else:
                    issues.append(issue)
            if issues:
                parts.append(f"Principales problemas: {', '.join(issues)}")

        return " - ".join(parts)
