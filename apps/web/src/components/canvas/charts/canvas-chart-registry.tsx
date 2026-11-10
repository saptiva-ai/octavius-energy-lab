/**
 * Registry tipo -> componente para las visualizaciones del canvas (F5 del
 * EPIC refactor-web-arquitectura). Reemplaza el switch/if de ChartPlaceholder
 * por un lookup: agregar una visualización nueva (AlertCards, PredictionList)
 * es registrar una entrada aquí, no editar canvas-panel.tsx.
 */
import * as React from "react";
import type { ChartData } from "@/lib/types";
import { PlotlyChartView } from "./PlotlyChartView";
import { AlertCards } from "./AlertCards";
import { PredictionView } from "./PredictionView";
import { CapacityView } from "./CapacityView";
import { ReliabilityView } from "./ReliabilityView";
import { RecencyRankingView } from "./RecencyRankingView";
import { CompositionView } from "./CompositionView";

export type CanvasChartKind =
  | "plotly"
  | "alerts"
  | "prediction"
  | "capacity"
  | "reliability"
  | "recency"
  | "composition";

interface ChartRegistryEntry {
  matches: (chart: ChartData) => boolean;
  render: (chart: ChartData) => React.ReactNode;
}

const REGISTRY: ChartRegistryEntry[] = [
  {
    matches: (chart) => chart.analytics?.chart_type === "alerts",
    render: (chart) => <AlertCards chart={chart} />,
  },
  {
    // predecir_faltante_hoy usa una lista priorizada, incluso al reabrir una
    // respuesta histórica cuyo chart_type era sankey.
    matches: (chart) => chart.analytics?.grounding?.capability === "prediction",
    render: (chart) => <PredictionView chart={chart} />,
  },
  {
    matches: (chart) =>
      chart.analytics?.grounding?.capability === "shelf_capacity",
    render: (chart) => (
      <CapacityView chart={chart} className="h-full min-h-0" />
    ),
  },
  {
    matches: (chart) =>
      chart.analytics?.grounding?.capability === "inventory_reliability",
    render: (chart) => (
      <ReliabilityView chart={chart} className="h-full min-h-0" />
    ),
  },
  {
    matches: (chart) =>
      chart.analytics?.grounding?.capability === "sales_recency",
    render: (chart) => (
      <RecencyRankingView chart={chart} className="h-full min-h-0" />
    ),
  },
  {
    matches: (chart) => {
      const related = chart.analytics?.grounding?.related_views;
      return (
        chart.analytics?.grounding?.capability === "composition" &&
        typeof related === "object" &&
        related !== null &&
        Array.isArray((related as Record<string, unknown>).panels)
      );
    },
    render: (chart) => (
      <CompositionView chart={chart} className="h-full min-h-0" />
    ),
  },
  {
    matches: () => true, // catch-all: cualquier otro ChartData es un plot Plotly
    render: (chart) => <PlotlyChartView chart={chart} />,
  },
];

export function renderCanvasChart(chart: ChartData): React.ReactNode {
  const entry = REGISTRY.find((e) => e.matches(chart));
  return entry ? entry.render(chart) : null;
}
