import * as React from "react";
import type { ChartData } from "@/lib/types";

interface MetricContextNoteProps {
  chart: ChartData;
}

export function MetricContextNote({ chart }: MetricContextNoteProps) {
  const analytics = chart.analytics;
  const visualization = analytics?.visualization;
  const target = visualization?.target;
  const definition =
    typeof analytics?.grounding?.business_definition === "string"
      ? analytics.grounding.business_definition
      : null;
  const rawCaveats = analytics?.grounding?.caveats;
  const caveats = Array.isArray(rawCaveats)
    ? rawCaveats.filter((value): value is string => typeof value === "string")
    : [];
  const isForecast = analytics?.grounding?.capability === "demand_forecast";
  const provider =
    typeof analytics?.grounding?.proveedor === "string"
      ? analytics.grounding.proveedor
      : null;
  const horizon =
    typeof analytics?.grounding?.horizonte_dias === "number"
      ? analytics.grounding.horizonte_dias
      : null;
  const cutoff =
    typeof analytics?.grounding?.forecast_cutoff === "string"
      ? analytics.grounding.forecast_cutoff
      : null;
  const rawLimitations = analytics?.grounding?.limitations;
  const limitations = Array.isArray(rawLimitations)
    ? rawLimitations.filter(
        (value): value is string => typeof value === "string",
      )
    : [];
  const intervalSemantics =
    typeof analytics?.grounding?.interval_semantics === "string"
      ? analytics.grounding.interval_semantics
      : null;
  const hasContext =
    isForecast ||
    visualization?.target_status != null ||
    visualization?.sample_size != null ||
    definition != null ||
    caveats.length > 0;

  if (!hasContext) return null;

  return (
    <div className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs text-muted">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {isForecast && (
          <span className="font-medium text-foreground">
            Provider: {provider ?? "no declarado"}
            {horizon != null ? ` · Horizonte: ${horizon} días` : ""}
            {cutoff ? ` · Corte: ${cutoff}` : ""}
          </span>
        )}
        {visualization?.target_status === "configured" && target ? (
          <span className="font-medium text-foreground">
            {target.label}: {target.value.toFixed(1)}%
            {target.source ? ` · Fuente: ${target.source}` : ""}
            {target.version ? ` · Versión: ${target.version}` : ""}
          </span>
        ) : visualization?.target_status === "not_configured" ? (
          <span>
            Sin meta configurada. Lectura descriptiva, sin color de
            cumplimiento.
          </span>
        ) : null}
        {visualization?.sample_size != null && (
          <span>Muestra: {visualization.sample_size} registros</span>
        )}
      </div>

      {limitations.map((limitation) => (
        <p key={limitation} className="mt-1">
          {limitation}
        </p>
      ))}
      {intervalSemantics && <p className="mt-1">{intervalSemantics}</p>}

      {(definition || caveats.length > 0) && (
        <details className="mt-1">
          <summary className="cursor-pointer font-medium text-foreground">
            Definición y alcance
          </summary>
          {definition && <p className="mt-1">{definition}</p>}
          {caveats.map((caveat) => (
            <p key={caveat} className="mt-1">
              {caveat}
            </p>
          ))}
        </details>
      )}
    </div>
  );
}

export default MetricContextNote;
