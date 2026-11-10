import * as React from "react";
import type { ChartData } from "@/lib/types";

interface CapacityViewProps {
  chart: ChartData;
  className?: string;
}

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function format(value: number | null, digits = 1): string {
  return value == null
    ? "No disponible"
    : value.toLocaleString("es-MX", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
}

export function CapacityView({ chart, className }: CapacityViewProps) {
  const analytics = chart.analytics;
  const rows = [...(analytics?.table_data ?? [])].sort(
    (left, right) =>
      Number(left.prioridad ?? Number.MAX_SAFE_INTEGER) -
      Number(right.prioridad ?? Number.MAX_SAFE_INTEGER),
  );

  return (
    <div className={className}>
      <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-foreground">
        <span className="font-semibold">Inventario de sistema al cierre.</span>{" "}
        No equivale a conteo físico. Capacidad sin fecha verificable; su
        vigencia puede diferir del corte de stock y venta.
      </div>

      <div className="space-y-2">
        {rows.map((row, index) => {
          const capacity = numeric(row.capacidad_unidades);
          const stock = numeric(row.stock_sistema);
          const utilization = numeric(row.utilizacion_pct);
          const coverage = numeric(row.cobertura_dias);
          const dailySales = numeric(row.venta_diaria);
          const overCapacity = utilization != null && utilization > 100;

          return (
            <article
              key={`${String(row.articulo_id ?? row.label)}-${index}`}
              data-testid="capacity-card"
              className="rounded-lg border border-border bg-surface p-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    {String(row.label ?? row.articulo_id ?? "SKU")}
                  </p>
                  <p className="text-[11px] text-muted">
                    Prioridad {String(row.prioridad ?? index + 1)} ·{" "}
                    {String(row.estado ?? "sin estado")}
                  </p>
                </div>
                <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-medium text-primary">
                  {String(row.accion_recomendada ?? "Revisar")}
                </span>
              </div>

              <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(10rem,1fr)]">
                <div>
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="font-medium text-foreground">
                      Utilización del anaquel
                    </span>
                    {capacity == null ||
                    capacity <= 0 ||
                    utilization == null ? (
                      <span className="text-muted">
                        Capacidad no disponible
                      </span>
                    ) : (
                      <span className="tabular-nums text-muted">
                        {format(stock, 0)} de {format(capacity, 0)} unidades (
                        {format(utilization)}%)
                      </span>
                    )}
                  </div>
                  {capacity != null &&
                    capacity > 0 &&
                    utilization != null &&
                    (overCapacity ? (
                      <div className="mt-2 rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1 text-xs font-medium text-red-600 dark:text-red-300">
                        {format(utilization)}%: excede la capacidad registrada
                      </div>
                    ) : (
                      <div
                        role="progressbar"
                        aria-label={`Utilización de ${String(row.label ?? row.articulo_id)}`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={utilization}
                        className="mt-2 h-2 overflow-hidden rounded-full bg-surface-2"
                      >
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{ width: `${Math.max(0, utilization)}%` }}
                        />
                      </div>
                    ))}
                </div>

                <div className="rounded-md bg-surface-2 p-2 text-xs">
                  <p className="font-semibold text-foreground">
                    Cobertura estimada
                  </p>
                  <p className="mt-1 text-muted">
                    {coverage == null
                      ? "Sin ritmo comparable"
                      : `${format(coverage)} días de venta`}
                  </p>
                  <p className="text-[10px] text-muted">
                    {dailySales == null
                      ? "Venta diaria no disponible"
                      : `${format(dailySales)} unidades/día`}
                  </p>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

export default CapacityView;
