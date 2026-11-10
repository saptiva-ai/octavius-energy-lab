/**
 * ComplianceBadge Component
 *
 * Compact badge for file attachments showing Copiloto Audit validation status.
 * Displays:
 * - Icon + severity count (e.g., "🔴 2 🟠 1")
 * - Clickable to open modal with full ValidationFindings
 * - Loading state while fetching report
 * - Graceful no-report state (hidden if not validated)
 *
 * Usage:
 * <ComplianceBadge documentId="doc-123" />
 */

"use client";

import React, { useState, useEffect } from "react";
import { apiClient } from "@/lib/api-client";
import type {
  ValidationReportResponse,
  FindingSeverity,
} from "@/types/validation";
import { cn } from "@/lib/utils";
import { ValidationFindings } from "./ValidationFindings";
import { logError } from "@/lib/logger";

interface ComplianceBadgeProps {
  documentId: string;
  className?: string;
}

const severityIcons: Record<FindingSeverity, string> = {
  critical: "🔴",
  high: "🟠",
  medium: "🟡",
  low: "🔵",
};

export function ComplianceBadge({
  documentId,
  className,
}: ComplianceBadgeProps) {
  const [report, setReport] = useState<ValidationReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    const fetchReport = async () => {
      try {
        setLoading(true);
        setError(null);

        const validationReport =
          await apiClient.getDocumentValidation(documentId);
        setReport(validationReport);
      } catch (err: any) {
        // 404 means no validation report exists - this is expected for documents that haven't been audited
        if (err.response?.status === 404) {
          setReport(null); // Hide badge
        } else {
          logError("Failed to fetch validation report:", err);
          setError(err.message || "Error al cargar reporte");
        }
      } finally {
        setLoading(false);
      }
    };

    fetchReport();
  }, [documentId]);

  // Don't show badge if no report exists or still loading
  if (loading || !report) {
    return null;
  }

  // Don't show badge if there was an error
  if (error) {
    return null;
  }

  const { summary } = report;
  const totalFindings = summary.total_findings;
  const bySeverity = summary.findings_by_severity;

  // Build compact display: "🔴 2 🟠 1" or "✅" if no findings
  const buildSummaryText = () => {
    if (totalFindings === 0) {
      return "✅";
    }

    const parts: string[] = [];
    if (bySeverity.critical > 0)
      parts.push(`${severityIcons.critical} ${bySeverity.critical}`);
    if (bySeverity.high > 0)
      parts.push(`${severityIcons.high} ${bySeverity.high}`);
    if (bySeverity.medium > 0)
      parts.push(`${severityIcons.medium} ${bySeverity.medium}`);
    if (bySeverity.low > 0)
      parts.push(`${severityIcons.low} ${bySeverity.low}`);

    return parts.join(" ");
  };

  const summaryText = buildSummaryText();

  // Badge styling based on findings
  const badgeVariant =
    totalFindings === 0
      ? "success"
      : bySeverity.critical > 0
        ? "error"
        : bySeverity.high > 0
          ? "warning"
          : "info";

  return (
    <>
      {/* Badge Button */}
      <button
        onClick={() => setModalOpen(true)}
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all hover:scale-105",
          totalFindings === 0
            ? "bg-green-100 text-green-700 border border-green-200 hover:bg-green-200"
            : bySeverity.critical > 0
              ? "bg-red-100 text-red-700 border border-red-200 hover:bg-red-200"
              : bySeverity.high > 0
                ? "bg-orange-100 text-orange-700 border border-orange-200 hover:bg-orange-200"
                : "bg-blue-100 text-blue-700 border border-blue-200 hover:bg-blue-200",
          className,
        )}
        aria-label="Ver reporte de validación de cumplimiento"
      >
        <span className="text-[10px]">📋</span>
        <span>{summaryText}</span>
      </button>

      {/* Modal with Full Report */}
      {modalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          onClick={() => setModalOpen(false)}
        >
          <div
            className="relative max-w-4xl w-full max-h-[90vh] overflow-y-auto bg-zinc-900 rounded-2xl shadow-2xl border border-zinc-700"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close Button */}
            <button
              onClick={() => setModalOpen(false)}
              className="absolute top-4 right-4 z-10 p-2 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
              aria-label="Cerrar"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>

            {/* Validation Findings Component */}
            <ValidationFindings report={report} />
          </div>
        </div>
      )}
    </>
  );
}
