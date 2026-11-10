"""
Validation Context Formatter

Formats validation findings into a compact context for LLM injection in RAG.
Maximum 800 tokens to avoid bloating the prompt.

Used by RAGChatStrategy to enable context-aware follow-up questions like:
- "¿Qué páginas tienen problemas?"
- "¿Cuáles son las violaciones más graves?"
"""

from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

MAX_TOKENS = 800
CHARS_PER_TOKEN = 4  # Rough estimate for Spanish/English


class ValidationContextFormatter:
    """Formats validation findings for LLM context injection"""

    @staticmethod
    def format_validation_context(
        findings: List[Dict],
        summary: Optional[Dict] = None,
        max_tokens: int = MAX_TOKENS,
    ) -> str:
        """
        Format validation findings as compact context string.

        Args:
            findings: List of Finding objects with severity, page, rule, issue
            summary: Optional summary dict with counts by severity
            max_tokens: Maximum tokens to use (default 800)

        Returns:
            Formatted string ready for prompt injection

        Example Output:
            VALIDATION_CONTEXT:
            El documento tiene 3 hallazgos críticos y 5 altos en las páginas siguientes:

            CRÍTICOS (3):
            - Pág. 5: Disclaimer ausente (disclaimer_coverage)
            - Pág. 12: Logo Demo Capital no detectado (logo_missing)
            - Pág. 18: Formato de número incorrecto: "1,234.56" → "1.234,56"

            ALTOS (5):
            - Pág. 3: Fuente no autorizada "Comic Sans" (font_violation)
            - Pág. 7: Color #FF0000 no está en paleta corporativa
            ...
        """
        logger.debug(
            "Formatting validation context",
            finding_count=len(findings),
            max_tokens=max_tokens,
        )

        if not findings:
            return ""

        # Sort by severity (critical → high → medium → low)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_findings = sorted(
            findings, key=lambda f: severity_order.get(f.get("severity", "low"), 99)
        )

        # Build context sections
        sections = []

        # Header with summary
        header = ValidationContextFormatter._format_header(sorted_findings, summary)
        sections.append(header)

        # Group by severity
        by_severity = ValidationContextFormatter._group_by_severity(sorted_findings)

        # Format each severity group (prioritize critical/high)
        max_chars = max_tokens * CHARS_PER_TOKEN
        current_chars = len(header)

        for severity in ["critical", "high", "medium", "low"]:
            group_findings = by_severity.get(severity, [])
            if not group_findings:
                continue

            section = ValidationContextFormatter._format_severity_group(
                severity, group_findings, max_chars=(max_chars - current_chars)
            )

            if section:
                sections.append(section)
                current_chars += len(section)

            # Stop if we're running out of space
            if current_chars >= max_chars * 0.9:  # Leave 10% buffer
                break

        result = "\n\n".join(sections)

        logger.info(
            "Validation context formatted",
            result_length=len(result),
            estimated_tokens=len(result) // CHARS_PER_TOKEN,
            findings_included=len(sorted_findings),
        )

        return result

    @staticmethod
    def _format_header(findings: List[Dict], summary: Optional[Dict]) -> str:
        """Format context header with counts"""
        if summary:
            critical = summary.get("critical", 0)
            high = summary.get("high", 0)
            medium = summary.get("medium", 0)
            low = summary.get("low", 0)

            parts = []
            if critical:
                parts.append(f"{critical} críticos")
            if high:
                parts.append(f"{high} altos")
            if medium:
                parts.append(f"{medium} medios")
            if low:
                parts.append(f"{low} bajos")

            counts_str = ", ".join(parts) if parts else "hallazgos"

            return (
                f"VALIDATION_CONTEXT:\nEl documento tiene {counts_str} en validación:"
            )
        else:
            return (
                f"VALIDATION_CONTEXT:\n"
                f"El documento tiene {len(findings)} hallazgos en validación:"
            )

    @staticmethod
    def _group_by_severity(findings: List[Dict]) -> Dict[str, List[Dict]]:
        """Group findings by severity"""
        groups = {}
        for finding in findings:
            severity = finding.get("severity", "low")
            if severity not in groups:
                groups[severity] = []
            groups[severity].append(finding)
        return groups

    @staticmethod
    def _format_severity_group(
        severity: str, findings: List[Dict], max_chars: int
    ) -> str:
        """Format one severity group (e.g., CRÍTICOS)"""
        severity_labels = {
            "critical": "CRÍTICOS",
            "high": "ALTOS",
            "medium": "MEDIOS",
            "low": "BAJOS",
        }

        label = severity_labels.get(severity, severity.upper())
        header = f"{label} ({len(findings)}):"

        lines = [header]
        chars_used = len(header)

        for finding in findings:
            line = ValidationContextFormatter._format_finding_line(finding)

            # Check if we have space
            if chars_used + len(line) > max_chars:
                # Add truncation notice
                remaining = len(findings) - len(lines) + 1
                if remaining > 0:
                    lines.append(f"  ... y {remaining} más")
                break

            lines.append(line)
            chars_used += len(line)

        return "\n".join(lines)

    @staticmethod
    def _format_finding_line(finding: Dict) -> str:
        """Format single finding as compact line"""
        page = finding.get("location", {}).get("page")
        rule = finding.get("rule", "")
        issue = finding.get("issue", "")

        # Truncate issue if too long
        if len(issue) > 80:
            issue = issue[:77] + "..."

        # Format: "- Pág. X: Issue (rule)"
        if page:
            if rule:
                return f"  - Pág. {page}: {issue} ({rule})"
            else:
                return f"  - Pág. {page}: {issue}"
        else:
            # No page info
            if rule:
                return f"  - {issue} ({rule})"
            else:
                return f"  - {issue}"


def inject_validation_context_in_prompt(
    base_prompt: str, findings: List[Dict], summary: Optional[Dict] = None
) -> str:
    """
    Convenience function to inject validation context into existing prompt.

    Args:
        base_prompt: Original prompt (system or user)
        findings: Validation findings
        summary: Optional summary statistics

    Returns:
        Augmented prompt with validation context

    Example:
        >>> prompt = "Eres un asistente financiero..."
        >>> augmented = inject_validation_context_in_prompt(
        ...     prompt,
        ...     validation_report.findings,
        ...     validation_report.summary
        ... )
    """
    if not findings:
        return base_prompt

    context = ValidationContextFormatter.format_validation_context(findings, summary)

    # Append to end of prompt
    return f"{base_prompt}\n\n{context}"
