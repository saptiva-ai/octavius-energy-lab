import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ChartData } from "@/lib/types";
import { AlertCards } from "../AlertCards";

jest.mock("../ChartNarration", () => ({
  ChartNarration: () => null,
}));

function buildChart(rows: Array<Record<string, unknown>>): ChartData {
  return {
    type: "chart",
    plotly_config: { data: [], layout: {} },
    analytics: {
      metric_name: "alertas",
      chart_type: rows.length > 0 ? "alerts" : "none",
      series: [],
      table_data: rows,
      response_text: "",
      grounding: { source: "retail-advisor", capability: "alerts" },
      error: null,
      schema_version: "1",
      data_as_of: "2026-07-30",
      freshness: "day_closed",
      visualization: {
        task: "status",
        title: "Foquitos accionables",
      },
    },
  };
}

function alertRow(overrides: Record<string, unknown> = {}) {
  return {
    tipo: "confiabilidad_sospechosa",
    severidad: "alta",
    articulo_id: "SKU002",
    nombre: "Refresco cola 2L",
    causa: "El sistema registra existencia sin venta reciente.",
    accion: "Cuenta físicamente el anaquel.",
    prioridad: 1,
    urgencia: "hoy",
    por_que_ahora: "La señal requiere verificación hoy.",
    impacto_unidades: 44,
    evidencia: [
      { label: "Sin venta", value: 12, unit: "días" },
      { label: "Existencia sistema", value: 44, unit: "unidades" },
    ],
    recomendacion_no_confirmada: true,
    datos: {},
    ...overrides,
  };
}

describe("AlertCards", () => {
  it("CA-01 ordena por prioridad y resume severidades sin ocultar el total", () => {
    render(
      <AlertCards
        chart={buildChart([
          alertRow({
            articulo_id: "SKU_MEDIA",
            nombre: "Producto medio",
            tipo: "venta_cayendo",
            severidad: "media",
            prioridad: 3,
          }),
          alertRow({
            articulo_id: "SKU_SEGUNDA",
            nombre: "Segunda prioridad",
            prioridad: 2,
          }),
          alertRow({
            articulo_id: "SKU_PRIMERA",
            nombre: "Primera prioridad",
            prioridad: 1,
          }),
        ])}
      />,
    );

    const cards = screen.getAllByTestId("alert-card");
    expect(cards).toHaveLength(3);
    expect(within(cards[0]).getByText("Primera prioridad")).toBeInTheDocument();
    expect(within(cards[1]).getByText("Segunda prioridad")).toBeInTheDocument();
    expect(screen.getByText("3 foquitos")).toBeInTheDocument();
    expect(screen.getByText("Alta 2")).toBeInTheDocument();
    expect(screen.getByText("Media 1")).toBeInTheDocument();
    expect(screen.getByText("Baja 0")).toBeInTheDocument();
  });

  it("CA-02 muestra evidencia, razón temporal y acción como recomendación", () => {
    render(<AlertCards chart={buildChart([alertRow()])} />);

    expect(screen.getByText("Prioridad 1")).toBeInTheDocument();
    expect(screen.getByText("Por qué ahora")).toBeInTheDocument();
    expect(
      screen.getByText("La señal requiere verificación hoy."),
    ).toBeInTheDocument();
    expect(screen.getByText("Sin venta: 12 días")).toBeInTheDocument();
    expect(
      screen.getByText("Existencia sistema: 44 unidades"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Siguiente acción recomendada"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/el conteo físico aún no está confirmado/i),
    ).toBeInTheDocument();
  });

  it("CA-03 filtra por tipo y mantiene visible el total original", () => {
    render(
      <AlertCards
        chart={buildChart([
          alertRow(),
          alertRow({
            articulo_id: "SKU010",
            nombre: "Agua natural",
            tipo: "riesgo_faltante",
            prioridad: 2,
            recomendacion_no_confirmada: false,
          }),
        ])}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Filtrar Riesgo de faltante" }),
    );

    expect(screen.getByText("2 foquitos")).toBeInTheDocument();
    expect(screen.getAllByTestId("alert-card")).toHaveLength(1);
    expect(screen.getByText("Agua natural")).toBeInTheDocument();
    expect(screen.queryByText("Refresco cola 2L")).not.toBeInTheDocument();
  });

  it("muestra estado vacío sin resumen engañoso", () => {
    render(<AlertCards chart={buildChart([])} />);

    expect(screen.getByText("0 foquitos")).toBeInTheDocument();
    expect(screen.getByText("Sin foquitos detectados.")).toBeInTheDocument();
    expect(screen.queryByText("Alta 0")).not.toBeInTheDocument();
  });

  it("mantiene prioridad y scroll en una lista larga", () => {
    const rows = Array.from({ length: 12 }, (_, index) =>
      alertRow({
        articulo_id: `SKU_${index}`,
        nombre: `Producto ${index}`,
        prioridad: 12 - index,
      }),
    );

    render(<AlertCards chart={buildChart(rows)} />);

    const cards = screen.getAllByTestId("alert-card");
    expect(cards).toHaveLength(12);
    expect(within(cards[0]).getByText("Producto 11")).toBeInTheDocument();
    expect(cards[0].parentElement).toHaveClass("overflow-y-auto");
  });
});
