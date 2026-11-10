"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { AuditReportResponse } from "@/lib/types";

interface AuditDetailViewProps {
  report: AuditReportResponse;
  className?: string;
}

const PANEL_BG = "#232B3A";
const PANEL_SURFACE = "#1E2533";

const CATEGORY_LABELS: Record<string, string> = {
  compliance: "Cumplimiento",
  disclaimer: "Descargos",
  format: "Formato",
  typography: "Tipografía",
  typography_checker: "Tipografía",
  grammar: "Gramática",
  logo: "Identidad visual",
  brand_logo: "Identidad visual",
  color_palette: "Paleta de colores",
  "color palette": "Paleta de colores",
  color: "Paleta de colores",
  colors: "Paleta de colores",
  color_palette_checker: "Paleta de colores",
  entity_consistency: "Consistencia de entidades",
  semantic_consistency: "Consistencia semántica",
  linguistic: "Lingüístico",
  language: "Lingüístico",
};

function formatCategoryName(raw: string): string {
  if (!raw) return "";
  const normalized = raw.toLowerCase();
  return (
    CATEGORY_LABELS[normalized] ||
    raw.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase())
  );
}

function DonutChart({
  critical,
  high,
  low,
  medium,
}: {
  critical: number;
  high: number;
  low: number;
  medium: number;
}) {
  const total = critical + high + medium + low || 1;
  const pct = (n: number) => Math.round((n / total) * 100);

  const segments = [
    { color: "#ef4444", value: pct(critical) },
    { color: "#f97316", value: pct(high) },
    { color: "#eab308", value: pct(medium) },
    { color: "#38bdf8", value: pct(low) },
  ];

  const conic = segments
    .reduce(
      (acc, seg) => {
        const start = acc.offset;
        const end = start + seg.value;
        acc.offset = end;
        acc.stops.push(`${seg.color} ${start}% ${end}%`);
        return acc;
      },
      { offset: 0, stops: [] as string[] },
    )
    .stops.join(", ");

  return (
    <div className="flex items-center gap-4">
      <div
        className="relative h-24 w-24 rounded-full"
        style={{ background: `conic-gradient(${conic})` }}
      >
        <div className="absolute inset-3 rounded-full bg-slate-950" />
        <div className="absolute inset-5 flex items-center justify-center text-sm font-semibold text-white">
          {total}
        </div>
      </div>
      <div className="space-y-1 text-sm text-saptiva-light">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[#ef4444]" />
          <span>Crítico: {critical}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[#f97316]" />
          <span>Alto: {high}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[#eab308]" />
          <span>Medio: {medium}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[#38bdf8]" />
          <span>Bajo: {low}</span>
        </div>
      </div>
    </div>
  );
}

export function AuditDetailView({ report, className }: AuditDetailViewProps) {
  const categories = React.useMemo<[string, any[]][]>(() => {
    const normalized = Object.entries(report.categories || {}).reduce<
      Record<string, any[]>
    >((acc, [key, value]) => {
      acc[key.toLowerCase()] = Array.isArray(value) ? value : [];
      return acc;
    }, {});

    const orderedKeys = [
      "compliance",
      "disclaimer",
      "format",
      "typography",
      "grammar",
      "logo",
      "color_palette",
      "entity_consistency",
      "semantic_consistency",
      "linguistic",
    ];

    const ordered = orderedKeys.map(
      (key) => [key, normalized[key] || []] as [string, any[]],
    );
    const extra = Object.entries(normalized).filter(
      ([key]) => !orderedKeys.includes(key),
    ) as [string, any[]][];
    return [...ordered, ...extra];
  }, [report.categories]);
  const rawName =
    report.metadata?.display_name ||
    report.metadata?.filename ||
    (report.doc_name && /^[0-9a-fA-F-]{20,}$/.test(report.doc_name)
      ? "Documento auditado"
      : report.doc_name);
  const displayName = rawName
    ? rawName.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase())
    : "Documento auditado";
  const summaryText = React.useMemo(() => {
    const summary = (report.metadata as any)?.summary;
    if (!summary) return null;
    if (typeof summary === "string") return summary;
    if (typeof summary === "object") {
      return (
        summary.text ||
        summary.summary ||
        summary.overview ||
        summary.short ||
        null
      );
    }
    return null;
  }, [report.metadata]);

  // Defensive: ensure stats exist with default values
  const stats = report.stats || {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    total: 0,
  };

  return (
    <div
      className={cn("flex h-full flex-col gap-4 text-white", className)}
      style={{ backgroundColor: PANEL_BG }}
    >
      <header
        className="flex items-start justify-between gap-3 border-b border-white/10 pb-3"
        style={{ backgroundColor: PANEL_BG }}
      >
        <div>
          <p className="text-[11px] uppercase tracking-wide text-saptiva-light/60">
            Reporte de Auditoría
          </p>
          <h2 className="text-sm font-semibold text-white">{displayName}</h2>
          <p className="text-[11px] text-saptiva-light/70">
            Policy: {report.metadata?.policy_used?.name || "N/D"}
          </p>
        </div>
      </header>

      <section className="flex items-center justify-center py-1">
        <DonutChart
          critical={stats.critical}
          high={stats.high}
          medium={stats.medium}
          low={stats.low}
        />
      </section>

      {summaryText && (
        <section
          className="rounded-lg border border-white/10 p-3 text-sm text-saptiva-light"
          style={{ backgroundColor: PANEL_SURFACE }}
        >
          <p className="text-xs uppercase tracking-wide text-saptiva-light/60">
            Resumen ejecutivo
          </p>
          <p className="mt-1 text-white leading-relaxed">{summaryText}</p>
        </section>
      )}

      <section
        className="flex-1 overflow-auto rounded-lg border border-white/10 p-3"
        style={{ backgroundColor: PANEL_SURFACE }}
      >
        <div className="space-y-3">
          {categories.every(([, findings]) => !findings.length) && (
            <div className="text-sm text-saptiva-light/70">
              Sin hallazgos registrados.
            </div>
          )}
          {categories.map(([cat, findings]) => (
            <details
              key={cat}
              className="group rounded-md border border-white/10 p-3"
              style={{ backgroundColor: PANEL_BG }}
            >
              <summary
                className="flex cursor-pointer items-center justify-between rounded-md border border-white/10 px-3 py-2 text-sm font-semibold list-none hover:border-saptiva/50 transition-colors"
                style={{ backgroundColor: PANEL_SURFACE }}
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs text-saptiva-light/70 transition-transform group-open:rotate-90">
                    ▸
                  </span>
                  <span>{formatCategoryName(cat)}</span>
                </div>
                <span className="text-xs text-saptiva-light/70 flex items-center gap-1">
                  {findings.length} hallazgos
                </span>
              </summary>
              <div className="mt-2 space-y-2 text-sm text-saptiva-light">
                {findings.length === 0 ? (
                  <div
                    className="rounded border border-dashed border-white/10 p-3 text-xs text-saptiva-light/70"
                    style={{ backgroundColor: PANEL_SURFACE }}
                  >
                    Sin hallazgos para este auditor.
                  </div>
                ) : (
                  findings.map((f, idx) => (
                    <div
                      key={`${f.id || idx}-${(f.message || "").slice(0, 20)}`}
                      className="rounded border border-white/10 p-2"
                      style={{ backgroundColor: PANEL_SURFACE }}
                    >
                      {(() => {
                        const message = (f.message || "").trim();
                        const suggestion = (f.suggestion || "").trim();
                        const description =
                          message || suggestion || "Sin descripción";

                        return (
                          <>
                            <div className="flex items-center justify-between text-xs uppercase tracking-tight">
                              <span
                                className={cn(
                                  "font-semibold",
                                  f.severity === "critical"
                                    ? "text-red-400"
                                    : f.severity === "high"
                                      ? "text-orange-400"
                                      : f.severity === "medium"
                                        ? "text-yellow-300"
                                        : "text-sky-300",
                                )}
                              >
                                {f.severity}
                              </span>
                              {f.page && (
                                <span className="text-[11px] text-saptiva-light/60">
                                  Página {f.page}
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-sm text-white">
                              {description}
                            </p>
                            {suggestion && description !== suggestion && (
                              <p className="text-xs text-saptiva-light/70">
                                Sugerencia: {suggestion}
                              </p>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  ))
                )}
              </div>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
