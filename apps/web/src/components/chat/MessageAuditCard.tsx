/**
 * MessageAuditCard Component
 *
 * Renders audit results inline in chat messages (P2.FE.2)
 *
 * Features:
 * - Compact summary with severity badges
 * - Top 5 findings preview
 * - Expandable to show all findings
 * - Actions: View full report, Re-audit
 *
 * Used when ChatMessage.validation_report_id is present
 */

"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import type { Finding, FindingSeverity } from "@/types/validation";
import type { AuditReportMessageMetadata } from "@/lib/contracts";

// ============================================================================
// Types
// ============================================================================
// El shape de la metadata vive en el contrato compartido (lib/contracts →
// AuditReportMessageMetadata); esta card normaliza defensivamente el resto.

interface MessageAuditCardProps {
  /** Contrato compartido (lib/contracts): la card normaliza internamente. */
  metadata: AuditReportMessageMetadata;
  className?: string;
  onReAudit?: () => void;
  onViewFull?: () => void;
}

// ============================================================================
// Severity Configuration
// ============================================================================

const severityConfig: Record<
  FindingSeverity,
  { bg: string; border: string; text: string; icon: string; label: string }
> = {
  critical: {
    bg: "bg-red-500/10",
    border: "border-red-500/50",
    text: "text-red-400",
    icon: "🔴",
    label: "Crítico",
  },
  high: {
    bg: "bg-orange-500/10",
    border: "border-orange-500/50",
    text: "text-orange-400",
    icon: "🟠",
    label: "Alto",
  },
  medium: {
    bg: "bg-yellow-500/10",
    border: "border-yellow-500/50",
    text: "text-yellow-400",
    icon: "🟡",
    label: "Medio",
  },
  low: {
    bg: "bg-blue-500/10",
    border: "border-blue-500/50",
    text: "text-blue-400",
    icon: "🔵",
    label: "Bajo",
  },
};

// ============================================================================
// Subcomponents
// ============================================================================

function SeverityBadge({
  severity,
  count,
}: {
  severity: FindingSeverity;
  count: number;
}) {
  if (count === 0) return null;

  const config = severityConfig[severity];

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium",
        config.bg,
        config.border,
        config.text,
        "border",
      )}
    >
      <span>{config.icon}</span>
      <span>
        {count} {config.label}
      </span>
    </div>
  );
}

function FindingItem({
  finding,
  compact = false,
}: {
  finding: Finding;
  compact?: boolean;
}) {
  const config = severityConfig[finding.severity];

  return (
    <div
      className={cn(
        "flex items-start gap-2 p-3 rounded-lg border",
        config.bg,
        config.border,
        "hover:bg-opacity-20 transition-colors",
      )}
    >
      <span className="text-base flex-shrink-0 mt-0.5">{config.icon}</span>
      <div className="flex-1 min-w-0">
        <p className={cn("text-sm font-medium", config.text)}>
          {finding.issue}
        </p>
        {!compact && finding.suggestion && (
          <p className="text-xs text-zinc-400 mt-1">💡 {finding.suggestion}</p>
        )}
        <p className="text-xs text-zinc-500 mt-1">
          {finding.location?.page && `📄 Página ${finding.location.page}`}
          {finding.rule && (
            <span className="ml-2 text-zinc-600">• {finding.rule}</span>
          )}
        </p>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function MessageAuditCard({
  metadata,
  className,
  onReAudit,
  onViewFull,
}: MessageAuditCardProps) {
  const [expanded, setExpanded] = useState(false);

  const safeMetadata: any = metadata ?? {};
  const rawSummary = safeMetadata.summary;
  const summary =
    rawSummary && typeof rawSummary === "object" ? rawSummary : null;

  const sampleFindings = Array.isArray(safeMetadata.sample_findings)
    ? safeMetadata.sample_findings
    : Array.isArray(safeMetadata.findings)
      ? safeMetadata.findings
      : [];

  const status = safeMetadata.status ?? "completed";
  const filename =
    safeMetadata.filename ?? safeMetadata.document_name ?? "Documento auditado";

  const findings_by_severity = (summary?.findings_by_severity as
    | Record<string, number>
    | undefined) ??
    safeMetadata.findings_by_severity ?? {
      critical: safeMetadata.critical_count ?? 0,
      high: safeMetadata.high_count ?? 0,
      medium: safeMetadata.medium_count ?? 0,
      low: safeMetadata.low_count ?? 0,
    };

  const total_findings =
    summary?.total_findings ??
    safeMetadata.total_findings ??
    safeMetadata.findings_count ??
    sampleFindings.length ??
    0;

  const policy_name =
    summary?.policy_name ??
    safeMetadata.policy_name ??
    safeMetadata.policy ??
    "No especificada";

  const disclaimerCoverage = summary?.disclaimer_coverage;
  const fontsUsed = summary?.fonts_used ?? [];
  const colorsDetected = summary?.colors_detected ?? [];
  const grammarIssues = summary?.grammar_issues ?? 0;
  const spellingIssues = summary?.spelling_issues ?? 0;
  const pagesWithGrammarIssues = summary?.pages_with_grammar_issues ?? [];
  const imageOverview = summary?.image_overview;

  // Handle error state
  if (status === "error") {
    return (
      <div
        className={cn(
          "p-4 rounded-lg border border-red-500/50 bg-red-500/10",
          className,
        )}
      >
        <div className="flex items-start gap-3">
          <span className="text-2xl">❌</span>
          <div>
            <h3 className="text-sm font-semibold text-red-400">
              Error en auditoría
            </h3>
            <p className="text-xs text-zinc-400 mt-1">
              {metadata.error_message || "No se pudo completar la auditoría"}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "rounded-lg border border-zinc-700/60 bg-zinc-800/40 overflow-hidden",
        className,
      )}
    >
      {/* Header */}
      <div className="p-4 border-b border-zinc-700/40">
        <div className="flex items-start gap-3">
          <span className="text-2xl flex-shrink-0">✅</span>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-zinc-100">
              Auditoría completada
            </h3>
            <p
              className="text-xs text-zinc-400 mt-0.5 truncate"
              title={filename}
            >
              {filename}
            </p>
            <p className="text-xs text-zinc-500 mt-1">
              Política: <span className="text-zinc-400">{policy_name}</span>
            </p>
          </div>
        </div>
      </div>

      {/* Summary */}
      <div className="p-4 space-y-3">
        {/* Total findings */}
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold text-zinc-100">
            {total_findings}
          </span>
          <span className="text-sm text-zinc-400">
            hallazgo{total_findings !== 1 ? "s" : ""} encontrado
            {total_findings !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Severity badges */}
        {total_findings > 0 && (
          <div className="flex flex-wrap gap-2">
            <SeverityBadge
              severity="critical"
              count={findings_by_severity.critical || 0}
            />
            <SeverityBadge
              severity="high"
              count={findings_by_severity.high || 0}
            />
            <SeverityBadge
              severity="medium"
              count={findings_by_severity.medium || 0}
            />
            <SeverityBadge
              severity="low"
              count={findings_by_severity.low || 0}
            />
          </div>
        )}

        {/* Compliance and quality metrics */}
        <div className="grid gap-2 text-xs text-zinc-400">
          {typeof disclaimerCoverage === "number" && (
            <div>
              📄 Cobertura de disclaimers:{" "}
              <span className="text-zinc-300">
                {(disclaimerCoverage * 100).toFixed(0)}%
              </span>
            </div>
          )}
          {(grammarIssues > 0 || spellingIssues > 0) && (
            <div>
              📝 Calidad de texto:{" "}
              <span className="text-zinc-300">
                {grammarIssues} gramática · {spellingIssues} ortografía
              </span>
              {pagesWithGrammarIssues.length > 0 && (
                <span className="ml-1 text-zinc-500">
                  (pág. {pagesWithGrammarIssues.slice(0, 6).join(", ")})
                </span>
              )}
            </div>
          )}
          {grammarIssues === 0 && spellingIssues === 0 && (
            <div>📝 Sin incidencias gramaticales detectadas.</div>
          )}
          {fontsUsed.length > 0 && (
            <div>
              🔤 Tipografías principales:{" "}
              <span className="text-zinc-300">
                {fontsUsed.slice(0, 3).join(", ")}
              </span>
            </div>
          )}
          {colorsDetected.length > 0 && (
            <div>
              🎨 Colores dominantes:{" "}
              <span className="text-zinc-300">
                {colorsDetected.slice(0, 5).join(", ")}
              </span>
            </div>
          )}
          {imageOverview?.total_images ? (
            <div>
              🖼️ Imágenes:{" "}
              <span className="text-zinc-300">
                {imageOverview.total_images} totales
              </span>
              {typeof imageOverview.largest_image_ratio === "number" && (
                <span className="ml-1 text-zinc-500">
                  (máx {Math.round(imageOverview.largest_image_ratio * 100)}%)
                </span>
              )}
            </div>
          ) : (
            summary &&
            imageOverview &&
            imageOverview.total_images === 0 && (
              <div>🖼️ No se detectaron imágenes en el documento.</div>
            )
          )}
        </div>

        {/* Findings preview */}
        {sampleFindings && sampleFindings.length > 0 && (
          <div className="space-y-2 mt-4">
            <p className="text-xs text-zinc-400 font-medium">
              {expanded ? "Todos los hallazgos:" : "Principales hallazgos:"}
            </p>
            <div className="space-y-2">
              {(expanded ? sampleFindings : sampleFindings.slice(0, 3)).map(
                (finding: any, idx: number) => (
                  <FindingItem
                    key={`${finding.id}-${idx}`}
                    finding={finding}
                    compact={!expanded}
                  />
                ),
              )}
            </div>

            {/* Expand/Collapse button */}
            {sampleFindings.length > 3 && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="text-xs text-blue-400 hover:text-blue-300 transition-colors mt-2"
              >
                {expanded
                  ? "Mostrar menos ▲"
                  : `Mostrar ${sampleFindings.length - 3} más ▼`}
              </button>
            )}
          </div>
        )}

        {/* No findings message */}
        {total_findings === 0 && (
          <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/50">
            <p className="text-sm text-green-400">
              🎉 ¡Excelente! No se encontraron problemas en este documento.
            </p>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="p-3 border-t border-zinc-700/40 bg-zinc-800/60">
        <div className="flex gap-2">
          {onViewFull && (
            <button
              onClick={onViewFull}
              className={cn(
                "flex-1 px-3 py-2 text-xs font-medium rounded-md",
                "bg-zinc-700/60 hover:bg-zinc-700 text-zinc-200",
                "transition-colors border border-zinc-600/40",
              )}
            >
              Ver reporte completo
            </button>
          )}
          {onReAudit && (
            <button
              onClick={onReAudit}
              className={cn(
                "px-3 py-2 text-xs font-medium rounded-md",
                "bg-blue-600/20 hover:bg-blue-600/30 text-blue-400",
                "transition-colors border border-blue-500/40",
              )}
            >
              🔄 Re-auditar
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Export
// ============================================================================

export default MessageAuditCard;
