"""
Unit tests for AuditResponseBuilder service.

Tests cover:
- Summary extraction
- Validation event building
- Result content generation
- Artifact building
- Metadata building
- SSE event building
- MCP result processing
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.streaming.audit_response_builder import (
    AuditResponseBuilder,
    AuditResult,
    AuditSummary,
)


@pytest.fixture
def sample_mcp_result():
    """Sample MCP audit result."""
    return {
        "job_id": "job-123",
        "status": "completed",
        "total_findings": 5,
        "findings_by_severity": {
            "critical": 1,
            "high": 2,
            "medium": 1,
            "low": 1,
        },
        "findings_by_category": {
            "grammar": 2,
            "format": 2,
            "compliance": 1,
        },
        "validation_duration_ms": 1500,
        "top_findings": [
            {"category": "grammar", "severity": "high", "message": "Typo found"},
            {"category": "format", "severity": "medium", "message": "Margin issue"},
        ],
        "policy_id": "policy-001",
        "policy_name": "Corporate Standard",
        "pdf_report_path": "/reports/audit-123.pdf",
        "executive_summary_markdown": "## Executive Summary\nDocument reviewed.",
        "disclaimer_coverage": 0.95,
    }


@pytest.mark.unit
class TestAuditResult:
    """Tests for AuditResult dataclass."""

    def test_successful_result(self):
        """Should represent successful audit."""
        result = AuditResult(
            success=True,
            content="Audit complete",
            validation_event={"type": "validation_complete"},
            artifact={"type": "audit_report_ui"},
            validation_report_id="report-123",
        )

        assert result.success is True
        assert result.content == "Audit complete"
        assert result.error_message is None

    def test_failed_result(self):
        """Should represent failed audit."""
        result = AuditResult(
            success=False,
            content="",
            validation_event=None,
            artifact=None,
            validation_report_id=None,
            error_message="Connection failed",
            error_type="ConnectionError",
        )

        assert result.success is False
        assert result.error_message == "Connection failed"
        assert result.error_type == "ConnectionError"


@pytest.mark.unit
class TestAuditSummary:
    """Tests for AuditSummary dataclass."""

    def test_summary_initialization(self):
        """Should initialize with correct values."""
        summary = AuditSummary(
            total_findings=10,
            critical=2,
            high=3,
            medium=3,
            low=2,
            duration_ms=1200,
            findings_by_category={"grammar": 5, "format": 5},
        )

        assert summary.total_findings == 10
        assert summary.critical == 2
        assert summary.high == 3
        assert summary.duration_ms == 1200
        assert len(summary.findings_by_category) == 2

    def test_summary_default_categories(self):
        """Should default findings_by_category to empty dict."""
        summary = AuditSummary(
            total_findings=0,
            critical=0,
            high=0,
            medium=0,
            low=0,
            duration_ms=100,
        )

        assert summary.findings_by_category == {}


@pytest.mark.unit
class TestExtractSummary:
    """Tests for extract_summary method."""

    def test_extracts_all_fields(self, sample_mcp_result):
        """Should extract all summary fields."""
        summary = AuditResponseBuilder.extract_summary(sample_mcp_result)

        assert summary.total_findings == 5
        assert summary.critical == 1
        assert summary.high == 2
        assert summary.medium == 1
        assert summary.low == 1
        assert summary.duration_ms == 1500
        assert "grammar" in summary.findings_by_category

    def test_handles_missing_fields(self):
        """Should handle missing fields with defaults."""
        result = {}
        summary = AuditResponseBuilder.extract_summary(result)

        assert summary.total_findings == 0
        assert summary.critical == 0
        assert summary.duration_ms == 0
        assert summary.findings_by_category == {}


@pytest.mark.unit
class TestBuildValidationCompleteEvent:
    """Tests for build_validation_complete_event method."""

    def test_builds_complete_event(self, sample_mcp_result):
        """Should build complete validation event."""
        event = AuditResponseBuilder.build_validation_complete_event(
            sample_mcp_result, "document.pdf"
        )

        assert event["type"] == "validation_complete"
        assert event["job_id"] == "job-123"
        assert event["status"] == "completed"
        assert event["filename"] == "document.pdf"
        assert event["duration_ms"] == 1500
        assert event["summary"]["total_findings"] == 5
        assert event["policy_name"] == "Corporate Standard"

    def test_includes_attachments(self, sample_mcp_result):
        """Should include PDF report path in attachments."""
        event = AuditResponseBuilder.build_validation_complete_event(
            sample_mcp_result, "doc.pdf"
        )

        assert "attachments" in event
        assert event["attachments"]["pdf_report_path"] == "/reports/audit-123.pdf"

    def test_empty_attachments_when_no_pdf(self):
        """Should have empty attachments when no PDF."""
        result = {"status": "completed"}
        event = AuditResponseBuilder.build_validation_complete_event(result, "doc.pdf")

        assert event["attachments"] == {}


@pytest.mark.unit
class TestBuildResultContent:
    """Tests for build_result_content method."""

    def test_basic_content_structure(self):
        """Should build basic content structure."""
        summary = AuditSummary(
            total_findings=3,
            critical=0,
            high=1,
            medium=1,
            low=1,
            duration_ms=1000,
        )

        content = AuditResponseBuilder.build_result_content(summary)

        assert "**Resultado de Auditoría**" in content
        assert "1000ms" in content

    def test_includes_executive_summary(self):
        """Should include executive summary when provided."""
        summary = AuditSummary(
            total_findings=0, critical=0, high=0, medium=0, low=0, duration_ms=100
        )
        exec_summary = "## Summary\nAll good!"

        content = AuditResponseBuilder.build_result_content(
            summary, executive_summary_md=exec_summary
        )

        assert "All good!" in content
        assert "---" in content  # Separator after exec summary

    def test_critical_findings_warning(self):
        """Should show warning for critical findings."""
        summary = AuditSummary(
            total_findings=2,
            critical=2,
            high=0,
            medium=0,
            low=0,
            duration_ms=100,
        )

        content = AuditResponseBuilder.build_result_content(summary)

        assert "⚠️" in content
        assert "ATENCIÓN" in content
        assert "críticos" in content
        assert "obligatoria" in content.lower()

    def test_singular_critical(self):
        """Should use singular for one critical."""
        summary = AuditSummary(
            total_findings=1,
            critical=1,
            high=0,
            medium=0,
            low=0,
            duration_ms=100,
        )

        content = AuditResponseBuilder.build_result_content(summary)

        assert "problema crítico" in content

    def test_high_priority_section(self):
        """Should show high priority section."""
        summary = AuditSummary(
            total_findings=3,
            critical=0,
            high=3,
            medium=0,
            low=0,
            duration_ms=100,
        )

        content = AuditResponseBuilder.build_result_content(summary)

        assert "📝" in content
        assert "prioridad alta" in content
        # Check for recommendation (singular or plural, with or without accent)
        assert "recomendaci" in content

    def test_suggestions_section(self):
        """Should show suggestions for medium/low."""
        summary = AuditSummary(
            total_findings=5,
            critical=0,
            high=0,
            medium=3,
            low=2,
            duration_ms=100,
        )

        content = AuditResponseBuilder.build_result_content(summary)

        assert "✓" in content
        assert "5 sugerencias" in content
        assert "opcional" in content

    def test_perfect_document(self):
        """Should show approval for zero findings."""
        summary = AuditSummary(
            total_findings=0,
            critical=0,
            high=0,
            medium=0,
            low=0,
            duration_ms=500,
        )

        content = AuditResponseBuilder.build_result_content(summary)

        assert "✅" in content
        assert "aprobado" in content.lower()

    def test_auditor_breakdown(self):
        """Should include auditor breakdown."""
        summary = AuditSummary(
            total_findings=5,
            critical=0,
            high=0,
            medium=5,
            low=0,
            duration_ms=100,
            findings_by_category={"grammar": 3, "format": 2},
        )

        content = AuditResponseBuilder.build_result_content(summary)

        assert "Desglose por auditor" in content
        assert "3 hallazgos" in content
        assert "2 hallazgos" in content


@pytest.mark.unit
class TestBuildAuditArtifact:
    """Tests for build_audit_artifact method."""

    def test_artifact_structure(self):
        """Should build correct artifact structure."""
        validation_event = {
            "policy_id": "policy-001",
            "policy_name": "Standard",
            "attachments": {"pdf_report_path": "/report.pdf"},
            "summary": {
                "total_findings": 3,
                "findings_by_severity": {"high": 1, "medium": 2},
            },
        }
        findings = [
            {"category": "grammar", "severity": "high", "message": "Error"},
            {"category": "grammar", "severity": "medium", "message": "Warning"},
            {"category": "format", "severity": "medium", "message": "Note"},
        ]

        artifact = AuditResponseBuilder.build_audit_artifact(
            "doc.pdf", validation_event, findings
        )

        assert artifact["type"] == "audit_report_ui"
        assert artifact["doc_name"] == "doc.pdf"
        assert artifact["metadata"]["filename"] == "doc.pdf"
        assert artifact["metadata"]["policy_used"]["id"] == "policy-001"

    def test_groups_findings_by_category(self):
        """Should group findings by category."""
        findings = [
            {"category": "grammar", "message": "A"},
            {"category": "grammar", "message": "B"},
            {"category": "format", "message": "C"},
        ]

        artifact = AuditResponseBuilder.build_audit_artifact(
            "doc.pdf", {"summary": {}}, findings
        )

        assert "grammar" in artifact["categories"]
        assert "format" in artifact["categories"]
        assert len(artifact["categories"]["grammar"]) == 2

    def test_stats_from_severity(self):
        """Should extract stats from severity breakdown."""
        validation_event = {
            "summary": {
                "total_findings": 6,
                "findings_by_severity": {
                    "critical": 1,
                    "high": 2,
                    "medium": 2,
                    "low": 1,
                },
            }
        }

        artifact = AuditResponseBuilder.build_audit_artifact(
            "doc.pdf", validation_event, []
        )

        assert artifact["stats"]["critical"] == 1
        assert artifact["stats"]["high"] == 2
        assert artifact["stats"]["total"] == 6


@pytest.mark.unit
class TestBuildMessageMetadata:
    """Tests for build_message_metadata method."""

    def test_includes_all_fields(self):
        """Should include all required fields."""
        validation_event = {
            "job_id": "job-123",
            "attachments": {"pdf_report_path": "/report.pdf"},
            "validation_report_id": "report-456",
        }
        artifact = {
            "metadata": {"report_pdf_url": "/report.pdf"}
        }

        metadata = AuditResponseBuilder.build_message_metadata(
            document_id="doc-789",
            filename="document.pdf",
            validation_event=validation_event,
            artifact=artifact,
        )

        assert metadata["audit_completed"] is True
        assert metadata["document_id"] == "doc-789"
        assert metadata["filename"] == "document.pdf"
        assert metadata["job_id"] == "job-123"
        assert metadata["report_pdf_url"] == "/report.pdf"
        assert "decision_metadata" in metadata


@pytest.mark.unit
class TestBuildValidationReportData:
    """Tests for build_validation_report_data method."""

    def test_builds_report_data(self, sample_mcp_result):
        """Should build complete report data."""
        validation_event = {"summary": {"total_findings": 5}}

        data = AuditResponseBuilder.build_validation_report_data(
            document_id="doc-123",
            user_id="user-456",
            mcp_result=sample_mcp_result,
            validation_event=validation_event,
        )

        assert data["document_id"] == "doc-123"
        assert data["user_id"] == "user-456"
        assert data["job_id"] == "job-123"
        assert data["status"] == "done"
        assert data["client_name"] == "Corporate Standard"

    def test_status_mapping(self):
        """Should map status correctly."""
        completed_result = {"status": "completed"}
        failed_result = {"status": "failed"}

        completed_data = AuditResponseBuilder.build_validation_report_data(
            "doc", "user", completed_result, {"summary": {}}
        )
        failed_data = AuditResponseBuilder.build_validation_report_data(
            "doc", "user", failed_result, {"summary": {}}
        )

        assert completed_data["status"] == "done"
        assert failed_data["status"] == "error"

    def test_generates_job_id_if_missing(self):
        """Should generate job_id if not in result."""
        result = {}

        data = AuditResponseBuilder.build_validation_report_data(
            "doc", "user", result, {"summary": {}}
        )

        assert data["job_id"] is not None
        assert len(data["job_id"]) > 0


@pytest.mark.unit
class TestBuildStartEvent:
    """Tests for build_start_event method."""

    def test_includes_filename(self):
        """Should include filename in message."""
        content = AuditResponseBuilder.build_start_event("report.pdf")

        assert "report.pdf" in content
        assert "🔍" in content
        assert "Analizando" in content


@pytest.mark.unit
class TestBuildMetaEvent:
    """Tests for build_meta_event method."""

    def test_event_structure(self):
        """Should build correct SSE event."""
        event = AuditResponseBuilder.build_meta_event(
            chat_id="chat-123",
            user_message_id="msg-456",
            model="saptiva-turbo",
            document_id="doc-789",
            filename="report.pdf",
        )

        assert event["event"] == "meta"

        data = json.loads(event["data"])
        assert data["chat_id"] == "chat-123"
        assert data["audit_streaming"] is True
        assert data["filename"] == "report.pdf"


@pytest.mark.unit
class TestBuildChunkEvent:
    """Tests for build_chunk_event method."""

    def test_basic_chunk(self):
        """Should build basic chunk event."""
        event = AuditResponseBuilder.build_chunk_event("Processing...")

        assert event["event"] == "chunk"

        data = json.loads(event["data"])
        assert data["content"] == "Processing..."

    def test_chunk_with_audit_event(self):
        """Should include audit event when provided."""
        audit_event = {"type": "progress", "percent": 50}
        event = AuditResponseBuilder.build_chunk_event("Half done", audit_event)

        data = json.loads(event["data"])
        assert data["audit_event"] == audit_event


@pytest.mark.unit
class TestBuildDoneEvent:
    """Tests for build_done_event method."""

    def test_done_event_structure(self):
        """Should build complete done event."""
        metadata = {"audit_completed": True}
        event = AuditResponseBuilder.build_done_event(
            message_id="msg-123",
            content="Audit complete",
            model="saptiva-turbo",
            chat_id="chat-456",
            metadata=metadata,
        )

        assert event["event"] == "done"

        data = json.loads(event["data"])
        assert data["message_id"] == "msg-123"
        assert data["content"] == "Audit complete"
        assert data["metadata"]["audit_completed"] is True

    def test_done_event_with_artifact(self):
        """Should include artifact when provided."""
        artifact = {"type": "audit_report_ui"}
        event = AuditResponseBuilder.build_done_event(
            message_id="msg-123",
            content="Done",
            model="model",
            chat_id="chat",
            metadata={},
            artifact=artifact,
        )

        data = json.loads(event["data"])
        assert data["artifact"] == artifact


@pytest.mark.unit
class TestBuildErrorEvent:
    """Tests for build_error_event method."""

    def test_basic_error(self):
        """Should build basic error event."""
        event = AuditResponseBuilder.build_error_event(
            error_type="ValidationError",
            message="Document invalid",
        )

        assert event["event"] == "error"

        data = json.loads(event["data"])
        assert data["error"] == "ValidationError"
        assert data["message"] == "Document invalid"

    def test_error_with_details(self):
        """Should include details when provided."""
        event = AuditResponseBuilder.build_error_event(
            error_type="ProcessingError",
            message="Failed",
            details="Connection timeout",
        )

        data = json.loads(event["data"])
        assert data["details"] == "Connection timeout"


@pytest.mark.unit
class TestPersistValidationReport:
    """Tests for persist_validation_report method."""

    @pytest.mark.asyncio
    async def test_successful_persistence(self, sample_mcp_result):
        """Should persist report and return ID."""
        mock_report = MagicMock()
        mock_report.id = "report-123"
        mock_report.insert = AsyncMock()

        validation_event = {"summary": {}}
        summary = AuditSummary(
            total_findings=5, critical=0, high=0, medium=0, low=0, duration_ms=100
        )

        # The ValidationReport is imported lazily inside the method
        with patch(
            "src.models.validation_report.ValidationReport",
            return_value=mock_report,
        ):
            result = await AuditResponseBuilder.persist_validation_report(
                document_id="doc-123",
                user_id="user-456",
                mcp_result=sample_mcp_result,
                validation_event=validation_event,
                summary=summary,
            )

        assert result == "report-123"
        assert validation_event["validation_report_id"] == "report-123"

    @pytest.mark.asyncio
    async def test_handles_persistence_error(self, sample_mcp_result):
        """Should handle persistence errors gracefully."""
        validation_event = {"summary": {}}
        summary = AuditSummary(
            total_findings=0, critical=0, high=0, medium=0, low=0, duration_ms=100
        )

        # The ValidationReport is imported lazily inside the method
        with patch(
            "src.models.validation_report.ValidationReport",
            side_effect=Exception("DB Error"),
        ):
            result = await AuditResponseBuilder.persist_validation_report(
                document_id="doc-123",
                user_id="user-456",
                mcp_result=sample_mcp_result,
                validation_event=validation_event,
                summary=summary,
            )

        assert result is None


@pytest.mark.unit
class TestProcessMcpResult:
    """Tests for process_mcp_result method."""

    def test_successful_processing(self, sample_mcp_result):
        """Should process result successfully."""
        result = AuditResponseBuilder.process_mcp_result(
            mcp_result=sample_mcp_result,
            document_id="doc-123",
            user_id="user-456",
            filename="report.pdf",
        )

        assert result.success is True
        assert result.content != ""
        assert result.validation_event is not None
        assert result.artifact is not None
        assert result.error_message is None

    def test_handles_processing_error(self):
        """Should handle errors gracefully."""
        # Invalid result that might cause issues
        bad_result = None

        result = AuditResponseBuilder.process_mcp_result(
            mcp_result=bad_result,
            document_id="doc-123",
            user_id="user-456",
            filename="report.pdf",
        )

        assert result.success is False
        assert result.error_message is not None
        assert result.error_type is not None


@pytest.mark.unit
class TestAuditResponseBuilderIntegration:
    """Integration tests for AuditResponseBuilder."""

    def test_full_audit_flow(self, sample_mcp_result):
        """Should process complete audit flow."""
        # Process result
        audit_result = AuditResponseBuilder.process_mcp_result(
            mcp_result=sample_mcp_result,
            document_id="doc-001",
            user_id="user-001",
            filename="annual_report.pdf",
        )

        assert audit_result.success is True

        # Build message metadata
        metadata = AuditResponseBuilder.build_message_metadata(
            document_id="doc-001",
            filename="annual_report.pdf",
            validation_event=audit_result.validation_event,
            artifact=audit_result.artifact,
        )

        assert metadata["audit_completed"] is True
        assert metadata["artifact"] == audit_result.artifact

        # Build done event
        done_event = AuditResponseBuilder.build_done_event(
            message_id="msg-001",
            content=audit_result.content,
            model="saptiva-turbo",
            chat_id="chat-001",
            metadata=metadata,
            artifact=audit_result.artifact,
        )

        assert done_event["event"] == "done"
