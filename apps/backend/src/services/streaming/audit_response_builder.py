"""
Audit Response Builder Service.

Extracted from streaming_handler.py for better testability.
Handles building and formatting audit validation responses.

REFACTOR-001: Phase 5.4 extraction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog

from .auditor_formatter import AUDITOR_DISPLAY_NAMES

logger = structlog.get_logger(__name__)


@dataclass
class AuditResult:
    """Result of audit validation."""

    success: bool
    content: str
    validation_event: Optional[Dict[str, Any]]
    artifact: Optional[Dict[str, Any]]
    validation_report_id: Optional[str]
    error_message: Optional[str] = None
    error_type: Optional[str] = None


@dataclass
class AuditSummary:
    """Summary of audit findings."""

    total_findings: int
    critical: int
    high: int
    medium: int
    low: int
    duration_ms: int
    findings_by_category: Dict[str, int] = field(default_factory=dict)


class AuditResponseBuilder:
    """
    Service for building audit validation responses.

    Responsibilities:
        - Build validation complete events
        - Generate human-readable audit result content
        - Build audit artifacts for UI
        - Format findings summaries
    """

    @staticmethod
    def extract_summary(mcp_result: Dict[str, Any]) -> AuditSummary:
        """
        Extract audit summary from MCP result.

        Args:
            mcp_result: Result from MCP auditor service

        Returns:
            AuditSummary with findings counts
        """
        findings_by_severity = mcp_result.get("findings_by_severity", {})

        return AuditSummary(
            total_findings=mcp_result.get("total_findings", 0),
            critical=findings_by_severity.get("critical", 0),
            high=findings_by_severity.get("high", 0),
            medium=findings_by_severity.get("medium", 0),
            low=findings_by_severity.get("low", 0),
            duration_ms=mcp_result.get("validation_duration_ms", 0),
            findings_by_category=mcp_result.get("findings_by_category", {}),
        )

    @staticmethod
    def build_validation_complete_event(
        mcp_result: Dict[str, Any],
        filename: str,
    ) -> Dict[str, Any]:
        """
        Build validation_complete event from MCP result.

        Args:
            mcp_result: Result from MCP auditor service
            filename: Document filename

        Returns:
            Validation complete event dict
        """
        return {
            "type": "validation_complete",
            "job_id": mcp_result.get("job_id"),
            "status": mcp_result.get("status"),
            "filename": filename,
            "duration_ms": mcp_result.get("validation_duration_ms", 0),
            "summary": {
                "total_findings": mcp_result.get("total_findings", 0),
                "findings_by_severity": mcp_result.get("findings_by_severity", {}),
                "findings_by_category": mcp_result.get("findings_by_category", {}),
                "disclaimer_coverage": mcp_result.get("disclaimer_coverage"),
            },
            "findings": mcp_result.get("top_findings", []),
            "policy_id": mcp_result.get("policy_id"),
            "policy_name": mcp_result.get("policy_name"),
            "attachments": (
                {"pdf_report_path": mcp_result.get("pdf_report_path")}
                if mcp_result.get("pdf_report_path")
                else {}
            ),
        }

    @staticmethod
    def build_result_content(
        summary: AuditSummary,
        executive_summary_md: Optional[str] = None,
    ) -> str:
        """
        Build human-readable audit result content.

        Args:
            summary: Audit summary with findings counts
            executive_summary_md: Optional executive summary markdown

        Returns:
            Formatted markdown content
        """
        content = "**Resultado de Auditoría**\n\n"

        # Add executive summary if available
        if executive_summary_md:
            content += f"{executive_summary_md}\n\n"
            content += "---\n\n"

        # Add auditor breakdown
        if summary.findings_by_category:
            content += "**Desglose por auditor:**\n\n"
            for category, count in summary.findings_by_category.items():
                display_name = AUDITOR_DISPLAY_NAMES.get(category, category)
                content += (
                    f"- {display_name}: {count} hallazgo{'s' if count != 1 else ''}\n"
                )
            content += "\n"

        # Critical findings (highest priority)
        if summary.critical > 0:
            content += f"⚠️ **ATENCIÓN:** {summary.critical} {'problema crítico' if summary.critical == 1 else 'problemas críticos'} {'detectado' if summary.critical == 1 else 'detectados'}\n"
            content += "_Corrección obligatoria antes de publicar_\n\n"

        # High priority findings
        if summary.high > 0:
            content += f"📝 **{summary.high} recomendación{'' if summary.high == 1 else 'es'}** de prioridad alta\n"
            content += "_Se sugiere revisar para cumplir estándares corporativos_\n\n"

        # Medium and Low together
        if summary.medium > 0 or summary.low > 0:
            suggestions_count = summary.medium + summary.low
            content += f"✓ **{suggestions_count} sugerencia{'' if suggestions_count == 1 else 's'}** opcional{'' if suggestions_count == 1 else 'es'}\n"
            content += "_Mejoras de estilo y calidad_\n\n"

        # Perfect document
        if summary.total_findings == 0:
            content += "✅ **Documento aprobado**\n"
            content += "_Cumple con todos los estándares de calidad_\n\n"

        # Footer
        content += "---\n"
        content += f"_Análisis completado • {summary.duration_ms}ms_\n"

        return content

    @staticmethod
    def build_audit_artifact(
        filename: str,
        validation_event: Dict[str, Any],
        findings: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Build audit artifact for UI display.

        Args:
            filename: Document filename
            validation_event: Validation complete event
            findings: List of findings from audit

        Returns:
            Audit artifact dict for UI
        """
        # Group findings by category
        categories = {}
        for finding in findings:
            category = finding.get("category", "Sin categoría")
            if category not in categories:
                categories[category] = []
            categories[category].append(finding)

        summary = validation_event.get("summary", {})
        findings_by_severity = summary.get("findings_by_severity", {})

        return {
            "type": "audit_report_ui",
            "doc_name": filename,
            "metadata": {
                "display_name": filename,
                "filename": filename,
                "policy_used": {
                    "id": validation_event.get("policy_id"),
                    "name": validation_event.get("policy_name", "N/D"),
                },
                "attachments": validation_event.get("attachments", {}),
                "validation_report_id": validation_event.get("validation_report_id"),
                "report_pdf_url": validation_event.get("attachments", {}).get(
                    "pdf_report_path"
                ),
            },
            "stats": {
                "critical": findings_by_severity.get("critical", 0),
                "high": findings_by_severity.get("high", 0),
                "medium": findings_by_severity.get("medium", 0),
                "low": findings_by_severity.get("low", 0),
                "total": summary.get("total_findings", 0),
            },
            "categories": categories,
            "actions": [],
            "payload": validation_event,
        }

    @staticmethod
    def build_message_metadata(
        document_id: str,
        filename: str,
        validation_event: Dict[str, Any],
        artifact: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build metadata for assistant message persistence.

        Args:
            document_id: Document ID
            filename: Document filename
            validation_event: Validation complete event
            artifact: Audit artifact

        Returns:
            Message metadata dict
        """
        report_pdf_url = artifact.get("metadata", {}).get("report_pdf_url")
        attachments = validation_event.get("attachments", {})
        validation_report_id = validation_event.get("validation_report_id")

        return {
            "audit_completed": True,
            "document_id": document_id,
            "filename": filename,
            "job_id": validation_event.get("job_id"),
            "artifact": artifact,
            "report_pdf_url": report_pdf_url,
            "attachments": attachments,
            "validation_report_id": validation_report_id,
            "decision_metadata": {
                "report_pdf_url": report_pdf_url,
                "attachments": attachments,
                "audit_artifact": artifact,
                "validation_report_id": validation_report_id,
            },
        }

    @staticmethod
    def build_validation_report_data(
        document_id: str,
        user_id: str,
        mcp_result: Dict[str, Any],
        validation_event: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build data for ValidationReport persistence.

        Args:
            document_id: Document ID
            user_id: User ID
            mcp_result: Raw MCP result
            validation_event: Validation complete event

        Returns:
            Dict suitable for ValidationReport model
        """
        summary = validation_event.get("summary", {})

        return {
            "document_id": document_id,
            "user_id": user_id,
            "job_id": mcp_result.get("job_id") or str(uuid4()),
            "status": "done" if mcp_result.get("status") == "completed" else "error",
            "client_name": mcp_result.get("policy_name"),
            "auditors_enabled": {
                "disclaimer": True,
                "format": True,
                "typography": True,
                "grammar": True,
                "logo": True,
                "color_palette": True,
                "entity_consistency": True,
                "semantic_consistency": True,
            },
            "findings": mcp_result.get("top_findings", []),
            "summary": {
                "total_findings": summary.get("total_findings", 0),
                "findings_by_severity": summary.get("findings_by_severity", {}),
                "findings_by_category": summary.get("findings_by_category", {}),
                "disclaimer_coverage": mcp_result.get("disclaimer_coverage"),
                "policy_id": mcp_result.get("policy_id"),
                "policy_name": mcp_result.get("policy_name"),
                "validation_duration_ms": summary.get("duration_ms", 0),
            },
            "attachments": validation_event.get("attachments", {}),
        }

    @staticmethod
    def build_start_event(filename: str) -> str:
        """Build start content for audit streaming."""
        return f"🔍 Analizando **{filename}**\n\n"

    @staticmethod
    def build_meta_event(
        chat_id: str,
        user_message_id: str,
        model: str,
        document_id: str,
        filename: str,
    ) -> Dict[str, Any]:
        """Build metadata SSE event for audit streaming."""
        return {
            "event": "meta",
            "data": json.dumps(
                {
                    "chat_id": chat_id,
                    "user_message_id": user_message_id,
                    "model": model,
                    "audit_streaming": True,
                    "document_id": document_id,
                    "filename": filename,
                }
            ),
        }

    @staticmethod
    def build_chunk_event(
        content: str, audit_event: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Build chunk SSE event with optional audit event."""
        data = {"content": content}
        if audit_event:
            data["audit_event"] = audit_event

        return {
            "event": "chunk",
            "data": json.dumps(data),
        }

    @staticmethod
    def build_done_event(
        message_id: str,
        content: str,
        model: str,
        chat_id: str,
        metadata: Dict[str, Any],
        artifact: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build done SSE event for audit completion."""
        done_data = {
            "message_id": message_id,
            "content": content,
            "model": model,
            "chat_id": chat_id,
            "metadata": metadata,
        }

        if artifact:
            done_data["artifact"] = artifact

        return {
            "event": "done",
            "data": json.dumps(done_data),
        }

    @staticmethod
    def build_error_event(
        error_type: str,
        message: str,
        details: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build error SSE event."""
        data = {
            "error": error_type,
            "message": message,
        }
        if details:
            data["details"] = details

        return {
            "event": "error",
            "data": json.dumps(data),
        }

    @staticmethod
    async def persist_validation_report(
        document_id: str,
        user_id: str,
        mcp_result: Dict[str, Any],
        validation_event: Dict[str, Any],
        summary: AuditSummary,
    ) -> Optional[str]:
        """
        Persist ValidationReport to MongoDB.

        Args:
            document_id: Document ID
            user_id: User ID
            mcp_result: Raw MCP result
            validation_event: Validation complete event (will be mutated with report ID)
            summary: Audit summary for logging

        Returns:
            validation_report_id if successful, None otherwise
        """
        # Lazy import to avoid circular dependencies
        from ...models.validation_report import ValidationReport

        try:
            report_data = AuditResponseBuilder.build_validation_report_data(
                document_id=document_id,
                user_id=user_id,
                mcp_result=mcp_result,
                validation_event=validation_event,
            )
            validation_report_doc = ValidationReport(**report_data)
            await validation_report_doc.insert()
            validation_report_id = str(validation_report_doc.id)

            # Mutate the event to include the report ID
            validation_event["validation_report_id"] = validation_report_id

            logger.info(
                "MCP audit: ValidationReport persisted",
                validation_report_id=validation_report_id,
                findings=summary.total_findings,
            )
            return validation_report_id

        except Exception as persist_exc:
            logger.error(
                "MCP audit: failed to persist ValidationReport",
                error=str(persist_exc),
                exc_type=type(persist_exc).__name__,
            )
            return None

    @staticmethod
    def process_mcp_result(
        mcp_result: Dict[str, Any],
        document_id: str,
        user_id: str,
        filename: str,
    ) -> AuditResult:
        """
        Process MCP audit result into structured response.

        This is the main entry point for processing audit results.

        Args:
            mcp_result: Result from MCP auditor service
            document_id: Document ID
            user_id: User ID
            filename: Document filename

        Returns:
            AuditResult with all processed data
        """
        try:
            # Extract summary
            summary = AuditResponseBuilder.extract_summary(mcp_result)

            # Build validation event
            validation_event = AuditResponseBuilder.build_validation_complete_event(
                mcp_result, filename
            )

            # Build result content
            content = AuditResponseBuilder.build_result_content(
                summary,
                executive_summary_md=mcp_result.get("executive_summary_markdown"),
            )

            # Build artifact
            artifact = AuditResponseBuilder.build_audit_artifact(
                filename=filename,
                validation_event=validation_event,
                findings=mcp_result.get("top_findings", []),
            )

            logger.info(
                "audit_response_builder.processed",
                document_id=document_id,
                total_findings=summary.total_findings,
                duration_ms=summary.duration_ms,
            )

            return AuditResult(
                success=True,
                content=content,
                validation_event=validation_event,
                artifact=artifact,
                validation_report_id=None,  # Set after persistence
            )

        except Exception as e:
            logger.error(
                "audit_response_builder.process_failed",
                error=str(e),
                exc_type=type(e).__name__,
                document_id=document_id,
            )

            return AuditResult(
                success=False,
                content="",
                validation_event=None,
                artifact=None,
                validation_report_id=None,
                error_message=str(e),
                error_type=type(e).__name__,
            )
