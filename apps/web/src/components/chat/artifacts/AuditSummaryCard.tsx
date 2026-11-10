"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { useCanvas } from "@/context/CanvasContext";
import type { AuditReportResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AuditSummaryCardProps {
  data: AuditReportResponse;
  className?: string;
}

export function AuditSummaryCard({ data, className }: AuditSummaryCardProps) {
  const params = useParams();
  const chatId = params?.chatId as string | undefined;
  const { openCanvas } = useCanvas();
  const displayName =
    data.metadata?.display_name ||
    data.metadata?.filename ||
    (data.doc_name && /^[0-9a-fA-F-]{20,}$/.test(data.doc_name)
      ? "Documento auditado"
      : data.doc_name);

  const stats = data?.stats || {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
  };

  const handleOpen = () => {
    const meta: any = data.metadata || {};
    openCanvas(data, {
      tab: "overview",
      sessionId: chatId,
      reportPdfUrl:
        meta?.attachments?.full_report_pdf?.url ||
        meta?.attachments?.full_report_pdf?.presigned_url ||
        meta?.attachments?.report_pdf_url ||
        meta?.report_pdf_url ||
        meta?.report_url ||
        meta?.pdf_url,
    });
  };

  // Generate business-oriented status message
  const getStatusMessage = () => {
    if (stats.critical > 0) {
      return {
        icon: "⚠️",
        text: "Requiere corrección inmediata",
        color: "text-red-400",
      };
    } else if (stats.high > 0) {
      return {
        icon: "📝",
        text: "Revisión recomendada",
        color: "text-orange-400",
      };
    } else if (stats.medium > 0 || stats.low > 0) {
      return {
        icon: "✓",
        text: "Documento en buen estado",
        color: "text-yellow-400",
      };
    } else {
      return {
        icon: "✅",
        text: "Aprobado para publicación",
        color: "text-green-400",
      };
    }
  };

  const status = getStatusMessage();

  return (
    <div
      className={cn(
        "rounded-lg border border-white/10 p-4 hover:border-saptiva/50 transition-all duration-200 text-white",
        className,
      )}
      style={{ backgroundColor: "#232B3A" }}
    >
      {/* Header */}
      <div className="flex items-start gap-3 mb-3">
        <div className="rounded-md bg-saptiva/20 p-2.5 flex-shrink-0 text-xl">
          {status.icon}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-white truncate">
            {displayName}
          </h3>
          <p className={cn("text-xs font-medium", status.color)}>
            {status.text}
          </p>
        </div>
      </div>

      {/* Simplified Stats - Business Language */}
      <div className="space-y-2 mb-3 text-xs">
        {stats.critical > 0 && (
          <div className="flex items-center justify-between px-3 py-2 rounded-md bg-red-500/10 border border-red-500/20">
            <span className="text-red-400 font-medium">Problemas críticos</span>
            <span className="text-red-400 font-bold">{stats.critical}</span>
          </div>
        )}
        {stats.high > 0 && (
          <div className="flex items-center justify-between px-3 py-2 rounded-md bg-orange-500/10 border border-orange-500/20">
            <span className="text-orange-400 font-medium">Recomendaciones</span>
            <span className="text-orange-400 font-bold">{stats.high}</span>
          </div>
        )}
        {(stats.medium > 0 || stats.low > 0) && (
          <div className="flex items-center justify-between px-3 py-2 rounded-md bg-sky-500/10 border border-sky-500/20">
            <span className="text-sky-400 font-medium">
              Sugerencias opcionales
            </span>
            <span className="text-sky-400 font-bold">
              {stats.medium + stats.low}
            </span>
          </div>
        )}
        {stats.critical === 0 &&
          stats.high === 0 &&
          stats.medium === 0 &&
          stats.low === 0 && (
            <div className="flex items-center justify-center px-3 py-2 rounded-md bg-green-500/10 border border-green-500/20">
              <span className="text-green-400 font-medium">
                ✅ Sin hallazgos - Documento aprobado
              </span>
            </div>
          )}
      </div>

      {/* Action Button */}
      <button
        onClick={handleOpen}
        className="
          w-full px-4 py-2 rounded-md
          bg-saptiva/20 border border-saptiva
          text-sm font-semibold text-saptiva
          hover:bg-saptiva/30 hover:border-saptiva/80
          transition-colors duration-200
        "
      >
        Abrir Análisis Completo
      </button>
    </div>
  );
}
