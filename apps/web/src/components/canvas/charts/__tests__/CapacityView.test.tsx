import { render, screen, within } from "@testing-library/react";
import type { ChartData } from "@/lib/types";
import { CapacityView } from "../CapacityView";

function buildChart(rows: Array<Record<string, unknown>>): ChartData {
  return {
    type: "chart",
    plotly_config: { data: [], layout: {} },
    analytics: {
      metric_name: "capacidad_anaquel",
      chart_type: "bar",
      series: [],
      table_data: rows,
      response_text: "",
      grounding: {
        source: "retail-advisor",
        capability: "shelf_capacity",
        stock_semantics: "inventario de sistema al cierre",
        capacity_freshness: "sin_fecha",
        sales_window_days: 7,
      },
      error: null,
      schema_version: "1",
      data_as_of: "2026-06-30",
      freshness: "monthly",
    },
  };
}

describe("CapacityView", () => {
  it("muestra utilización, cobertura y acción como conceptos separados", () => {
    render(
      <CapacityView
        chart={buildChart([
          {
            articulo_id: "SKU001",
            label: "Refresco cola 600ml",
            prioridad: 1,
            capacidad_unidades: 60,
            stock_sistema: 30,
            utilizacion_pct: 50,
            venta_diaria: 15,
            cobertura_dias: 2,
            estado: "normal",
            accion_recomendada: "Monitorear",
          },
        ])}
      />,
    );

    expect(
      screen.getByText(/inventario de sistema al cierre/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/capacidad sin fecha verificable/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "50",
    );
    expect(screen.getByText("30 de 60 unidades (50.0%)")).toBeInTheDocument();
    expect(screen.getByText("2.0 días de venta")).toBeInTheDocument();
    expect(screen.getByText("15.0 unidades/día")).toBeInTheDocument();
    expect(screen.getByText("Monitorear")).toBeInTheDocument();
  });

  it("no recorta sobrecapacidad y distingue capacidad ausente", () => {
    render(
      <CapacityView
        chart={buildChart([
          {
            articulo_id: "SOBRE",
            label: "Producto sobre capacidad",
            prioridad: 1,
            capacidad_unidades: 40,
            stock_sistema: 50,
            utilizacion_pct: 125,
            estado: "sobrecapacidad",
            accion_recomendada: "Contar físicamente y validar capacidad",
          },
          {
            articulo_id: "SIN",
            label: "Producto sin capacidad",
            prioridad: 2,
            capacidad_unidades: null,
            stock_sistema: 12,
            utilizacion_pct: null,
            estado: "capacidad_no_verificable",
            accion_recomendada: "Auditar capacidad de anaquel",
          },
        ])}
      />,
    );

    const cards = screen.getAllByTestId("capacity-card");
    expect(within(cards[0]).getAllByText(/125.0%/)).toHaveLength(2);
    expect(
      within(cards[0]).getByText(/excede la capacidad/i),
    ).toBeInTheDocument();
    expect(
      within(cards[1]).getByText(/capacidad no disponible/i),
    ).toBeInTheDocument();
  });
});
