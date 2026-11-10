/**
 * ValidationFindings Component
 *
 * Displays Copiloto Audit validation report with:
 * - Summary cards (total findings, disclaimer coverage, duration)
 * - Findings grouped by severity
 * - Individual finding cards with details
 * - Collapsible sections for better UX
 */

"use client";

import React, { useState } from "react";
import type {
  ValidationReportResponse,
  Finding,
  FindingSeverity,
  FindingCategory,
} from "@/types/validation";
import { cn } from "@/lib/utils";

// Severity badge colors
const severityConfig: Record<
  FindingSeverity,
  { bg: string; border: string; text: string; icon: string }
> = {
  critical: {
    bg: "bg-red-500/10",
    border: "border-red-500/50",
    text: "text-red-400",
    icon: "🔴",
  },
  high: {
    bg: "bg-orange-500/10",
    border: "border-orange-500/50",
    text: "text-orange-400",
    icon: "🟠",
  },
  medium: {
    bg: "bg-yellow-500/10",
    border: "border-yellow-500/50",
    text: "text-yellow-400",
    icon: "🟡",
  },
  low: {
    bg: "bg-blue-500/10",
    border: "border-blue-500/50",
    text: "text-blue-400",
    icon: "🔵",
  },
};

// Category icons
const categoryIcons: Record<FindingCategory, string> = {
  compliance: "📋",
  format: "🎨",
  logo: "🖼️",
  linguistic: "✍️",
};

const auditorDisplayNames: Record<string, string> = {
  compliance: "Cumplimiento legal",
  disclaimer: "Descargos",
  format: "Formato y estilo",
  typography: "Tipografía",
  grammar: "Gramática",
  logo: "Identidad visual",
  color_palette: "Paleta de colores",
  entity_consistency: "Consistencia de entidades",
  semantic_consistency: "Consistencia semántica",
};

interface ValidationFindingsProps {
  report: ValidationReportResponse;
  className?: string;
}

interface SummaryCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: string;
  className?: string;
}

function SummaryCard({
  title,
  value,
  subtitle,
  icon,
  className,
}: SummaryCardProps) {
  return (
    <div
      className={cn(
        "p-4 rounded-lg border border-zinc-700/60 bg-zinc-800/40",
        className,
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-xs text-zinc-400 mb-1">{title}</p>
          <p className="text-2xl font-semibold text-zinc-100">{value}</p>
          {subtitle && <p className="text-xs text-zinc-500 mt-1">{subtitle}</p>}
        </div>
        {icon && <span className="text-2xl">{icon}</span>}
      </div>
    </div>
  );
}

interface FindingCardProps {
  finding: Finding;
  className?: string;
}

function FindingCard({ finding, className }: FindingCardProps) {
  const [expanded, setExpanded] = useState(false);
  const config = severityConfig[finding.severity];

  return (
    <div
      className={cn(
        "p-4 rounded-lg border transition-colors",
        config.bg,
        config.border,
        "hover:border-opacity-70",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        <span className="text-xl flex-shrink-0">{config.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className={cn("text-xs font-medium uppercase", config.text)}>
              {finding.severity}
            </span>
            <span className="text-xs text-zinc-500">•</span>
            <span className="text-xs text-zinc-400">
              {categoryIcons[finding.category]} {finding.category}
            </span>
            {finding.location && (
              <>
                <span className="text-xs text-zinc-500">•</span>
                <span className="text-xs text-zinc-400">
                  Página {finding.location.page}
                </span>
              </>
            )}
          </div>

          <p className="text-sm text-zinc-200 mb-2">{finding.issue}</p>

          {finding.suggestion && (
            <p className="text-sm text-zinc-400 italic">
              💡 {finding.suggestion}
            </p>
          )}

          {/* Expandable details */}
          {(finding.location?.text_snippet || finding.evidence.length > 0) && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-3 text-xs text-zinc-400 hover:text-zinc-300 transition-colors flex items-center gap-1"
            >
              {expanded ? "▼" : "▶"} {expanded ? "Ocultar" : "Ver"} detalles
            </button>
          )}

          {expanded && (
            <div className="mt-3 space-y-2 pt-3 border-t border-zinc-700/40">
              {finding.location?.text_snippet && (
                <div className="text-xs">
                  <p className="text-zinc-500 mb-1">Texto detectado:</p>
                  <p className="text-zinc-300 bg-zinc-900/50 p-2 rounded font-mono">
                    &quot;{finding.location.text_snippet}&quot;
                  </p>
                </div>
              )}

              {finding.evidence.length > 0 && (
                <div className="text-xs">
                  <p className="text-zinc-500 mb-1">Evidencia:</p>
                  <div className="space-y-1">
                    {finding.evidence.map((ev, idx) => (
                      <div key={idx} className="bg-zinc-900/50 p-2 rounded">
                        <span className="text-zinc-400">{ev.kind}:</span>{" "}
                        <span className="text-zinc-300">
                          {JSON.stringify(ev.data, null, 2)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function ValidationFindings({
  report,
  className,
}: ValidationFindingsProps) {
  const { summary, findings } = report;

  // Calculate disclaimer coverage percentage
  const disclaimerCoverage = summary.disclaimer
    ? Math.round(summary.disclaimer.coverage * 100)
    : null;

  // Group findings by severity
  const findingsBySeverity: Record<FindingSeverity, Finding[]> = {
    critical: [],
    high: [],
    medium: [],
    low: [],
  };

  findings.forEach((finding) => {
    findingsBySeverity[finding.severity].push(finding);
  });

  const friendlyAuditors =
    summary.auditors_run
      ?.map((auditorKey) => {
        if (!auditorKey) return null;
        const normalized = auditorKey.toLowerCase();
        return (
          auditorDisplayNames[normalized] ||
          normalized
            .replace(/_/g, " ")
            .replace(/\b\w/g, (char) => char.toUpperCase())
        );
      })
      .filter((label): label is string => Boolean(label)) ?? [];

  return (
    <div
      className={cn(
        "space-y-4 p-5 bg-gradient-to-b from-zinc-900/60 to-zinc-900/40 rounded-xl border border-zinc-700/60",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-3 pb-4 border-b border-zinc-700/60">
        <span className="text-2xl">🔍</span>
        <div>
          <h3 className="text-lg font-semibold text-zinc-100">
            Reporte de Auditoría
          </h3>
          <p className="text-sm text-zinc-400">
            Copiloto Audit - Validación de documentos
          </p>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <SummaryCard
          title="Total de Hallazgos"
          value={summary.total_findings}
          subtitle={
            summary.total_findings === 0
              ? "✓ Sin problemas detectados"
              : `${summary.findings_by_severity.critical || 0} críticos, ${summary.findings_by_severity.high || 0} altos`
          }
          icon="📊"
        />

        {disclaimerCoverage !== null && (
          <SummaryCard
            title="Cobertura de Disclaimers"
            value={`${disclaimerCoverage}%`}
            subtitle={
              summary.disclaimer
                ? `${summary.disclaimer.pages_with_disclaimer}/${summary.disclaimer.total_pages} páginas`
                : undefined
            }
            icon="⚖️"
          />
        )}

        {summary.total_duration_ms && (
          <SummaryCard
            title="Tiempo de Procesamiento"
            value={`${(summary.total_duration_ms / 1000).toFixed(1)}s`}
            subtitle={
              friendlyAuditors.length > 0
                ? `Auditores: ${friendlyAuditors.join(", ")}`
                : undefined
            }
            icon="⏱️"
          />
        )}
      </div>

      {/* Findings Section */}
      {summary.total_findings > 0 ? (
        <div className="space-y-4">
          {/* Findings by Severity */}
          {(["critical", "high", "medium", "low"] as FindingSeverity[]).map(
            (severity) => {
              const severityFindings = findingsBySeverity[severity];
              if (severityFindings.length === 0) return null;

              const config = severityConfig[severity];

              return (
                <div key={severity} className="space-y-2">
                  <h4
                    className={cn(
                      "text-sm font-medium flex items-center gap-2",
                      config.text,
                    )}
                  >
                    {config.icon}
                    <span className="uppercase">
                      {severity} ({severityFindings.length})
                    </span>
                  </h4>
                  <div className="space-y-2">
                    {severityFindings.map((finding) => (
                      <FindingCard key={finding.id} finding={finding} />
                    ))}
                  </div>
                </div>
              );
            },
          )}
        </div>
      ) : (
        <div className="py-8 text-center">
          <span className="text-5xl mb-3 block">✅</span>
          <p className="text-lg font-medium text-zinc-200 mb-1">
            ¡Documento aprobado!
          </p>
          <p className="text-sm text-zinc-400">
            No se encontraron problemas de cumplimiento
          </p>
        </div>
      )}

      {/* Footer */}
      <div className="pt-4 border-t border-zinc-700/60 text-xs text-zinc-500">
        <p>
          Job ID: <code className="text-zinc-400">{report.job_id}</code>
        </p>
      </div>
    </div>
  );
}
