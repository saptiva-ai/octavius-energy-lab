"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import type { ValidationReportResponse } from "@/types/validation";

interface AuditReportCardProps {
  report: ValidationReportResponse;
  className?: string;
}

type SeverityLevel = "high" | "medium" | "low";

const SEVERITY_CONFIG = {
  high: {
    label: "Alta",
    color: "red",
    bgClass: "bg-red-500/10",
    borderClass: "border-red-500/30",
    textClass: "text-red-400",
    badgeClass: "bg-red-500/20 text-red-300",
  },
  medium: {
    label: "Media",
    color: "yellow",
    bgClass: "bg-yellow-500/10",
    borderClass: "border-yellow-500/30",
    textClass: "text-yellow-400",
    badgeClass: "bg-yellow-500/20 text-yellow-300",
  },
  low: {
    label: "Baja",
    color: "blue",
    bgClass: "bg-blue-500/10",
    borderClass: "border-blue-500/30",
    textClass: "text-blue-400",
    badgeClass: "bg-blue-500/20 text-blue-300",
  },
} as const;

/**
 * AuditReportCard - Displays validation report with findings
 *
 * Features:
 * - Summary section with total findings and severity breakdown
 * - Expandable sections by auditor (compliance, format, grammar, logo)
 * - Color-coded severity badges
 * - Filterable findings
 * - Re-audit action
 *
 * Usage:
 * ```tsx
 * <AuditReportCard report={validationReport} />
 * ```
 */
export function AuditReportCard({ report, className }: AuditReportCardProps) {
  const [expandedSections, setExpandedSections] = React.useState<Set<string>>(
    new Set(["all"]), // Expand all by default
  );
  const [severityFilter, setSeverityFilter] = React.useState<
    SeverityLevel | "all"
  >("all");

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  };

  const { summary } = report;
  const totalFindings = summary.total_findings;

  // Get findings by severity
  const highFindings = summary.findings_by_severity?.high || 0;
  const mediumFindings = summary.findings_by_severity?.medium || 0;
  const lowFindings = summary.findings_by_severity?.low || 0;

  // Overall status
  const statusConfig = {
    passed: {
      icon: "✅",
      label: "Aprobado",
      bgClass: "bg-green-500/10",
      borderClass: "border-green-500/30",
      textClass: "text-green-400",
    },
    failed: {
      icon: "❌",
      label: "Fallido",
      bgClass: "bg-red-500/10",
      borderClass: "border-red-500/30",
      textClass: "text-red-400",
    },
    warning: {
      icon: "⚠️",
      label: "Con advertencias",
      bgClass: "bg-yellow-500/10",
      borderClass: "border-yellow-500/30",
      textClass: "text-yellow-400",
    },
  };

  const status = report.status || "warning";
  const currentStatus =
    statusConfig[status as keyof typeof statusConfig] || statusConfig.warning;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.3 }}
      className={cn(
        "rounded-xl border shadow-lg overflow-hidden",
        currentStatus.borderClass,
        currentStatus.bgClass,
        className,
      )}
    >
      {/* Header */}
      <div className="px-5 py-4 border-b border-neutral-800/50">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-2xl">{currentStatus.icon}</span>
              <h3
                className={cn("text-lg font-semibold", currentStatus.textClass)}
              >
                Reporte de Auditoría
              </h3>
            </div>
            <p className="text-sm text-neutral-400 mt-1">
              Demo Capital - ID: {report.job_id?.slice(0, 8)}
            </p>
          </div>
          <div
            className={cn(
              "px-3 py-1 rounded-full text-sm font-medium",
              currentStatus.textClass,
              "border",
              currentStatus.borderClass,
            )}
          >
            {currentStatus.label}
          </div>
        </div>
      </div>

      {/* Summary Section */}
      <div className="px-5 py-4 bg-neutral-900/30">
        <div className="grid grid-cols-4 gap-4">
          {/* Total Findings */}
          <div className="text-center">
            <div className="text-2xl font-bold text-neutral-100">
              {totalFindings}
            </div>
            <div className="text-xs text-neutral-400 mt-1">Hallazgos</div>
          </div>

          {/* High Severity */}
          <div className="text-center">
            <div
              className={cn(
                "text-2xl font-bold",
                highFindings > 0 ? "text-red-400" : "text-neutral-600",
              )}
            >
              {highFindings}
            </div>
            <div className="text-xs text-neutral-400 mt-1">Alta</div>
          </div>

          {/* Medium Severity */}
          <div className="text-center">
            <div
              className={cn(
                "text-2xl font-bold",
                mediumFindings > 0 ? "text-yellow-400" : "text-neutral-600",
              )}
            >
              {mediumFindings}
            </div>
            <div className="text-xs text-neutral-400 mt-1">Media</div>
          </div>

          {/* Low Severity */}
          <div className="text-center">
            <div
              className={cn(
                "text-2xl font-bold",
                lowFindings > 0 ? "text-blue-400" : "text-neutral-600",
              )}
            >
              {lowFindings}
            </div>
            <div className="text-xs text-neutral-400 mt-1">Baja</div>
          </div>
        </div>
      </div>

      {/* Findings by Auditor */}
      {summary.auditor_summaries && summary.auditor_summaries.length > 0 && (
        <div className="px-5 py-4 space-y-3">
          <h4 className="text-sm font-semibold text-neutral-300 mb-3">
            Detalles por Auditor
          </h4>

          {summary.auditor_summaries.map((auditor, idx) => {
            const sectionKey = auditor.auditor_name;
            const isExpanded =
              expandedSections.has("all") || expandedSections.has(sectionKey);

            return (
              <motion.div
                key={sectionKey}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: idx * 0.1 }}
                className="rounded-lg border border-neutral-800 bg-neutral-900/50 overflow-hidden"
              >
                {/* Auditor Header */}
                <button
                  type="button"
                  onClick={() => toggleSection(sectionKey)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-neutral-800/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-base">
                      {getAuditorIcon(auditor.auditor_name)}
                    </span>
                    <div className="text-left">
                      <div className="text-sm font-medium text-neutral-100">
                        {getAuditorLabel(auditor.auditor_name)}
                      </div>
                      <div className="text-xs text-neutral-400">
                        {auditor.findings_count} hallazgo(s)
                      </div>
                    </div>
                  </div>
                  <motion.svg
                    className="h-5 w-5 text-neutral-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    animate={{ rotate: isExpanded ? 180 : 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 9l-7 7-7-7"
                    />
                  </motion.svg>
                </button>

                {/* Auditor Findings */}
                <AnimatePresence>
                  {isExpanded && auditor.findings_count > 0 && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="border-t border-neutral-800"
                    >
                      <div className="px-4 py-3 space-y-2 max-h-60 overflow-y-auto thin-scroll">
                        {/* TODO: Map actual findings here */}
                        <p className="text-xs text-neutral-400">
                          Ver detalles completos en el reporte
                        </p>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Footer Actions */}
      <div className="px-5 py-4 bg-neutral-900/30 border-t border-neutral-800/50 flex items-center justify-between">
        <p className="text-xs text-neutral-500">
          Generado {new Date(report.created_at).toLocaleString("es-ES")}
        </p>
        <button
          type="button"
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 border border-blue-500/30 transition-colors"
        >
          Re-auditar
        </button>
      </div>
    </motion.div>
  );
}

// Helper functions
function getAuditorIcon(auditorName: string): string {
  const icons: Record<string, string> = {
    compliance: "📋",
    disclaimer: "📋",
    format: "🎨",
    grammar: "✍️",
    logo: "🖼️",
    typography: "🔤",
    color_palette: "🌈",
    "color palette": "🌈",
    entity_consistency: "🔍",
    semantic_consistency: "🧠",
  };
  return icons[auditorName.toLowerCase()] || "📄";
}

function getAuditorLabel(auditorName: string): string {
  const labels: Record<string, string> = {
    compliance: "Cumplimiento",
    disclaimer: "Descargo de responsabilidad",
    format: "Formato y estilos",
    grammar: "Gramática y ortografía",
    logo: "Logo e imágenes",
    typography: "Tipografía",
    color_palette: "Paleta de colores",
    "color palette": "Paleta de colores",
    entity_consistency: "Consistencia de entidades",
    semantic_consistency: "Consistencia semántica",
  };
  return labels[auditorName.toLowerCase()] || auditorName;
}
