import * as React from "react";
import { formatoValor } from "@/lib/charts/analytics-to-chart-data";

interface StoreComparisonSummaryProps {
  rows: Array<Record<string, unknown>>;
  unit?: string | null;
  period?: string | null;
}

const PERIOD_LABELS: Record<string, string> = {
  today: "Hoy",
  yesterday: "Ayer",
  last_7_days: "Últimos 7 días",
  last_30_days: "Últimos 30 días",
};

const UNIT_LABELS: Record<string, string> = {
  count: "unidades",
  currency: "MXN",
  percent: "pp",
};

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function signed(value: number, unit?: string | null): string {
  const sign = value > 0 ? "+" : "";
  const formatted =
    unit === "percent" ? value.toFixed(1) : formatoValor(value, unit);
  const unitLabel = unit ? UNIT_LABELS[unit] : null;
  return `${sign}${formatted}${unitLabel ? ` ${unitLabel}` : ""}`;
}

export function StoreComparisonSummary({
  rows,
  unit,
  period,
}: StoreComparisonSummaryProps) {
  const focus = rows.find((row) => row.comparison_role === "focus");
  const control = rows.find((row) => row.comparison_role === "control");
  const delta = numeric(focus?.delta_absolute);
  if (!focus || !control || delta == null) return null;

  const deltaPercent = numeric(focus.delta_percent);
  const focusLabel = String(focus.label ?? "Tienda foco");
  const controlLabel = String(control.label ?? "Tienda control");
  const periodLabel = period
    ? (PERIOD_LABELS[period] ?? period.replace(/_/g, " "))
    : "Periodo no declarado";

  return (
    <section
      aria-label="Resultado de comparación contra tienda control"
      className="grid gap-3 rounded-lg border border-border bg-surface p-3 sm:grid-cols-[minmax(0,1fr)_auto]"
    >
      <div>
        <p className="text-xs font-semibold text-foreground">{focusLabel}</p>
        <p className="mt-0.5 text-[11px] text-muted">
          vs {controlLabel} · {periodLabel}
        </p>
      </div>
      <div className="text-left sm:text-right">
        <p className="text-lg font-semibold tabular-nums text-foreground">
          {signed(delta, unit)}
        </p>
        {deltaPercent == null ? (
          <p className="text-[11px] text-muted">
            Porcentaje no disponible: control en cero
          </p>
        ) : (
          <p className="text-xs font-medium tabular-nums text-muted">
            {deltaPercent > 0 ? "+" : ""}
            {deltaPercent.toFixed(1)}%
          </p>
        )}
      </div>
    </section>
  );
}

export default StoreComparisonSummary;
