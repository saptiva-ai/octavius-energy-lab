import * as React from "react";
import type { ChartData } from "@/lib/types";

interface RecencyRankingViewProps {
  chart: ChartData;
  className?: string;
}

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function format(value: number): string {
  return value.toLocaleString("es-MX", {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  });
}

export function RecencyRankingView({
  chart,
  className,
}: RecencyRankingViewProps) {
  const analytics = chart.analytics;
  const target = analytics?.visualization?.target;
  const targetConfigured =
    analytics?.visualization?.target_status === "configured" && target != null;
  const rows = [...(analytics?.table_data ?? [])].sort(
    (left, right) =>
      Number(left.prioridad ?? Number.MAX_SAFE_INTEGER) -
      Number(right.prioridad ?? Number.MAX_SAFE_INTEGER),
  );
  const maxValue = Math.max(
    targetConfigured ? target.value : 0,
    ...rows.map((row) => numeric(row.value) ?? 0),
    1,
  );
  const tailOmitted = numeric(analytics?.grounding?.tail_omitted) ?? 0;

  return (
    <div className={className}>
      <div className="mb-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-foreground">
        <span className="font-semibold">Señal para investigar.</span> Es
        recencia desde la última venta observada; no confirma faltante físico.
      </div>
      <div className="mb-3 text-xs text-muted">
        {targetConfigured ? (
          <span>
            {target.label}: {format(target.value)} días
            {target.source ? ` · Fuente: ${target.source}` : ""}
            {target.version ? ` · Versión: ${target.version}` : ""}
          </span>
        ) : (
          <span>
            Sin umbral configurado. Ranking descriptivo, sin estado de revisión.
          </span>
        )}
      </div>

      <div className="space-y-3">
        {rows.map((row, index) => {
          const value = numeric(row.value);
          const needsReview = row.estado_recencia === "revisar";
          if (value == null) return null;
          return (
            <article
              key={`${String(row.articulo_id ?? row.label)}-${index}`}
              data-testid="recency-row"
              className="grid gap-2 rounded-lg border border-border bg-surface p-3 sm:grid-cols-[minmax(10rem,1fr)_minmax(12rem,2fr)_auto]"
            >
              <div className="min-w-0">
                <p className="whitespace-normal break-words text-sm font-semibold text-foreground">
                  {String(row.label ?? row.articulo_id ?? "SKU")}
                </p>
                {row.articulo_id != null && (
                  <p className="text-[10px] text-muted">
                    {String(row.articulo_id)}
                  </p>
                )}
              </div>

              <div className="self-center">
                <div
                  role="progressbar"
                  aria-label={`${String(row.label ?? row.articulo_id)}: ${format(value)} días sin venta${
                    targetConfigured
                      ? `, umbral ${format(target.value)} días`
                      : ""
                  }`}
                  aria-valuemin={0}
                  aria-valuemax={maxValue}
                  aria-valuenow={value}
                  className="relative h-3 rounded-full bg-surface-2"
                >
                  <div
                    className={`h-full rounded-full ${
                      needsReview ? "bg-red-500" : "bg-primary"
                    }`}
                    style={{ width: `${(100 * value) / maxValue}%` }}
                  />
                  {targetConfigured && (
                    <span
                      aria-hidden="true"
                      className="absolute top-[-3px] h-5 w-0.5 bg-foreground"
                      style={{ left: `${(100 * target.value) / maxValue}%` }}
                    />
                  )}
                </div>
                <p className="mt-1 text-[10px] text-muted">
                  {value === 1 ? "1 día" : `${format(value)} días`} desde la
                  última venta
                  {/* GRA-12: junto a barras de cientos de días la marca del
                      umbral no se ve; se dice en texto. */}
                  {targetConfigured
                    ? ` · umbral ${format(target.value)} días`
                    : ""}
                </p>
              </div>

              <div className="flex items-center justify-between gap-3 sm:flex-col sm:items-end sm:justify-center">
                <span className="font-semibold tabular-nums text-foreground">
                  {format(value)} días
                </span>
                <span
                  className={`rounded-full px-2 py-1 text-xs font-medium ${
                    needsReview
                      ? "bg-red-500/10 text-red-600 dark:text-red-300"
                      : "bg-primary/10 text-primary"
                  }`}
                >
                  {needsReview ? "Investigar" : "Monitorear"}
                </span>
              </div>
            </article>
          );
        })}
      </div>

      {tailOmitted > 0 && (
        <p className="mt-3 text-xs text-muted">
          {format(tailOmitted)} SKU adicionales fuera del top mostrado.
        </p>
      )}
      {analytics?.grounding?.pareto_status ===
        "omitted_no_additive_measure" && (
        <p className="mt-1 text-xs text-muted">
          Pareto omitido: los días de recencia no son una magnitud aditiva de
          impacto.
        </p>
      )}
    </div>
  );
}

export default RecencyRankingView;
