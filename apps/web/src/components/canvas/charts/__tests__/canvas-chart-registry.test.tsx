import { render, screen } from "@testing-library/react";
import { renderCanvasChart } from "../canvas-chart-registry";
import type { ChartData } from "@/lib/types";

jest.mock("../PlotlyChartView", () => ({
  PlotlyChartView: () => <div>Mocked PlotlyChartView</div>,
}));
jest.mock("../AlertCards", () => ({
  AlertCards: () => <div>Mocked AlertCards</div>,
}));
jest.mock("../PredictionView", () => ({
  PredictionView: () => <div>Mocked PredictionView</div>,
}));
jest.mock("../CapacityView", () => ({
  CapacityView: () => <div>Mocked CapacityView</div>,
}));
jest.mock("../ReliabilityView", () => ({
  ReliabilityView: () => <div>Mocked ReliabilityView</div>,
}));
jest.mock("../RecencyRankingView", () => ({
  RecencyRankingView: () => <div>Mocked RecencyRankingView</div>,
}));
jest.mock("../CompositionView", () => ({
  CompositionView: () => <div>Mocked CompositionView</div>,
}));

function buildChart(
  chartType: string | undefined,
  capability?: string,
): ChartData {
  return {
    type: "chart",
    plotly_config: { data: [], layout: {} },
    analytics: chartType
      ? ({
          metric_name: "x",
          chart_type: chartType,
          series: [],
          table_data: [],
          response_text: "",
          grounding: capability ? { capability } : {},
          error: null,
          schema_version: "1",
          data_as_of: null,
          freshness: "unknown",
        } as any)
      : undefined,
  };
}

describe("canvas-chart-registry", () => {
  it("routes chart_type=alerts to AlertCards", () => {
    render(<>{renderCanvasChart(buildChart("alerts"))}</>);
    expect(screen.getByText("Mocked AlertCards")).toBeInTheDocument();
  });

  it("routes prediction to the prioritized view, including historical sankeys", () => {
    render(<>{renderCanvasChart(buildChart("sankey", "prediction"))}</>);
    expect(screen.getByText("Mocked PredictionView")).toBeInTheDocument();
  });

  it("routes shelf capacity to its operational view", () => {
    render(<>{renderCanvasChart(buildChart("bar", "shelf_capacity"))}</>);
    expect(screen.getByText("Mocked CapacityView")).toBeInTheDocument();
  });

  it("routes inventory reliability to its evidence view", () => {
    render(
      <>{renderCanvasChart(buildChart("bar", "inventory_reliability"))}</>,
    );
    expect(screen.getByText("Mocked ReliabilityView")).toBeInTheDocument();
  });

  it("routes sales recency to its horizontal ranking", () => {
    render(<>{renderCanvasChart(buildChart("bar", "sales_recency"))}</>);
    expect(screen.getByText("Mocked RecencyRankingView")).toBeInTheDocument();
  });

  it("routes related composition views to their sequential view", () => {
    const chart = buildChart("bar", "composition");
    if (chart.analytics) {
      chart.analytics.grounding.related_views = { panels: [] };
    }
    render(<>{renderCanvasChart(chart)}</>);
    expect(screen.getByText("Mocked CompositionView")).toBeInTheDocument();
  });

  it("routes a plain sankey (not prediction) to PlotlyChartView (catch-all)", () => {
    render(<>{renderCanvasChart(buildChart("sankey"))}</>);
    expect(screen.getByText("Mocked PlotlyChartView")).toBeInTheDocument();
  });

  it("routes any other chart_type to PlotlyChartView (catch-all)", () => {
    render(<>{renderCanvasChart(buildChart("bar"))}</>);
    expect(screen.getByText("Mocked PlotlyChartView")).toBeInTheDocument();
  });

  it("routes charts with no analytics at all to PlotlyChartView (catch-all)", () => {
    render(<>{renderCanvasChart(buildChart(undefined))}</>);
    expect(screen.getByText("Mocked PlotlyChartView")).toBeInTheDocument();
  });
});
