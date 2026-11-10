import { render, screen } from "@testing-library/react";
import type { ChartData } from "@/lib/types";
import { IntradayContextPanel } from "../IntradayContextPanel";

function buildChart(
  grounding: Record<string, unknown>,
  benchmark = true,
): ChartData {
  return {
    type: "chart",
    plotly_config: { data: [], layout: {} },
    analytics: {
      metric_name: "venta_hora",
      chart_type: "line",
      series: [],
      table_data: [],
      response_text: "",
      visualization: {
        task: "trend",
        title: "Venta por hora",
        headline: "Mundo E va arriba",
        ...(benchmark
          ? {
              benchmark: {
                label: "Mismo día de semana anterior",
                value: 100,
                source: "ventas_hora",
                version: "1",
              },
            }
          : {}),
      },
      grounding: {
        source: "retail-advisor",
        capability: "intraday_sales",
        unit: "count",
        timezone: "America/Mexico_City",
        cutoff_hour: 14,
        partial_hour: 14,
        future_hours: [15, 16, 17],
        comparison_status: benchmark
          ? "configured"
          : "unavailable_no_benchmark",
        actual_cumulative: 120,
        benchmark_cumulative: benchmark ? 100 : null,
        delta_absolute: benchmark ? 20 : null,
        delta_percent: benchmark ? 20 : null,
        missing_actual_hours: [],
        missing_benchmark_hours: [],
        ...grounding,
      },
      error: null,
      schema_version: "1",
      data_as_of: "2026-07-31",
      freshness: "intraday",
    },
  };
}

describe("IntradayContextPanel", () => {
  it("explica corte, parcial, futuro y delta acumulado", () => {
    render(<IntradayContextPanel chart={buildChart({})} />);

    expect(screen.getByText(/corte 14:00/i)).toBeInTheDocument();
    expect(screen.getByText(/120 unidades acumuladas/i)).toBeInTheDocument();
    expect(screen.getByText(/\+20 unidades/i)).toBeInTheDocument();
    expect(screen.getByText(/\+20.0%/i)).toBeInTheDocument();
    expect(screen.getByText(/hora 14:00 parcial/i)).toBeInTheDocument();
    expect(screen.getByText(/15:00-17:00 futuras/i)).toBeInTheDocument();
    expect(
      screen.getByText(/las horas sin fila no se convierten en cero/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/America\/Mexico_City/i)).toBeInTheDocument();
  });

  it("sin comparable válido presenta tendencia descriptiva", () => {
    render(
      <IntradayContextPanel
        chart={buildChart(
          {
            comparison_status: "unavailable_incomplete_alignment",
            missing_actual_hours: [11],
            missing_benchmark_hours: [],
          },
          false,
        )}
      />,
    );

    expect(screen.getByText(/tendencia descriptiva/i)).toBeInTheDocument();
    expect(screen.getByText(/hora 11:00 sin observación/i)).toBeInTheDocument();
    expect(screen.queryByText(/\+20.0%/i)).not.toBeInTheDocument();
  });
});
