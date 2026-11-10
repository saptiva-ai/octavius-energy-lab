"""
Utility helpers to normalize audit findings into a presentation-agnostic payload.

These are presentation utilities only - audit logic is in un plugin privado de auditoría.
"""

from typing import Any, Dict, List, Optional

from ..schemas.audit import AuditFinding, AuditReportResponse, AuditStats

# Whitelist of technical terms to ignore for low-severity noise
TECHNICAL_WHITELIST = {
    "genai",
    "deployment",
    "stack",
    "on-prem",
    "on prem",
    "frida",
    "k8s",
    "billing",
    "endpoint",
    "audit",
}


def _should_filter_low_noise(message: str, severity: str) -> bool:
    """
    Return True if the finding should be filtered out as low-severity technical jargon.
    """
    if severity != "low":
        return False
    msg_lower = message.lower()
    return any(term in msg_lower for term in TECHNICAL_WHITELIST)


def build_audit_report_response(
    *,
    doc_name: str,
    findings: List[Dict[str, Any]],
    summary: Optional[Any] = None,
    actions: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditReportResponse:
    """
    Normalize raw findings into AuditReportResponse with filtering and grouping.
    """
    filtered: List[AuditFinding] = []
    for f in findings or []:
        severity = str(f.get("severity", "")).lower() or "low"
        message = f.get("message") or f.get("issue") or f.get("description") or ""

        if _should_filter_low_noise(message, severity):
            continue

        category = f.get("category") or "uncategorized"
        normalized = AuditFinding(
            id=f.get("id"),
            category=category,
            severity=severity,
            message=message,
            page=(
                (f.get("location") or {}).get("page")
                if isinstance(f.get("location"), dict)
                else f.get("page")
            ),
            suggestion=f.get("suggestion"),
            rule=f.get("rule"),
            raw=f or {},
        )
        filtered.append(normalized)

    # Stats
    stats_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    categories: Dict[str, List[AuditFinding]] = {}

    for finding in filtered:
        sev = finding.severity.lower()
        if sev not in stats_counts:
            sev = "low"
        stats_counts[sev] += 1
        categories.setdefault(finding.category, []).append(finding)

    total = sum(stats_counts.values())
    stats = AuditStats(
        critical=stats_counts["critical"],
        high=stats_counts["high"],
        medium=stats_counts["medium"],
        low=stats_counts["low"],
        total=total,
    )

    # Build response
    resp = AuditReportResponse(
        doc_name=doc_name,
        stats=stats,
        categories=categories,
        actions=actions or [],
        metadata=metadata or {},
    )

    # Preserve summary in metadata if provided
    if summary is not None:
        resp.metadata["summary"] = summary

    return resp


def _extract_summary_text(summary: Optional[Any]) -> Optional[str]:
    """
    Normalize summary payload (string or dict) into displayable text.
    """
    if summary is None:
        return None
    if isinstance(summary, str):
        return summary.strip()
    if isinstance(summary, dict):
        for key in ("text", "summary", "overview", "short"):
            if summary.get(key):
                return str(summary[key]).strip()
    return None


def summarize_audit_for_message(
    doc_name: str,
    artifact: AuditReportResponse,
    summary_raw: Optional[Any] = None,
    max_findings: int = 3,
) -> str:
    """
    Build a concise, human-readable summary for chat messages using audit results.
    """
    summary_text = _extract_summary_text(summary_raw) or _extract_summary_text(
        artifact.metadata.get("summary") if artifact.metadata else None
    )

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    severity_label = {
        "critical": "Crítico",
        "high": "Alto",
        "medium": "Medio",
        "low": "Bajo",
    }

    all_findings: List[AuditFinding] = []
    for findings in artifact.categories.values():
        all_findings.extend(findings)

    all_findings.sort(
        key=lambda f: (
            severity_order.get(str(f.severity).lower(), 99),
            (f.page or 0),
        )
    )
    top_findings = all_findings[:max_findings]

    lines: List[str] = [
        f"He revisado {doc_name} y encontré algunos puntos importantes que necesitan atención:",
    ]

    if summary_text:
        clipped = (
            summary_text if len(summary_text) <= 320 else summary_text[:317] + "..."
        )
        lines.append(f"- {clipped}")

    if top_findings:
        lines.append("Principales focos:")
        for finding in top_findings:
            sev = severity_label.get(str(finding.severity).lower(), "Info")
            msg = finding.message.strip()
            msg = msg if len(msg) <= 220 else msg[:217] + "..."
            lines.append(f"- [{sev}] {msg}")

    stats = artifact.stats
    lines.append(
        f"Resumen de hallazgos: {stats.critical} crítico, {stats.high} alto, {stats.medium} medio, {stats.low} bajo."
    )
    lines.append("¿Qué sigue?")
    lines.append(
        "👉 Revisa el reporte detallado en el panel lateral para ver exactamente qué ajustar."
    )
    lines.append("👉 Descarga el reporte con todas las ubicaciones y sugerencias.")

    return "\n".join(lines)
