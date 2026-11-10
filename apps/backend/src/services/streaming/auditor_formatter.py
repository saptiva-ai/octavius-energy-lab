"""
Auditor Result Formatter Service.

Extracted from streaming_handler.py for better testability.
Handles transformation of raw MCP auditor validation findings into
user-friendly markdown formats with proper categorization and severity grouping.

REFACTOR-001: Phase 1 extraction.
"""

from __future__ import annotations

import re
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


# Pattern to detect auditor analysis sentences
AUDITOR_ANALYSIS_PATTERN = re.compile(
    r"^(el auditor|la auditoría|auditor)", re.IGNORECASE
)

# Canonical ordering for auditor display
AUDITOR_ORDER = [
    "compliance",
    "format",
    "typography",
    "grammar",
    "logo",
    "color_palette",
    "entity_consistency",
    "semantic_consistency",
]

# Display names for auditors (Spanish)
AUDITOR_DISPLAY_NAMES = {
    "compliance": "Cumplimiento",
    "format": "Formato",
    "typography": "Tipografía",
    "grammar": "Lingüístico",
    "logo": "Identidad visual",
    "color_palette": "Paleta de colores",
    "entity_consistency": "Consistencia de entidades",
    "semantic_consistency": "Consistencia semántica",
    "other": "Otros",
}

# Human-readable names for auditors
AUDITOR_HUMANIZE_NAMES = {
    "compliance": "Disclaimer Auditor",
    "format": "Format Auditor",
    "typography": "Typography Auditor",
    "grammar": "Grammar Auditor",
    "logo": "Logo Auditor",
    "color_palette": "Color Palette Auditor",
    "entity_consistency": "Entity Consistency Auditor",
    "semantic_consistency": "Semantic Consistency Auditor",
    "other": "General Auditor",
}

# Severity display labels (Spanish)
SEVERITY_DISPLAY = {
    "critical": "críticos",
    "high": "altos",
    "medium": "medios",
    "low": "bajos",
}


class AuditorResultFormatterService:
    """
    Service for formatting audit validation results into user-friendly formats.

    Responsibilities:
        - Normalize auditor category names
        - Aggregate findings by auditor type
        - Build markdown breakdown for display
        - Generate human-readable severity summaries
    """

    @staticmethod
    def format_auditor_markdown(text: str) -> str:
        """
        Ensure auditor analysis sentences render as markdown sub-lists.

        Args:
            text: Raw text that may contain auditor analysis

        Returns:
            Formatted text with proper markdown sub-list formatting
        """
        if not text:
            return text

        formatted_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                formatted_lines.append("")
                continue

            if AUDITOR_ANALYSIS_PATTERN.match(stripped) and not stripped.startswith(
                "-"
            ):
                formatted_lines.append(f"   - {stripped}")
            else:
                formatted_lines.append(line)

        return "\n".join(formatted_lines)

    @staticmethod
    def normalize_auditor_key(category: str) -> str:
        """
        Normalize auditor category names to canonical keys.

        Handles various Spanish/English naming conventions.

        Args:
            category: Raw category name from audit findings

        Returns:
            Canonical category key
        """
        value = (category or "").lower()
        if not value:
            return "other"

        if value in {"compliance", "cumplimiento"} or "disclaimer" in value:
            return "compliance"
        if (
            value in {"format", "formato"}
            or "layout" in value
            or "margen" in value
            or "tabla" in value
        ):
            return "format"
        if (
            value in {"typography", "tipografia", "tipografía"}
            or "font" in value
            or "tipograf" in value
        ):
            return "typography"
        if (
            value in {"grammar", "gramatica", "gramática"}
            or "linguistic" in value
            or "ortograf" in value
        ):
            return "grammar"
        if value in {"logo", "identidad"} or "visual" in value:
            return "logo"
        if value in {"color_palette", "color"} or "paleta" in value:
            return "color_palette"
        if value in {"entity_consistency"} or "entidad" in value or "entity" in value:
            return "entity_consistency"
        if (
            value in {"semantic_consistency"}
            or "semant" in value
            or "coherencia" in value
        ):
            return "semantic_consistency"

        return "other"

    @staticmethod
    def aggregate_auditors(validation_event: dict) -> dict:
        """
        Aggregate validation findings by auditor type.

        Args:
            validation_event: The validation_complete event dict

        Returns:
            Dict mapping auditor key to aggregated findings data
        """
        summary = validation_event.get("summary") or {}
        by_auditor = summary.get("by_auditor")
        if isinstance(by_auditor, dict) and by_auditor:
            normalized = {str(k).lower(): v for k, v in by_auditor.items()}
            return normalized

        findings = validation_event.get("findings") or []
        auditors: dict[str, dict] = {}

        for finding in findings:
            key = AuditorResultFormatterService.normalize_auditor_key(
                finding.get("category", "")
            )
            entry = auditors.setdefault(
                key,
                {
                    "total": 0,
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "findings": [],
                },
            )
            entry["total"] += 1
            severity = str(finding.get("severity", "low")).lower()
            if severity in {"critical", "high", "medium", "low"}:
                entry[severity] += 1
            entry["findings"].append(finding)

        # Generate summary for each auditor
        for key, data in auditors.items():
            summary_text = AuditorResultFormatterService.humanize_auditor_result(
                AUDITOR_HUMANIZE_NAMES.get(key, "General Auditor"),
                len(data.get("findings", [])),
                data.get("findings", []),
            )
            data["summary"] = summary_text

        return auditors

    @staticmethod
    def build_breakdown_markdown(validation_event: dict) -> Optional[str]:
        """
        Build markdown breakdown of validation results by auditor.

        Args:
            validation_event: The validation_complete event dict

        Returns:
            Markdown string with auditor breakdown, or None if no findings
        """
        auditors = AuditorResultFormatterService.aggregate_auditors(validation_event)
        if not auditors:
            return None

        lines: list[str] = []
        handled = set()

        def append_line(key: str) -> None:
            data = auditors.get(key)
            if not data:
                return
            handled.add(key)
            label = AUDITOR_DISPLAY_NAMES.get(key, key.replace("_", " ").title())
            summary_text = data.get("summary")

            if not summary_text:
                severity_parts = []
                for severity, label_text in SEVERITY_DISPLAY.items():
                    count = data.get(severity, 0)
                    if count:
                        plural = "hallazgo" if count == 1 else "hallazgos"
                        severity_parts.append(f"{count} {plural} {label_text}")

                if severity_parts:
                    summary_text = ", ".join(severity_parts)
                else:
                    total = data.get("total", 0)
                    summary_text = (
                        "Sin hallazgos reportados"
                        if total == 0
                        else f"{total} hallazgos registrados"
                    )

            lines.append(f"- **{label}:** {summary_text.strip()}")

        # Add auditors in canonical order
        for key in AUDITOR_ORDER:
            append_line(key)

        # Add any remaining auditors not in canonical order
        for key in auditors.keys():
            if key not in handled:
                append_line(key)

        if not lines:
            return None

        return "### Análisis por auditor\n" + "\n".join(lines)

    @staticmethod
    def humanize_auditor_result(
        auditor_name: str, findings_count: int, findings: list
    ) -> str:
        """
        Generate human-readable interpretation of auditor results.

        Args:
            auditor_name: Name of the auditor (e.g., "Grammar Auditor")
            findings_count: Number of findings
            findings: List of finding dictionaries with 'severity' key

        Returns:
            Human-readable summary string with emoji and interpretation
        """
        if findings_count == 0:
            no_issues_messages = {
                "Grammar Auditor": "No se detectaron errores ortográficos ni gramaticales. El texto está impecable.",
                "Format Auditor": "El formato del documento cumple perfectamente con los estándares.",
                "Logo Auditor": "Los logos están correctamente posicionados y con la calidad esperada.",
                "Color Palette Auditor": "La paleta de colores está bien aplicada en todo el documento.",
                "Disclaimer Auditor": "Todos los disclaimers requeridos están presentes y correctos.",
                "Typography Auditor": "La tipografía cumple con las especificaciones del manual de marca.",
                "Entity Consistency Auditor": "Las entidades están nombradas de forma consistente en todo el documento.",
                "Semantic Consistency Auditor": "El contenido mantiene coherencia semántica en todas las secciones.",
            }
            return no_issues_messages.get(
                auditor_name, f"No se encontraron problemas en {auditor_name}."
            )

        # Count by severity
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for finding in findings:
            severity = finding.get("severity", "low").lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        # Build interpretation based on severity distribution
        critical = severity_counts["critical"]
        high = severity_counts["high"]
        medium = severity_counts["medium"]
        low = severity_counts["low"]

        if critical > 0:
            level = "🔴 Crítico"
            interpretation = f"Se encontraron {critical} {'problema' if critical == 1 else 'problemas'} {'crítico' if critical == 1 else 'críticos'} que requieren atención inmediata"
        elif high > 0:
            level = "🟠 Alto"
            interpretation = f"Hay {high} {'hallazgo' if high == 1 else 'hallazgos'} de prioridad alta que deben corregirse"
        elif medium > 0:
            level = "🟡 Medio"
            interpretation = f"Se detectaron {medium} {'aspecto' if medium == 1 else 'aspectos'} a mejorar de prioridad media"
        else:
            level = "🟢 Bajo"
            interpretation = (
                f"Solo {low} {'detalle' if low == 1 else 'detalles'} menores detectados"
            )

        return f"{level} - {interpretation}"
