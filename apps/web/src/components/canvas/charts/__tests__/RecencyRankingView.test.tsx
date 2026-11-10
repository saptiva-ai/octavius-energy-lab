import { render, screen, within } from "@testing-library/react";
import type { ChartData } from "@/lib/types";
import { RecencyRankingView } from "../RecencyRankingView";

function buildChart(
  rows: Array<Record<string, unknown>>,
  configuredTarget = true,
): ChartData {
  return {
    type: "chart",
    plotly_config: { data: [], layout: {} },
    analytics: {
      metric_name: "dias_sin_venta",
      chart_type: "bar",
      series: [],
      table_data: rows,
      response_text: "",
      visualization: {
        task: "ranking",
        title: "Días sin venta",
        higher_is_better: false,
        target_status: configuredTarget ? "configured" : "not_configured",
        ...(configuredTarget
          ? {
              target: {
                label: "Umbral de revisión",
                value: 4,
                source: "Configuración operativa",
                version: "v1",
              },
            }
          : {}),
      },
      grounding: {
        source: "retail-advisor",
        capability: "sales_recency",
        tail_omitted: 2,
        pareto_status: "omitted_no_additive_measure",
        caveats: [
          "Es recencia desde la última venta observada.",
          "No confirma faltante físico.",
        ],
      },
      error: null,
      schema_version: "1",
      data_as_of: "2026-06-30",
      freshness: "day_closed",
    },
  };
}

describe("RecencyRankingView", () => {
  it("muestra ranking horizontal peor primero, umbral y cola omitida", () => {
    render(
      <RecencyRankingView
        chart={buildChart([
          {
            label:
              "Nombre de producto deliberadamente largo para validar lectura completa",
            articulo_id: "SKU2",
            value: 12,
            estado_recencia: "revisar",
            delta_to_threshold: 8,
            prioridad: 1,
          },
          {
            label: "Producto reciente",
            articulo_id: "SKU1",
            value: 2,
            estado_recencia: "monitorear",
            delta_to_threshold: -2,
            prioridad: 2,
          },
        ])}
      />,
    );

    expect(
      screen.getByText(
        "Nombre de producto deliberadamente largo para validar lectura completa",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /umbral de revisión: 4 días.*configuración operativa.*v1/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no confirma faltante físico/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/2 SKU adicionales fuera del top/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Pareto omitido.*no son una magnitud aditiva/i),
    ).toBeInTheDocument();

    const bars = screen.getAllByRole("progressbar");
    expect(bars[0]).toHaveAttribute("aria-valuenow", "12");
    expect(bars[0]).toHaveAttribute(
      "aria-label",
      expect.stringMatching(/12 días.*umbral 4/i),
    );
    const cards = screen.getAllByTestId("recency-row");
    expect(within(cards[0]).getByText("Investigar")).toBeInTheDocument();
    expect(within(cards[1]).getByText("Monitorear")).toBeInTheDocument();
  });

  it("sin procedencia no dibuja una referencia inventada", () => {
    render(
      <RecencyRankingView
        chart={buildChart(
          [
            {
              label: "Producto",
              value: 7,
              estado_recencia: "descriptiva",
              prioridad: 1,
            },
          ],
          false,
        )}
      />,
    );

    expect(screen.getByText(/sin umbral configurado/i)).toBeInTheDocument();
    expect(screen.queryByText(/Fuente:/i)).not.toBeInTheDocument();
  });
});
