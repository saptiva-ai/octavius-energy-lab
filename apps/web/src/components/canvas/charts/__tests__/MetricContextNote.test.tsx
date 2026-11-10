import { render, screen } from "@testing-library/react";
import type { ChartData } from "@/lib/types";
import { MetricContextNote } from "../MetricContextNote";

function buildChart(configured: boolean): ChartData {
  return {
    type: "chart",
    plotly_config: { data: [], layout: {} },
    analytics: {
      metric_name: "disponibilidad",
      chart_type: "bar",
      series: [],
      table_data: [],
      response_text: "",
      error: null,
      schema_version: "1",
      data_as_of: "2026-07-30",
      freshness: "day_closed",
      grounding: {
        business_definition:
          "Proporción de registros con inventario de sistema positivo.",
        caveats: [
          "Mide inventario de sistema, no existencia física observada en anaquel.",
        ],
      },
      visualization: {
        task: "ranking",
        title: "Inventario de sistema con existencia",
        target_status: configured ? "configured" : "not_configured",
        target: configured
          ? {
              label: "Objetivo acordado",
              value: 96,
              source: "Comité operativo",
              version: "2026-Q3",
            }
          : null,
        sample_size: 300,
      },
    },
  };
}

describe("MetricContextNote", () => {
  it("muestra objetivo, fuente, versión y muestra cuando están configurados", () => {
    render(<MetricContextNote chart={buildChart(true)} />);

    expect(screen.getByText(/Objetivo acordado: 96.0%/)).toBeInTheDocument();
    expect(screen.getByText(/Comité operativo/)).toBeInTheDocument();
    expect(screen.getByText(/2026-Q3/)).toBeInTheDocument();
    expect(screen.getByText("Muestra: 300 registros")).toBeInTheDocument();
  });

  it("declara lectura descriptiva y deja accesible definición y caveat", () => {
    render(<MetricContextNote chart={buildChart(false)} />);

    expect(
      screen.getByText(/Sin meta configurada. Lectura descriptiva/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Definición y alcance")).toBeInTheDocument();
    expect(
      screen.getByText(/no existencia física observada en anaquel/i),
    ).toBeInTheDocument();
  });

  it("declara provider, horizonte, corte y limitación del forecast", () => {
    const chart = buildChart(false);
    if (!chart.analytics) throw new Error("fixture analytics requerida");
    chart.analytics.grounding = {
      capability: "demand_forecast",
      proveedor: "baseline_local",
      horizonte_dias: 7,
      forecast_cutoff: "2026-07-20",
      limitations: [
        "El proveedor no entregó un intervalo válido; se muestra el punto.",
      ],
    };

    render(<MetricContextNote chart={chart} />);

    expect(screen.getByText(/Provider: baseline_local/)).toBeInTheDocument();
    expect(screen.getByText(/Horizonte: 7 días/)).toBeInTheDocument();
    expect(screen.getByText(/Corte: 2026-07-20/)).toBeInTheDocument();
    expect(
      screen.getByText(/no entregó un intervalo válido/i),
    ).toBeInTheDocument();
  });
});
