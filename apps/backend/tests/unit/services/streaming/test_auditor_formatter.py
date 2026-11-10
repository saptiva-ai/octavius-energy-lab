"""
Unit tests for AuditorResultFormatterService.

Tests cover:
- Markdown formatting for auditor analysis
- Auditor key normalization
- Findings aggregation by auditor type
- Breakdown markdown generation
- Human-readable result interpretation
"""

import pytest
from src.services.streaming.auditor_formatter import (
    AuditorResultFormatterService,
    AUDITOR_ANALYSIS_PATTERN,
    AUDITOR_ORDER,
    AUDITOR_DISPLAY_NAMES,
    AUDITOR_HUMANIZE_NAMES,
    SEVERITY_DISPLAY,
)


@pytest.mark.unit
class TestFormatAuditorMarkdown:
    """Tests for format_auditor_markdown method."""

    def test_empty_text(self):
        """Should handle empty text."""
        result = AuditorResultFormatterService.format_auditor_markdown("")
        assert result == ""

    def test_none_text(self):
        """Should handle None text."""
        result = AuditorResultFormatterService.format_auditor_markdown(None)
        assert result is None

    def test_text_without_auditor_pattern(self):
        """Should return unchanged text without auditor patterns."""
        text = "This is regular text\nWith multiple lines"
        result = AuditorResultFormatterService.format_auditor_markdown(text)
        assert result == text

    def test_text_with_auditor_prefix_el_auditor(self):
        """Should format 'el auditor' as sub-list."""
        text = "el auditor encontró problemas"
        result = AuditorResultFormatterService.format_auditor_markdown(text)
        assert result == "   - el auditor encontró problemas"

    def test_text_with_auditor_prefix_la_auditoria(self):
        """Should format 'la auditoría' as sub-list."""
        text = "la auditoría reveló deficiencias"
        result = AuditorResultFormatterService.format_auditor_markdown(text)
        assert result == "   - la auditoría reveló deficiencias"

    def test_text_with_auditor_prefix_auditor(self):
        """Should format 'auditor' as sub-list."""
        text = "Auditor de gramática encontró errores"
        result = AuditorResultFormatterService.format_auditor_markdown(text)
        assert result == "   - Auditor de gramática encontró errores"

    def test_already_formatted_line(self):
        """Should not double-format lines starting with dash."""
        text = "- el auditor ya formateado"
        result = AuditorResultFormatterService.format_auditor_markdown(text)
        assert result == "- el auditor ya formateado"

    def test_multiline_mixed_content(self):
        """Should format only auditor lines in mixed content."""
        text = """Header line
el auditor de formato detectó márgenes incorrectos
Regular paragraph
la auditoría de gramática no encontró errores"""

        result = AuditorResultFormatterService.format_auditor_markdown(text)

        lines = result.split("\n")
        assert lines[0] == "Header line"
        assert lines[1] == "   - el auditor de formato detectó márgenes incorrectos"
        assert lines[2] == "Regular paragraph"
        assert lines[3] == "   - la auditoría de gramática no encontró errores"

    def test_preserves_empty_lines(self):
        """Should preserve empty lines in output."""
        text = "Line 1\n\nLine 3"
        result = AuditorResultFormatterService.format_auditor_markdown(text)
        assert result == "Line 1\n\nLine 3"


@pytest.mark.unit
class TestNormalizeAuditorKey:
    """Tests for normalize_auditor_key method."""

    def test_empty_category(self):
        """Should return 'other' for empty category."""
        assert AuditorResultFormatterService.normalize_auditor_key("") == "other"
        assert AuditorResultFormatterService.normalize_auditor_key(None) == "other"

    def test_compliance_variations(self):
        """Should normalize compliance variations."""
        assert AuditorResultFormatterService.normalize_auditor_key("compliance") == "compliance"
        assert AuditorResultFormatterService.normalize_auditor_key("Compliance") == "compliance"
        assert AuditorResultFormatterService.normalize_auditor_key("cumplimiento") == "compliance"
        assert AuditorResultFormatterService.normalize_auditor_key("disclaimer_check") == "compliance"

    def test_format_variations(self):
        """Should normalize format variations."""
        assert AuditorResultFormatterService.normalize_auditor_key("format") == "format"
        assert AuditorResultFormatterService.normalize_auditor_key("formato") == "format"
        assert AuditorResultFormatterService.normalize_auditor_key("layout_check") == "format"
        assert AuditorResultFormatterService.normalize_auditor_key("margen_validator") == "format"
        assert AuditorResultFormatterService.normalize_auditor_key("tabla_format") == "format"

    def test_typography_variations(self):
        """Should normalize typography variations."""
        assert AuditorResultFormatterService.normalize_auditor_key("typography") == "typography"
        assert AuditorResultFormatterService.normalize_auditor_key("tipografia") == "typography"
        assert AuditorResultFormatterService.normalize_auditor_key("tipografía") == "typography"
        assert AuditorResultFormatterService.normalize_auditor_key("font_check") == "typography"

    def test_grammar_variations(self):
        """Should normalize grammar variations."""
        assert AuditorResultFormatterService.normalize_auditor_key("grammar") == "grammar"
        assert AuditorResultFormatterService.normalize_auditor_key("gramatica") == "grammar"
        assert AuditorResultFormatterService.normalize_auditor_key("gramática") == "grammar"
        assert AuditorResultFormatterService.normalize_auditor_key("linguistic") == "grammar"
        assert AuditorResultFormatterService.normalize_auditor_key("ortografia") == "grammar"

    def test_logo_variations(self):
        """Should normalize logo variations."""
        assert AuditorResultFormatterService.normalize_auditor_key("logo") == "logo"
        assert AuditorResultFormatterService.normalize_auditor_key("identidad") == "logo"
        assert AuditorResultFormatterService.normalize_auditor_key("visual_check") == "logo"

    def test_color_palette_variations(self):
        """Should normalize color palette variations."""
        assert AuditorResultFormatterService.normalize_auditor_key("color_palette") == "color_palette"
        assert AuditorResultFormatterService.normalize_auditor_key("color") == "color_palette"
        assert AuditorResultFormatterService.normalize_auditor_key("paleta_check") == "color_palette"

    def test_entity_consistency_variations(self):
        """Should normalize entity consistency variations."""
        assert AuditorResultFormatterService.normalize_auditor_key("entity_consistency") == "entity_consistency"
        assert AuditorResultFormatterService.normalize_auditor_key("entidad_check") == "entity_consistency"
        assert AuditorResultFormatterService.normalize_auditor_key("entity_validator") == "entity_consistency"

    def test_semantic_consistency_variations(self):
        """Should normalize semantic consistency variations."""
        assert AuditorResultFormatterService.normalize_auditor_key("semantic_consistency") == "semantic_consistency"
        assert AuditorResultFormatterService.normalize_auditor_key("semantica") == "semantic_consistency"
        assert AuditorResultFormatterService.normalize_auditor_key("coherencia") == "semantic_consistency"

    def test_unknown_category(self):
        """Should return 'other' for unknown categories."""
        assert AuditorResultFormatterService.normalize_auditor_key("random") == "other"
        assert AuditorResultFormatterService.normalize_auditor_key("xyz_check") == "other"


@pytest.mark.unit
class TestAggregateAuditors:
    """Tests for aggregate_auditors method."""

    def test_empty_validation_event(self):
        """Should return empty dict for empty event."""
        result = AuditorResultFormatterService.aggregate_auditors({})
        assert result == {}

    def test_with_by_auditor_summary(self):
        """Should use pre-aggregated by_auditor if available."""
        validation_event = {
            "summary": {
                "by_auditor": {
                    "Grammar": {"total": 5, "high": 2, "medium": 3},
                    "Format": {"total": 3, "low": 3},
                }
            }
        }

        result = AuditorResultFormatterService.aggregate_auditors(validation_event)

        assert "grammar" in result
        assert "format" in result

    def test_aggregates_findings_by_category(self):
        """Should aggregate findings by normalized category."""
        validation_event = {
            "findings": [
                {"category": "grammar", "severity": "high", "message": "Error 1"},
                {"category": "Grammar", "severity": "medium", "message": "Error 2"},
                {"category": "format", "severity": "low", "message": "Error 3"},
            ]
        }

        result = AuditorResultFormatterService.aggregate_auditors(validation_event)

        assert result["grammar"]["total"] == 2
        assert result["grammar"]["high"] == 1
        assert result["grammar"]["medium"] == 1
        assert result["format"]["total"] == 1
        assert result["format"]["low"] == 1

    def test_counts_severity_levels(self):
        """Should count all severity levels correctly."""
        validation_event = {
            "findings": [
                {"category": "compliance", "severity": "critical"},
                {"category": "compliance", "severity": "high"},
                {"category": "compliance", "severity": "medium"},
                {"category": "compliance", "severity": "low"},
                {"category": "compliance", "severity": "low"},
            ]
        }

        result = AuditorResultFormatterService.aggregate_auditors(validation_event)

        assert result["compliance"]["total"] == 5
        assert result["compliance"]["critical"] == 1
        assert result["compliance"]["high"] == 1
        assert result["compliance"]["medium"] == 1
        assert result["compliance"]["low"] == 2

    def test_handles_invalid_severity(self):
        """Should handle invalid severity gracefully."""
        validation_event = {
            "findings": [
                {"category": "grammar", "severity": "unknown"},
                {"category": "grammar", "severity": ""},
            ]
        }

        result = AuditorResultFormatterService.aggregate_auditors(validation_event)

        assert result["grammar"]["total"] == 2
        # Invalid severities should not increment any counter

    def test_stores_findings_list(self):
        """Should store findings list in aggregation."""
        finding1 = {"category": "logo", "severity": "high", "message": "Logo error"}
        finding2 = {"category": "logo", "severity": "low", "message": "Logo warning"}

        validation_event = {"findings": [finding1, finding2]}

        result = AuditorResultFormatterService.aggregate_auditors(validation_event)

        assert len(result["logo"]["findings"]) == 2
        assert finding1 in result["logo"]["findings"]
        assert finding2 in result["logo"]["findings"]

    def test_generates_summary_text(self):
        """Should generate summary text for each auditor."""
        validation_event = {
            "findings": [
                {"category": "grammar", "severity": "high", "message": "Error"},
            ]
        }

        result = AuditorResultFormatterService.aggregate_auditors(validation_event)

        assert "summary" in result["grammar"]
        assert isinstance(result["grammar"]["summary"], str)


@pytest.mark.unit
class TestBuildBreakdownMarkdown:
    """Tests for build_breakdown_markdown method."""

    def test_empty_validation_event(self):
        """Should return None for empty event."""
        result = AuditorResultFormatterService.build_breakdown_markdown({})
        assert result is None

    def test_no_findings(self):
        """Should return None when no findings."""
        validation_event = {"findings": []}
        result = AuditorResultFormatterService.build_breakdown_markdown(validation_event)
        assert result is None

    def test_builds_markdown_header(self):
        """Should include section header."""
        validation_event = {
            "findings": [{"category": "grammar", "severity": "low"}]
        }

        result = AuditorResultFormatterService.build_breakdown_markdown(validation_event)

        assert "### Análisis por auditor" in result

    def test_uses_display_names(self):
        """Should use Spanish display names."""
        validation_event = {
            "findings": [
                {"category": "compliance", "severity": "low"},
                {"category": "grammar", "severity": "low"},
            ]
        }

        result = AuditorResultFormatterService.build_breakdown_markdown(validation_event)

        assert "Cumplimiento" in result
        assert "Lingüístico" in result

    def test_respects_canonical_order(self):
        """Should display auditors in canonical order."""
        validation_event = {
            "findings": [
                {"category": "grammar", "severity": "low"},
                {"category": "compliance", "severity": "low"},
                {"category": "format", "severity": "low"},
            ]
        }

        result = AuditorResultFormatterService.build_breakdown_markdown(validation_event)

        # Compliance should appear before Format, and Format before Grammar
        compliance_pos = result.find("Cumplimiento")
        format_pos = result.find("Formato")
        grammar_pos = result.find("Lingüístico")

        assert compliance_pos < format_pos < grammar_pos

    def test_includes_severity_counts(self):
        """Should include severity counts in breakdown."""
        validation_event = {
            "findings": [
                {"category": "grammar", "severity": "critical"},
                {"category": "grammar", "severity": "high"},
            ]
        }

        result = AuditorResultFormatterService.build_breakdown_markdown(validation_event)

        # Should mention findings with severity
        assert "Lingüístico" in result

    def test_handles_auditors_not_in_order(self):
        """Should include auditors not in canonical order."""
        validation_event = {
            "findings": [
                {"category": "unknown_auditor", "severity": "low"},
            ]
        }

        result = AuditorResultFormatterService.build_breakdown_markdown(validation_event)

        # Should still include the unknown auditor
        assert result is not None
        assert "**" in result  # Bold formatting

    def test_fallback_severity_parts_when_no_summary(self):
        """Should build severity parts when no pre-generated summary (lines 246-254)."""
        # Use by_auditor format which doesn't have summary field
        validation_event = {
            "summary": {
                "by_auditor": {
                    "grammar": {
                        "total": 3,
                        "critical": 1,
                        "high": 2,
                        "medium": 0,
                        "low": 0,
                    }
                }
            }
        }

        result = AuditorResultFormatterService.build_breakdown_markdown(validation_event)

        # Should have generated the severity parts
        assert result is not None
        assert "Lingüístico" in result
        # Should mention critical and high findings
        assert "críticos" in result or "altos" in result or "hallazgo" in result

    def test_fallback_no_severity_counts_zero_total(self):
        """Should show 'Sin hallazgos' when no severity counts and total is 0 (lines 255-259)."""
        validation_event = {
            "summary": {
                "by_auditor": {
                    "compliance": {
                        "total": 0,
                        "critical": 0,
                        "high": 0,
                        "medium": 0,
                        "low": 0,
                    }
                }
            }
        }

        result = AuditorResultFormatterService.build_breakdown_markdown(validation_event)

        assert result is not None
        assert "Cumplimiento" in result
        assert "Sin hallazgos reportados" in result

    def test_fallback_no_severity_counts_nonzero_total(self):
        """Should show 'N hallazgos registrados' when total > 0 but no severity (lines 260-261)."""
        validation_event = {
            "summary": {
                "by_auditor": {
                    "format": {
                        "total": 5,
                        # No severity counts defined
                    }
                }
            }
        }

        result = AuditorResultFormatterService.build_breakdown_markdown(validation_event)

        assert result is not None
        assert "Formato" in result
        assert "5 hallazgos registrados" in result

    def test_singular_plural_in_severity_parts(self):
        """Should use correct singular/plural in severity parts (line 250)."""
        validation_event = {
            "summary": {
                "by_auditor": {
                    "typography": {
                        "total": 1,
                        "critical": 0,
                        "high": 1,
                        "medium": 0,
                        "low": 0,
                    }
                }
            }
        }

        result = AuditorResultFormatterService.build_breakdown_markdown(validation_event)

        assert result is not None
        # Should use singular "hallazgo" for count of 1
        assert "1 hallazgo" in result

    def test_returns_none_when_all_auditors_have_no_data(self):
        """Should return None when auditors exist but all have falsy data (line 275)."""
        validation_event = {
            "summary": {
                "by_auditor": {
                    "grammar": None,
                    "format": {},
                    "compliance": False,
                }
            }
        }

        result = AuditorResultFormatterService.build_breakdown_markdown(validation_event)

        # When all auditor data is falsy, no lines are added
        assert result is None


@pytest.mark.unit
class TestHumanizeAuditorResult:
    """Tests for humanize_auditor_result method."""

    def test_zero_findings_grammar(self):
        """Should return success message for Grammar Auditor."""
        result = AuditorResultFormatterService.humanize_auditor_result(
            "Grammar Auditor", 0, []
        )
        assert "impecable" in result or "errores" not in result.lower()

    def test_zero_findings_format(self):
        """Should return success message for Format Auditor."""
        result = AuditorResultFormatterService.humanize_auditor_result(
            "Format Auditor", 0, []
        )
        assert "cumple" in result.lower() or "perfectamente" in result.lower()

    def test_zero_findings_unknown_auditor(self):
        """Should return generic success for unknown auditor."""
        result = AuditorResultFormatterService.humanize_auditor_result(
            "Unknown Auditor", 0, []
        )
        assert "No se encontraron problemas" in result

    def test_critical_findings(self):
        """Should show critical level for critical findings."""
        findings = [
            {"severity": "critical", "message": "Critical issue"},
            {"severity": "low", "message": "Minor issue"},
        ]
        result = AuditorResultFormatterService.humanize_auditor_result(
            "Grammar Auditor", 2, findings
        )

        assert "🔴" in result
        assert "Crítico" in result
        assert "atención inmediata" in result

    def test_high_findings_without_critical(self):
        """Should show high level when no critical but has high."""
        findings = [
            {"severity": "high", "message": "High issue"},
            {"severity": "medium", "message": "Medium issue"},
        ]
        result = AuditorResultFormatterService.humanize_auditor_result(
            "Grammar Auditor", 2, findings
        )

        assert "🟠" in result
        assert "Alto" in result
        assert "prioridad alta" in result

    def test_medium_findings_without_higher(self):
        """Should show medium level when no high or critical."""
        findings = [
            {"severity": "medium", "message": "Medium issue"},
            {"severity": "low", "message": "Low issue"},
        ]
        result = AuditorResultFormatterService.humanize_auditor_result(
            "Grammar Auditor", 2, findings
        )

        assert "🟡" in result
        assert "Medio" in result
        assert "mejorar" in result

    def test_low_findings_only(self):
        """Should show low level for only low findings."""
        findings = [
            {"severity": "low", "message": "Low issue 1"},
            {"severity": "low", "message": "Low issue 2"},
        ]
        result = AuditorResultFormatterService.humanize_auditor_result(
            "Grammar Auditor", 2, findings
        )

        assert "🟢" in result
        assert "Bajo" in result
        assert "menores" in result

    def test_singular_plural_critical(self):
        """Should use correct singular/plural for critical."""
        one_critical = [{"severity": "critical", "message": "Issue"}]
        result_one = AuditorResultFormatterService.humanize_auditor_result(
            "Grammar Auditor", 1, one_critical
        )
        assert "problema" in result_one and "problemas" not in result_one.replace("problema", "")

        two_critical = [
            {"severity": "critical", "message": "Issue 1"},
            {"severity": "critical", "message": "Issue 2"},
        ]
        result_two = AuditorResultFormatterService.humanize_auditor_result(
            "Grammar Auditor", 2, two_critical
        )
        assert "problemas" in result_two

    def test_handles_invalid_severity(self):
        """Should handle findings with invalid severity."""
        findings = [
            {"severity": "invalid", "message": "Unknown severity"},
        ]
        # Should not raise, treated as default (low)
        result = AuditorResultFormatterService.humanize_auditor_result(
            "Grammar Auditor", 1, findings
        )
        assert result is not None


@pytest.mark.unit
class TestAuditorPatternRegex:
    """Tests for AUDITOR_ANALYSIS_PATTERN regex."""

    def test_matches_el_auditor(self):
        """Should match 'el auditor' at line start."""
        assert AUDITOR_ANALYSIS_PATTERN.match("el auditor detectó")
        assert AUDITOR_ANALYSIS_PATTERN.match("El Auditor encontró")

    def test_matches_la_auditoria(self):
        """Should match 'la auditoría' at line start."""
        assert AUDITOR_ANALYSIS_PATTERN.match("la auditoría reveló")
        assert AUDITOR_ANALYSIS_PATTERN.match("La Auditoría indica")

    def test_matches_auditor(self):
        """Should match 'auditor' at line start."""
        assert AUDITOR_ANALYSIS_PATTERN.match("auditor de gramática")
        assert AUDITOR_ANALYSIS_PATTERN.match("Auditor verificó")

    def test_no_match_middle_of_line(self):
        """Should not match if pattern not at start."""
        assert not AUDITOR_ANALYSIS_PATTERN.match("Según el auditor")
        assert not AUDITOR_ANALYSIS_PATTERN.match("   el auditor")  # Leading spaces


@pytest.mark.unit
class TestConstants:
    """Tests for module constants."""

    def test_auditor_order_coverage(self):
        """AUDITOR_ORDER should cover main auditor types."""
        expected = {
            "compliance",
            "format",
            "typography",
            "grammar",
            "logo",
            "color_palette",
            "entity_consistency",
            "semantic_consistency",
        }
        assert set(AUDITOR_ORDER) == expected

    def test_display_names_coverage(self):
        """AUDITOR_DISPLAY_NAMES should cover all ordered auditors."""
        for auditor in AUDITOR_ORDER:
            assert auditor in AUDITOR_DISPLAY_NAMES

    def test_humanize_names_coverage(self):
        """AUDITOR_HUMANIZE_NAMES should cover all ordered auditors."""
        for auditor in AUDITOR_ORDER:
            assert auditor in AUDITOR_HUMANIZE_NAMES

    def test_severity_display_coverage(self):
        """SEVERITY_DISPLAY should cover all severity levels."""
        expected = {"critical", "high", "medium", "low"}
        assert set(SEVERITY_DISPLAY.keys()) == expected
