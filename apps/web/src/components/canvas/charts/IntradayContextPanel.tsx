import * as React from "react";
import type { ChartData } from "@/lib/types";

interface IntradayContextPanelProps {
  chart: ChartData;
}

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function hours(value: unknown): number[] {
  return Array.isArray(value)
    ? value.filter(
        (hour): hour is number =>
          typeof hour === "number" && Number.isInteger(hour),
      )
    : [];
}

function formatValue(value: number): string {
  return value.toLocaleString("es-MX", {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  });
}

function formatHour(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

export function IntradayContextPanel({ chart }: IntradayContextPanelProps) {
  const grounding = chart.analytics?.grounding;
  if (grounding?.capability !== "intraday_sales") return null;

  const cutoff = numeric(grounding.cutoff_hour);
  const partial = numeric(grounding.partial_hour);
  const future = hours(grounding.future_hours);
  const missingActual = hours(grounding.missing_actual_hours);
  const missingBenchmark = hours(grounding.missing_benchmark_hours);
  const actual = numeric(grounding.actual_cumulative);
  const delta = numeric(grounding.delta_absolute);
  const deltaPercent = numeric(grounding.delta_percent);
  const configured = grounding.comparison_status === "configured";
  const timezone =
    typeof grounding.timezone === "string"
      ? grounding.timezone
      : "America/Mexico_City";

  return (
    <section
      aria-label="Contexto de venta intradía"
      className="grid gap-2 rounded-lg border border-border bg-surface-2 p-3 text-xs text-foreground sm:grid-cols-2"
    >
      <div>
        <p className="font-semibold">
          {cutoff == null
            ? "Corte no disponible"
            : `Corte ${formatHour(cutoff)}`}
        </p>
        {actual != null && (
          <p className="mt-1">{formatValue(actual)} unidades acumuladas</p>
        )}
        <p className="mt-1 text-muted">Zona horaria: {timezone}</p>
      </div>

      <div>
        {configured && delta != null ? (
          <>
            <p className="font-semibold">
              {delta >= 0 ? "+" : ""}
              {formatValue(delta)} unidades
            </p>
            {deltaPercent != null && (
              <p className="mt-1">
                {deltaPercent >= 0 ? "+" : ""}
                {deltaPercent.toFixed(1)}% vs mismo día de semana anterior
              </p>
            )}
          </>
        ) : (
          <p className="font-semibold">
            Tendencia descriptiva, sin comparable válido
          </p>
        )}
      </div>

      <div className="sm:col-span-2">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted">
          <span>Horas anteriores: completas</span>
          {partial != null && <span>Hora {formatHour(partial)} parcial</span>}
          {future.length > 0 && (
            <span>
              {formatHour(future[0])}-{formatHour(future[future.length - 1])}{" "}
              futuras
            </span>
          )}
        </div>
        {missingActual.map((hour) => (
          <p key={`actual-${hour}`} className="mt-1 text-amber-600">
            Hora {formatHour(hour)} sin observación en actual.
          </p>
        ))}
        {missingBenchmark.map((hour) => (
          <p key={`benchmark-${hour}`} className="mt-1 text-amber-600">
            Hora {formatHour(hour)} sin observación en referencia.
          </p>
        ))}
        <p className="mt-1 text-muted">
          Las horas sin fila no se convierten en cero.
        </p>
      </div>
    </section>
  );
}

export default IntradayContextPanel;
