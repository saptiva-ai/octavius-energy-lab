import { render, screen, within } from "@testing-library/react";
import type { ChartData } from "@/lib/types";
import { PredictionList } from "../PredictionList";

jest.mock("../ChartNarration", () => ({
  ChartNarration: () => null,
}));

function predictionRow(overrides: Record<string, unknown> = {}) {
  return {
    articulo_id: "SKU001",
    nombre: "Agua natural 1L",
    es_top_seller: false,
    stock_cierre: 8,
    venta_diaria: 20,
    cobertura_dias: 0.4,
    capacidad_unidades: 40,
    prioridad: 1,
    urgencia: "alta",
    accion_recomendada: "Resurtir ahora",
    ...overrides,
  };
}

function buildChart(rows: Array<Record<string, unknown>>): ChartData {
  return {
    type: "chart",
    plotly_config: { data: [], layout: {} },
    analytics: {
      metric_name: "prediccion_faltante",
      chart_type: rows.length > 0 ? "table" : "none",
      series: [],
      table_data: rows,
      response_text: "",
      grounding: {
        source: "retail-advisor",
        capability: "prediction",
        ventana_dias: 7,
      },
      error: null,
      schema_version: "1",
      data_as_of: "2026-07-30",
      freshness: "day_closed",
      visualization: {
        task: "ranking",
        title: "Prioridad de resurtido",
      },
    },
  };
}

describe("PredictionList", () => {
  it("CA-01 ordena por prioridad y resume urgencias", () => {
    render(
      <PredictionList
        chart={buildChart([
          predictionRow({
            articulo_id: "SKU_BAJA",
            nombre: "Producto preventivo",
            prioridad: 3,
            urgencia: "baja",
            cobertura_dias: 1.2,
          }),
          predictionRow({
            articulo_id: "SKU_MEDIA",
            nombre: "Producto para hoy",
            prioridad: 2,
            urgencia: "media",
            cobertura_dias: 0.7,
          }),
          predictionRow({
            articulo_id: "SKU_ALTA",
            nombre: "Producto inmediato",
            prioridad: 1,
          }),
        ])}
      />,
    );

    const cards = screen.getAllByTestId("prediction-card");
    expect(
      within(cards[0]).getByText("Producto inmediato"),
    ).toBeInTheDocument();
    expect(within(cards[1]).getByText("Producto para hoy")).toBeInTheDocument();
    expect(screen.getByText("Alta 1")).toBeInTheDocument();
    expect(screen.getByText("Media 1")).toBeInTheDocument();
    expect(screen.getByText("Baja 1")).toBeInTheDocument();
  });

  it("CA-02 separa dato observado, estimación y recomendación", () => {
    render(<PredictionList chart={buildChart([predictionRow()])} />);

    expect(screen.getByText("Prioridad 1")).toBeInTheDocument();
    expect(screen.getByText("Dato observado")).toBeInTheDocument();
    expect(screen.getByText("8 unidades al cierre")).toBeInTheDocument();
    expect(screen.getByText("Cobertura estimada")).toBeInTheDocument();
    expect(screen.getByText("0.4 días de venta")).toBeInTheDocument();
    expect(
      screen.getByText("Siguiente acción recomendada"),
    ).toBeInTheDocument();
    expect(screen.getByText("Resurtir ahora")).toBeInTheDocument();
    expect(
      screen.getByText(
        /stock al cierre ÷ promedio diario de venta de los últimos 7 días/i,
      ),
    ).toBeInTheDocument();
  });

  it("CA-03 etiqueta el nivel de llenado sin usarlo como urgencia", () => {
    render(<PredictionList chart={buildChart([predictionRow()])} />);

    expect(screen.getByText("Nivel de llenado")).toBeInTheDocument();
    expect(screen.getByText("8 de 40 unidades (20%)")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "Nivel de llenado de Agua natural 1L",
      }),
    ).toHaveAttribute("aria-valuenow", "20");
    expect(screen.getByText("Urgencia alta")).toBeInTheDocument();
  });

  it("CA-05 no inventa llenado cuando la capacidad no está disponible", () => {
    render(
      <PredictionList
        chart={buildChart([
          predictionRow({
            capacidad_unidades: null,
          }),
        ])}
      />,
    );

    expect(screen.getByText("Capacidad no disponible")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("mantiene un estado vacío explícito", () => {
    render(<PredictionList chart={buildChart([])} />);

    expect(
      screen.getByText("Sin artículos en riesgo de faltante."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Alta 0")).not.toBeInTheDocument();
  });
});
