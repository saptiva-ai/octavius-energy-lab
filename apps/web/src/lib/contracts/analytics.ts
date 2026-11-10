/**
 * Contrato del plugin retail-advisor (espejo de
 * plugins/retail-advisor/src/retailadvisor/schemas.py — schema_version 1).
 *
 * Regla R2 del refactor: ningún shape del backend se renderiza sin tipo aquí.
 * El plugin garantiza `chart_type` EXPLÍCITO (regla anti-deuda #3) y
 * `freshness`/`data_as_of` para no alucinar frescura (inventario es
 * día-cerrado, solo ventas es intradía).
 */

export const ANALYTICS_SCHEMA_VERSION = "1";

export type AnalyticsChartType =
  | "line"
  | "bar"
  | "table"
  | "scatter"
  | "sankey"
  | "alerts"
  | "map" // choropleth por región (2026-07-13, aditivo — schema_version 1)
  | "none";

export type AnalyticsFreshness =
  | "intraday"
  | "daily" // forecast de demanda (2026-07-20, aditivo — schema_version 1)
  | "day_closed"
  | "monthly"
  | "unknown";

export interface AnalyticsSeriesPoint {
  label: string;
  value: number;
  dimension?: string | null;
  interval_low?: number | null;
  interval_high?: number | null;
}

export interface AnalyticsSeries {
  name: string;
  points: AnalyticsSeriesPoint[];
  // Serie observada vs proyectada: el canvas pinta el forecast punteado
  // (2026-07-24, aditivo — schema_version 1).
  role?: "real" | "forecast" | null;
}

export type AnalyticsVisualizationTask =
  | "trend"
  | "comparison"
  | "ranking"
  | "status"
  | "composition"
  | "spatial"
  | "table";

export interface AnalyticsVisualizationReference {
  label: string;
  value: number;
  source?: string | null;
  version?: string | null;
}

export interface AnalyticsVisualization {
  task: AnalyticsVisualizationTask;
  title: string;
  subtitle?: string | null;
  headline?: string | null;
  higher_is_better?: boolean | null;
  target?: AnalyticsVisualizationReference | null;
  target_status?: "configured" | "not_configured" | null;
  benchmark?: AnalyticsVisualizationReference | null;
  sample_size?: number | null;
}

export interface AnalyticsGrounding {
  source?: string; // "retail-advisor"
  capability?: string; // "alerts" | "prediction" | metric query
  metric?: string;
  unit?: string | null;
  dimension?: string | null;
  period?: string | null;
  tienda?: string | null;
  freshness?: AnalyticsFreshness;
  data_as_of?: string | null;
  [key: string]: unknown;
}

export interface AnalyticsResponse {
  metric_name: string;
  chart_type: AnalyticsChartType;
  series: AnalyticsSeries[];
  table_data: Array<Record<string, unknown>>;
  response_text: string;
  grounding: AnalyticsGrounding;
  error: string | null;
  schema_version: string;
  data_as_of: string | null;
  freshness: AnalyticsFreshness;
  // Aditivo: mensajes históricos pueden no traerlo.
  visualization?: AnalyticsVisualization | null;
}

/** Guard estructural: identifica una respuesta del contrato retail. */
export function isAnalyticsResponse(
  value: unknown,
): value is AnalyticsResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.metric_name === "string" &&
    typeof v.schema_version === "string" &&
    typeof v.chart_type === "string" &&
    Array.isArray(v.series)
  );
}
