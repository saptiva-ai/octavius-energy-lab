"""
Unit tests for audit_utils module.

Tests:
- TECHNICAL_WHITELIST constant
- _should_filter_low_noise function
- build_audit_report_response function
- _extract_summary_text function
- summarize_audit_for_message function
"""

from typing import Any, Dict

import pytest

from src.schemas.audit import AuditFinding, AuditReportResponse, AuditStats
from src.services.audit_utils import (
    TECHNICAL_WHITELIST,
    _extract_summary_text,
    _should_filter_low_noise,
    build_audit_report_response,
    summarize_audit_for_message,
)

pytestmark = [pytest.mark.unit]


class TestTechnicalWhitelist:
    """Test TECHNICAL_WHITELIST constant."""

    def test_is_set(self):
        """Test TECHNICAL_WHITELIST is a set."""
        assert isinstance(TECHNICAL_WHITELIST, set)

    def test_contains_expected_terms(self):
        """Test contains expected technical terms."""
        expected_terms = {"genai", "deployment", "k8s", "frida", "billing"}
        for term in expected_terms:
            assert term in TECHNICAL_WHITELIST

    def test_all_items_are_lowercase(self):
        """Test all items are lowercase."""
        for term in TECHNICAL_WHITELIST:
            assert term == term.lower()


class TestShouldFilterLowNoise:
    """Test _should_filter_low_noise function."""

    def test_returns_false_for_high_severity(self):
        """Test returns False for high severity."""
        result = _should_filter_low_noise("Contains genai term", "high")
        assert result is False

    def test_returns_false_for_medium_severity(self):
        """Test returns False for medium severity."""
        result = _should_filter_low_noise("Contains k8s term", "medium")
        assert result is False

    def test_returns_false_for_critical_severity(self):
        """Test returns False for critical severity."""
        result = _should_filter_low_noise("Deployment issue", "critical")
        assert result is False

    def test_returns_true_for_low_severity_with_whitelist_term(self):
        """Test returns True for low severity with whitelist term."""
        result = _should_filter_low_noise("Issue with genai configuration", "low")
        assert result is True

    def test_returns_true_for_low_severity_with_k8s(self):
        """Test returns True for low severity with k8s term."""
        result = _should_filter_low_noise("k8s namespace configuration", "low")
        assert result is True

    def test_returns_false_for_low_severity_without_whitelist_term(self):
        """Test returns False for low severity without whitelist term."""
        result = _should_filter_low_noise("Regular security issue", "low")
        assert result is False

    def test_case_insensitive_matching(self):
        """Test case insensitive matching."""
        result = _should_filter_low_noise("GENAI Configuration", "low")
        assert result is True

    def test_matches_partial_terms(self):
        """Test matches partial terms."""
        result = _should_filter_low_noise("on-premise deployment", "low")
        assert result is True


class TestBuildAuditReportResponse:
    """Test build_audit_report_response function."""

    def test_returns_audit_report_response(self):
        """Test returns AuditReportResponse."""
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=[],
        )
        assert isinstance(result, AuditReportResponse)

    def test_sets_doc_name(self):
        """Test sets doc_name correctly."""
        result = build_audit_report_response(
            doc_name="document.pdf",
            findings=[],
        )
        assert result.doc_name == "document.pdf"

    def test_filters_low_noise_findings(self):
        """Test filters low noise findings."""
        findings = [
            {"severity": "low", "message": "genai configuration issue"},
            {"severity": "high", "message": "Security vulnerability"},
        ]
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=findings,
        )
        # Only high severity should remain
        assert result.stats.total == 1
        assert result.stats.high == 1
        assert result.stats.low == 0

    def test_normalizes_finding_severity(self):
        """Test normalizes finding severity to lowercase."""
        findings = [
            {"severity": "HIGH", "message": "Test issue"},
            {"severity": "Medium", "message": "Another issue"},
        ]
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=findings,
        )
        all_findings = []
        for cat_findings in result.categories.values():
            all_findings.extend(cat_findings)

        severities = [f.severity for f in all_findings]
        assert "high" in severities
        assert "medium" in severities

    def test_default_severity_is_low(self):
        """Test default severity is low when not provided."""
        findings = [
            {"message": "Issue without severity"},
        ]
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=findings,
        )
        # Low severity without whitelist terms should be included
        all_findings = []
        for cat_findings in result.categories.values():
            all_findings.extend(cat_findings)

        if all_findings:
            assert all_findings[0].severity == "low"

    def test_extracts_message_from_different_fields(self):
        """Test extracts message from various possible fields."""
        findings = [
            {"issue": "Issue from issue field", "severity": "high"},
            {"description": "Issue from description field", "severity": "high"},
        ]
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=findings,
        )
        all_findings = []
        for cat_findings in result.categories.values():
            all_findings.extend(cat_findings)

        messages = [f.message for f in all_findings]
        assert "Issue from issue field" in messages
        assert "Issue from description field" in messages

    def test_groups_findings_by_category(self):
        """Test groups findings by category."""
        findings = [
            {"severity": "high", "message": "Issue 1", "category": "security"},
            {"severity": "high", "message": "Issue 2", "category": "security"},
            {"severity": "high", "message": "Issue 3", "category": "compliance"},
        ]
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=findings,
        )
        assert "security" in result.categories
        assert "compliance" in result.categories
        assert len(result.categories["security"]) == 2
        assert len(result.categories["compliance"]) == 1

    def test_default_category_is_uncategorized(self):
        """Test default category is 'uncategorized'."""
        findings = [
            {"severity": "high", "message": "Issue without category"},
        ]
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=findings,
        )
        assert "uncategorized" in result.categories

    def test_calculates_stats_correctly(self):
        """Test calculates stats correctly."""
        findings = [
            {"severity": "critical", "message": "Critical issue"},
            {"severity": "high", "message": "High issue 1"},
            {"severity": "high", "message": "High issue 2"},
            {"severity": "medium", "message": "Medium issue"},
        ]
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=findings,
        )
        assert result.stats.critical == 1
        assert result.stats.high == 2
        assert result.stats.medium == 1
        assert result.stats.low == 0
        assert result.stats.total == 4

    def test_extracts_page_from_location_dict(self):
        """Test extracts page from location dict."""
        findings = [
            {
                "severity": "high",
                "message": "Issue",
                "location": {"page": 5},
            },
        ]
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=findings,
        )
        all_findings = []
        for cat_findings in result.categories.values():
            all_findings.extend(cat_findings)

        assert all_findings[0].page == 5

    def test_extracts_page_from_direct_field(self):
        """Test extracts page from direct field."""
        findings = [
            {
                "severity": "high",
                "message": "Issue",
                "page": 10,
            },
        ]
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=findings,
        )
        all_findings = []
        for cat_findings in result.categories.values():
            all_findings.extend(cat_findings)

        assert all_findings[0].page == 10

    def test_includes_actions(self):
        """Test includes actions."""
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=[],
            actions=["Fix issue A", "Update policy B"],
        )
        assert result.actions == ["Fix issue A", "Update policy B"]

    def test_includes_metadata(self):
        """Test includes metadata."""
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=[],
            metadata={"source": "test"},
        )
        assert result.metadata["source"] == "test"

    def test_includes_summary_in_metadata(self):
        """Test includes summary in metadata when provided."""
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=[],
            summary="This is a summary",
        )
        assert result.metadata["summary"] == "This is a summary"

    def test_handles_empty_findings(self):
        """Test handles empty findings list."""
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=[],
        )
        assert result.stats.total == 0

    def test_handles_none_findings(self):
        """Test handles None findings."""
        result = build_audit_report_response(
            doc_name="test.pdf",
            findings=None,
        )
        assert result.stats.total == 0


class TestExtractSummaryText:
    """Test _extract_summary_text function."""

    def test_returns_none_for_none_input(self):
        """Test returns None for None input."""
        result = _extract_summary_text(None)
        assert result is None

    def test_returns_string_directly(self):
        """Test returns string directly."""
        result = _extract_summary_text("This is a summary")
        assert result == "This is a summary"

    def test_strips_whitespace_from_string(self):
        """Test strips whitespace from string."""
        result = _extract_summary_text("  Summary with spaces  ")
        assert result == "Summary with spaces"

    def test_extracts_text_key_from_dict(self):
        """Test extracts 'text' key from dict."""
        result = _extract_summary_text({"text": "Summary text"})
        assert result == "Summary text"

    def test_extracts_summary_key_from_dict(self):
        """Test extracts 'summary' key from dict."""
        result = _extract_summary_text({"summary": "Summary content"})
        assert result == "Summary content"

    def test_extracts_overview_key_from_dict(self):
        """Test extracts 'overview' key from dict."""
        result = _extract_summary_text({"overview": "Overview content"})
        assert result == "Overview content"

    def test_extracts_short_key_from_dict(self):
        """Test extracts 'short' key from dict."""
        result = _extract_summary_text({"short": "Short summary"})
        assert result == "Short summary"

    def test_priority_order_text_first(self):
        """Test 'text' key has priority over other keys."""
        result = _extract_summary_text({
            "text": "From text",
            "summary": "From summary",
        })
        assert result == "From text"

    def test_returns_none_for_empty_dict(self):
        """Test returns None for empty dict."""
        result = _extract_summary_text({})
        assert result is None

    def test_returns_none_for_dict_without_known_keys(self):
        """Test returns None for dict without known keys."""
        result = _extract_summary_text({"other_key": "value"})
        assert result is None


class TestSummarizeAuditForMessage:
    """Test summarize_audit_for_message function."""

    def test_includes_doc_name(self):
        """Test includes document name."""
        artifact = AuditReportResponse(
            doc_name="test.pdf",
            stats=AuditStats(critical=0, high=0, medium=0, low=0, total=0),
            categories={},
            actions=[],
            metadata={},
        )
        result = summarize_audit_for_message("test.pdf", artifact)
        assert "test.pdf" in result

    def test_includes_stats_summary(self):
        """Test includes stats summary."""
        artifact = AuditReportResponse(
            doc_name="test.pdf",
            stats=AuditStats(critical=1, high=2, medium=3, low=4, total=10),
            categories={},
            actions=[],
            metadata={},
        )
        result = summarize_audit_for_message("test.pdf", artifact)
        assert "1 crítico" in result
        assert "2 alto" in result
        assert "3 medio" in result
        assert "4 bajo" in result

    def test_includes_summary_text(self):
        """Test includes summary text when provided."""
        artifact = AuditReportResponse(
            doc_name="test.pdf",
            stats=AuditStats(critical=0, high=0, medium=0, low=0, total=0),
            categories={},
            actions=[],
            metadata={},
        )
        result = summarize_audit_for_message(
            "test.pdf", artifact, summary_raw="This is the summary"
        )
        assert "This is the summary" in result

    def test_clips_long_summary(self):
        """Test clips summary longer than 320 characters."""
        long_summary = "A" * 400
        artifact = AuditReportResponse(
            doc_name="test.pdf",
            stats=AuditStats(critical=0, high=0, medium=0, low=0, total=0),
            categories={},
            actions=[],
            metadata={},
        )
        result = summarize_audit_for_message("test.pdf", artifact, summary_raw=long_summary)
        assert "..." in result
        # Should be clipped
        assert "A" * 400 not in result

    def test_includes_top_findings(self):
        """Test includes top findings."""
        finding = AuditFinding(
            id="1",
            category="security",
            severity="high",
            message="Security issue found",
            page=1,
            suggestion=None,
            rule=None,
            raw={},
        )
        artifact = AuditReportResponse(
            doc_name="test.pdf",
            stats=AuditStats(critical=0, high=1, medium=0, low=0, total=1),
            categories={"security": [finding]},
            actions=[],
            metadata={},
        )
        result = summarize_audit_for_message("test.pdf", artifact)
        assert "Security issue found" in result
        assert "[Alto]" in result

    def test_limits_findings_to_max_findings(self):
        """Test limits findings to max_findings parameter."""
        findings = [
            AuditFinding(
                id=str(i),
                category="security",
                severity="high",
                message=f"Issue {i}",
                page=i,
                suggestion=None,
                rule=None,
                raw={},
            )
            for i in range(10)
        ]
        artifact = AuditReportResponse(
            doc_name="test.pdf",
            stats=AuditStats(critical=0, high=10, medium=0, low=0, total=10),
            categories={"security": findings},
            actions=[],
            metadata={},
        )
        result = summarize_audit_for_message("test.pdf", artifact, max_findings=2)
        # Should only include 2 findings
        assert "Issue 0" in result
        assert "Issue 1" in result
        assert "Issue 9" not in result

    def test_sorts_findings_by_severity(self):
        """Test sorts findings by severity (critical first)."""
        findings_low = AuditFinding(
            id="1",
            category="test",
            severity="low",
            message="Low severity issue",
            page=1,
            suggestion=None,
            rule=None,
            raw={},
        )
        findings_critical = AuditFinding(
            id="2",
            category="test",
            severity="critical",
            message="Critical severity issue",
            page=1,
            suggestion=None,
            rule=None,
            raw={},
        )
        artifact = AuditReportResponse(
            doc_name="test.pdf",
            stats=AuditStats(critical=1, high=0, medium=0, low=1, total=2),
            categories={"test": [findings_low, findings_critical]},
            actions=[],
            metadata={},
        )
        result = summarize_audit_for_message("test.pdf", artifact)
        # Critical should appear before low
        critical_pos = result.find("Critical severity issue")
        low_pos = result.find("Low severity issue")
        assert critical_pos < low_pos

    def test_includes_cta_text(self):
        """Test includes call-to-action text."""
        artifact = AuditReportResponse(
            doc_name="test.pdf",
            stats=AuditStats(critical=0, high=0, medium=0, low=0, total=0),
            categories={},
            actions=[],
            metadata={},
        )
        result = summarize_audit_for_message("test.pdf", artifact)
        assert "¿Qué sigue?" in result
        assert "panel lateral" in result

    def test_clips_long_finding_message(self):
        """Test clips finding message longer than 220 characters."""
        long_message = "B" * 300
        finding = AuditFinding(
            id="1",
            category="security",
            severity="high",
            message=long_message,
            page=1,
            suggestion=None,
            rule=None,
            raw={},
        )
        artifact = AuditReportResponse(
            doc_name="test.pdf",
            stats=AuditStats(critical=0, high=1, medium=0, low=0, total=1),
            categories={"security": [finding]},
            actions=[],
            metadata={},
        )
        result = summarize_audit_for_message("test.pdf", artifact)
        assert "..." in result
        # Full message should not be present
        assert long_message not in result
