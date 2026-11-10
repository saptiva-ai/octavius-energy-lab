"""
Unit tests for validation_context_formatter module.

Tests:
- ValidationContextFormatter class methods
- inject_validation_context_in_prompt function
- Formatting and truncation behavior
"""

import pytest

from src.services.validation_context_formatter import (
    CHARS_PER_TOKEN,
    MAX_TOKENS,
    ValidationContextFormatter,
    inject_validation_context_in_prompt,
)

pytestmark = [pytest.mark.unit]


class TestConstants:
    """Test module constants."""

    def test_max_tokens_value(self):
        """Test MAX_TOKENS is reasonable."""
        assert MAX_TOKENS == 800

    def test_chars_per_token(self):
        """Test CHARS_PER_TOKEN estimate."""
        assert CHARS_PER_TOKEN == 4


class TestFormatValidationContext:
    """Test format_validation_context method."""

    def test_empty_findings_returns_empty(self):
        """Test empty findings returns empty string."""
        result = ValidationContextFormatter.format_validation_context([])
        assert result == ""

    def test_single_finding(self):
        """Test formatting single finding."""
        findings = [
            {
                "severity": "critical",
                "location": {"page": 5},
                "rule": "disclaimer_coverage",
                "issue": "Disclaimer ausente",
            }
        ]

        result = ValidationContextFormatter.format_validation_context(findings)

        assert "VALIDATION_CONTEXT" in result
        assert "Pág. 5" in result
        assert "Disclaimer ausente" in result
        assert "disclaimer_coverage" in result

    def test_multiple_findings_sorted_by_severity(self):
        """Test findings are sorted by severity."""
        findings = [
            {"severity": "low", "issue": "Minor issue"},
            {"severity": "critical", "issue": "Critical issue"},
            {"severity": "high", "issue": "High issue"},
        ]

        result = ValidationContextFormatter.format_validation_context(findings)

        # Critical should come before high
        critical_pos = result.find("CRÍTICOS")
        high_pos = result.find("ALTOS")

        assert critical_pos < high_pos

    def test_includes_summary_in_header(self):
        """Test summary is included in header."""
        findings = [{"severity": "critical", "issue": "Test"}]
        summary = {"critical": 2, "high": 3}

        result = ValidationContextFormatter.format_validation_context(
            findings, summary=summary
        )

        assert "2 críticos" in result
        assert "3 altos" in result

    def test_header_without_summary(self):
        """Test header without summary uses finding count."""
        findings = [
            {"severity": "critical", "issue": "Issue 1"},
            {"severity": "high", "issue": "Issue 2"},
        ]

        result = ValidationContextFormatter.format_validation_context(findings)

        assert "2 hallazgos" in result

    def test_respects_max_tokens(self):
        """Test output respects max_tokens limit."""
        # Create many findings
        findings = [
            {"severity": "critical", "issue": f"Issue number {i}"}
            for i in range(100)
        ]

        result = ValidationContextFormatter.format_validation_context(
            findings, max_tokens=100
        )

        # Should be within limit (100 * 4 = 400 chars max)
        assert len(result) < 500  # Some buffer for truncation message


class TestFormatHeader:
    """Test _format_header method."""

    def test_with_summary(self):
        """Test header with summary dict."""
        findings = [{"severity": "critical", "issue": "Test"}]
        summary = {"critical": 1, "high": 2, "medium": 0, "low": 3}

        result = ValidationContextFormatter._format_header(findings, summary)

        assert "VALIDATION_CONTEXT" in result
        assert "1 críticos" in result
        assert "2 altos" in result
        assert "3 bajos" in result
        assert "0 medios" not in result  # Zero counts not included

    def test_without_summary(self):
        """Test header without summary."""
        findings = [{"severity": "critical"}, {"severity": "high"}]

        result = ValidationContextFormatter._format_header(findings, None)

        assert "2 hallazgos" in result

    def test_empty_summary(self):
        """Test header with empty summary."""
        findings = [{"severity": "critical"}]
        summary = {}

        result = ValidationContextFormatter._format_header(findings, summary)

        # Should use fallback
        assert "hallazgos" in result


class TestGroupBySeverity:
    """Test _group_by_severity method."""

    def test_groups_correctly(self):
        """Test findings are grouped by severity."""
        findings = [
            {"severity": "critical", "issue": "C1"},
            {"severity": "high", "issue": "H1"},
            {"severity": "critical", "issue": "C2"},
            {"severity": "low", "issue": "L1"},
        ]

        result = ValidationContextFormatter._group_by_severity(findings)

        assert len(result["critical"]) == 2
        assert len(result["high"]) == 1
        assert len(result["low"]) == 1

    def test_missing_severity_defaults_to_low(self):
        """Test findings without severity are treated as low."""
        findings = [{"issue": "No severity"}]

        result = ValidationContextFormatter._group_by_severity(findings)

        assert "low" in result
        assert len(result["low"]) == 1


class TestFormatSeverityGroup:
    """Test _format_severity_group method."""

    def test_formats_critical_group(self):
        """Test critical severity label."""
        findings = [{"issue": "Test issue"}]

        result = ValidationContextFormatter._format_severity_group(
            "critical", findings, max_chars=500
        )

        assert "CRÍTICOS (1)" in result

    def test_formats_high_group(self):
        """Test high severity label."""
        findings = [{"issue": "Test"}]

        result = ValidationContextFormatter._format_severity_group(
            "high", findings, max_chars=500
        )

        assert "ALTOS (1)" in result

    def test_formats_medium_group(self):
        """Test medium severity label."""
        findings = [{"issue": "Test"}]

        result = ValidationContextFormatter._format_severity_group(
            "medium", findings, max_chars=500
        )

        assert "MEDIOS (1)" in result

    def test_formats_low_group(self):
        """Test low severity label."""
        findings = [{"issue": "Test"}]

        result = ValidationContextFormatter._format_severity_group(
            "low", findings, max_chars=500
        )

        assert "BAJOS (1)" in result

    def test_truncates_when_exceeding_max_chars(self):
        """Test truncation when exceeding max_chars."""
        findings = [
            {"issue": f"Long issue text number {i}"} for i in range(20)
        ]

        result = ValidationContextFormatter._format_severity_group(
            "critical", findings, max_chars=200
        )

        assert "... y" in result
        assert "más" in result


class TestFormatFindingLine:
    """Test _format_finding_line method."""

    def test_full_finding(self):
        """Test formatting finding with all fields."""
        finding = {
            "location": {"page": 5},
            "rule": "test_rule",
            "issue": "Test issue description",
        }

        result = ValidationContextFormatter._format_finding_line(finding)

        assert "Pág. 5" in result
        assert "Test issue description" in result
        assert "(test_rule)" in result

    def test_finding_without_page(self):
        """Test formatting finding without page."""
        finding = {
            "rule": "test_rule",
            "issue": "No page info",
        }

        result = ValidationContextFormatter._format_finding_line(finding)

        assert "Pág." not in result
        assert "No page info" in result
        assert "(test_rule)" in result

    def test_finding_without_rule(self):
        """Test formatting finding without rule."""
        finding = {
            "location": {"page": 3},
            "issue": "Issue only",
        }

        result = ValidationContextFormatter._format_finding_line(finding)

        assert "Pág. 3" in result
        assert "Issue only" in result
        assert "()" not in result

    def test_finding_only_issue(self):
        """Test formatting finding with only issue."""
        finding = {"issue": "Minimal finding"}

        result = ValidationContextFormatter._format_finding_line(finding)

        assert "Minimal finding" in result

    def test_truncates_long_issue(self):
        """Test long issues are truncated."""
        finding = {"issue": "x" * 100}

        result = ValidationContextFormatter._format_finding_line(finding)

        assert len(result) < 100
        assert "..." in result


class TestInjectValidationContextInPrompt:
    """Test inject_validation_context_in_prompt function."""

    def test_empty_findings_returns_original(self):
        """Test empty findings returns original prompt."""
        prompt = "Original prompt"

        result = inject_validation_context_in_prompt(prompt, [])

        assert result == prompt

    def test_appends_context_to_prompt(self):
        """Test context is appended to prompt."""
        prompt = "System prompt: Be helpful"
        findings = [{"severity": "high", "issue": "Test issue"}]

        result = inject_validation_context_in_prompt(prompt, findings)

        assert result.startswith(prompt)
        assert "VALIDATION_CONTEXT" in result
        assert "Test issue" in result

    def test_with_summary(self):
        """Test injection with summary."""
        prompt = "Base prompt"
        findings = [{"severity": "critical", "issue": "Critical!"}]
        summary = {"critical": 1}

        result = inject_validation_context_in_prompt(prompt, findings, summary)

        assert "1 críticos" in result


class TestIntegration:
    """Integration tests for complete formatting scenarios."""

    def test_realistic_validation_report(self):
        """Test formatting a realistic validation report."""
        findings = [
            {
                "severity": "critical",
                "location": {"page": 5},
                "rule": "disclaimer_coverage",
                "issue": "Disclaimer ausente en portada",
            },
            {
                "severity": "critical",
                "location": {"page": 12},
                "rule": "logo_missing",
                "issue": "Logo corporativo no detectado",
            },
            {
                "severity": "high",
                "location": {"page": 3},
                "rule": "font_violation",
                "issue": "Fuente no autorizada: Comic Sans",
            },
            {
                "severity": "high",
                "location": {"page": 7},
                "rule": "color_palette",
                "issue": "Color #FF0000 no está en paleta corporativa",
            },
            {
                "severity": "medium",
                "location": {"page": 15},
                "rule": "number_format",
                "issue": "Formato de número: '1,234.56' debería ser '1.234,56'",
            },
        ]
        summary = {"critical": 2, "high": 2, "medium": 1}

        result = ValidationContextFormatter.format_validation_context(
            findings, summary
        )

        # Check structure
        assert "VALIDATION_CONTEXT" in result
        assert "2 críticos" in result
        assert "2 altos" in result
        assert "1 medios" in result

        # Check sections appear in order
        assert result.index("CRÍTICOS") < result.index("ALTOS")
        assert result.index("ALTOS") < result.index("MEDIOS")

        # Check findings are included
        assert "Disclaimer ausente" in result
        assert "Logo corporativo" in result
        assert "Comic Sans" in result
