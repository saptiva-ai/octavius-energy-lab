import * as React from "react";
import type { ChartData } from "@/lib/types";

interface ReliabilityViewProps {
  chart: ChartData;
  className?: string;
}

const STATE_LABELS: Record<string, string> = {
  bajo_umbral: "Bajo umbral",
  sin_evidencia: "Sin evidencia",
  evidencia_rezagada: "Evidencia rezagada",
  observada: "Evidencia vigente",
};

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function format(value: number | null, digits = 1): string {
  return value == null
    ? "Sin evidencia"
    : value.toLocaleString("es-MX", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
}

function formatDate(value: unknown): string {
  if (typeof value !== "string" || !value) return "Sin auditoría";
  const parsed = new Date(`${value.slice(0, 10)}T12:00:00Z`);
  if (!Number.isFinite(parsed.getTime())) return "Fecha no disponible";
  return parsed.toLocaleDateString("es-MX", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function ReliabilityView({ chart, className }: ReliabilityViewProps) {
  const analytics = chart.analytics;
  const target = analytics?.visualization?.target;
  const targetConfigured =
    analytics?.visualization?.target_status === "configured" && target != null;
  const caveats = Array.isArray(analytics?.grounding?.caveats)
    ? analytics.grounding.caveats.filter(
        (value): value is string => typeof value === "string",
      )
    : [];
  const formulaCaveat =
    caveats.find((value) => value.toLowerCase().includes("fórmula")) ??
    "La fórmula de origen sigue en draft y debe confirmarse con el cliente.";
  const rows = [...(analytics?.table_data ?? [])].sort(
    (left, right) =>
      Number(left.prioridad ?? Number.MAX_SAFE_INTEGER) -
      Number(right.prioridad ?? Number.MAX_SAFE_INTEGER),
  );

  return (
    <div className={className}>
      <div className="mb-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-foreground">
        <span className="font-semibold">Definición en draft.</span>{" "}
        {formulaCaveat}
      </div>
      <div className="mb-3 text-xs text-muted">
        {targetConfigured ? (
          <span>
            {target.label}: {format(target.value)}%
            {target.source ? ` · Fuente: ${target.source}` : ""}
            {target.version ? ` · Versión: ${target.version}` : ""}
          </span>
        ) : (
          <span>
            Sin umbral configurado. Lectura descriptiva, sin color de
            cumplimiento.
          </span>
        )}
      </div>

      <div className="space-y-2">
        {rows.map((row, index) => {
          const value = numeric(row.value);
          const auditCount = numeric(row.audit_count) ?? 0;
          const sampleSize = numeric(row.sample_size) ?? 0;
          const auditedSkus = numeric(row.audited_skus) ?? 0;
          const eligibleSkus = numeric(row.eligible_skus) ?? 0;
          const coverage = numeric(row.sample_coverage_pct);
          const delta = numeric(row.delta_to_target);
          const state = String(row.estado_evidencia ?? "sin_evidencia");

          return (
            <article
              key={`${String(row.label ?? "grupo")}-${index}`}
              data-testid="reliability-card"
              className="rounded-lg border border-border bg-surface p-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    {String(row.label ?? "Grupo sin etiqueta")}
                  </p>
                  <p className="text-[11px] text-muted">
                    Prioridad {String(row.prioridad ?? index + 1)} ·{" "}
                    {STATE_LABELS[state] ?? state}
                  </p>
                </div>
                <span className="text-lg font-semibold tabular-nums text-foreground">
                  {value == null ? "Sin evidencia" : `${format(value)}%`}
                </span>
              </div>

              {value != null && (
                <div
                  role="progressbar"
                  aria-label={`Confiabilidad de ${String(row.label ?? "grupo")}`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={value}
                  className="relative mt-3 h-2 rounded-full bg-surface-2"
                >
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
                  />
                  {targetConfigured && (
                    <span
                      aria-hidden="true"
                      className="absolute top-[-3px] h-4 w-0.5 bg-foreground"
                      style={{
                        left: `${Math.max(0, Math.min(100, target.value))}%`,
                      }}
                    />
                  )}
                </div>
              )}

              <div className="mt-3 grid gap-2 text-xs sm:grid-cols-3">
                <div className="rounded-md bg-surface-2 p-2">
                  <p className="font-semibold text-foreground">
                    {auditCount} {auditCount === 1 ? "auditoría" : "auditorías"}
                  </p>
                  <p className="text-[10px] text-muted">
                    {sampleSize} mediciones válidas
                  </p>
                </div>
                <div className="rounded-md bg-surface-2 p-2">
                  <p className="font-semibold text-foreground">
                    Cobertura de muestra
                  </p>
                  <p className="text-[10px] text-muted">
                    {auditedSkus} de {eligibleSkus} SKU
                    {coverage != null ? ` (${format(coverage)}%)` : ""}
                  </p>
                </div>
                <div className="rounded-md bg-surface-2 p-2">
                  <p className="font-semibold text-foreground">
                    Última auditoría: {formatDate(row.last_audit_date)}
                  </p>
                  <p className="text-[10px] text-muted">
                    {numeric(row.audit_age_days) == null
                      ? "Vigencia no disponible"
                      : `${format(numeric(row.audit_age_days), 0)} días de antigüedad`}
                  </p>
                </div>
              </div>

              {delta != null && (
                <p className="mt-2 text-xs font-medium text-muted">
                  Brecha contra umbral: {delta > 0 ? "+" : ""}
                  {format(delta)} pp
                </p>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}

export default ReliabilityView;
