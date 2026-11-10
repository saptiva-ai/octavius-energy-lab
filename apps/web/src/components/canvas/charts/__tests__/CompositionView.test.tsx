import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ChartData } from "@/lib/types";
import { CompositionView, relatedViewsCsv } from "../CompositionView";

function buildChart(partial = false): ChartData {
  return {
    type: "chart",
    title: "Venta",
    plotly_config: { data: [], layout: {} },
    analytics: {
      metric_name: "venta_hora",
      chart_type: "bar",
      series: [],
      table_data: [],
      response_text:
        "Descomposición observacional: muestra concentración, no una causa.",
      grounding: {
        source: "retail-advisor",
        capability: "composition",
        related_views: {
          version: "1",
          status: partial ? "partial" : "complete",
          reading: "observational_not_causal",
          focus_panel_id: "p1",
          stop_reason: partial ? "presupuesto_agotado" : "completado",
          shared_context: {
            metric_id: "venta_hora",
            metric_label: "Venta",
            unit: "currency",
            period: "2026-06-24..2026-06-30",
            filters: { categoria: "refrescos" },
            data_as_of: "2026-06-30",
          },
          unlinked_contradictions: [],
          panels: [
            {
              id: "p1",
              sequence: 1,
              title: "Magnitud y tendencia",
              status: "ready",
              visual: "line",
              metric_id: "venta_hora",
              metric_label: "Venta",
              unit: "currency",
              period: "2026-06-24..2026-06-30",
              filters: { categoria: "refrescos" },
              data_as_of: "2026-06-30",
              dimension: null,
              finding: "Venta total: 200 MXN.",
              contradictions: [],
              state_message: null,
              rows: [
                { label: "2026-06-29", value: 90, dimension: null },
                { label: "2026-06-30", value: 110, dimension: null },
              ],
            },
            {
              id: "p2",
              sequence: 2,
              title: "Concentración regional",
              status: "ready",
              visual: "horizontal_bar",
              metric_id: "venta_hora",
              metric_label: "Venta",
              unit: "currency",
              period: "2026-06-24..2026-06-30",
              filters: { categoria: "refrescos" },
              data_as_of: "2026-06-30",
              dimension: "region",
              finding: "Norte concentra 150 MXN.",
              contradictions: [
                "La partición regional difiere del total observado.",
              ],
              state_message: null,
              rows: [
                { label: "Norte", value: 150, dimension: "region" },
                { label: "Sur", value: 50, dimension: "region" },
              ],
            },
            {
              id: "p3",
              sequence: 3,
              title: "Tiendas con mayor venta",
              status: "ready",
              visual: "horizontal_bar",
              metric_id: "venta_hora",
              metric_label: "Venta",
              unit: "currency",
              period: "2026-06-24..2026-06-30",
              filters: { categoria: "refrescos" },
              data_as_of: "2026-06-30",
              dimension: "tienda",
              finding: "Mundo E encabeza el ranking.",
              contradictions: [],
              state_message: null,
              rows: [{ label: "Mundo E", value: 80, dimension: "tienda" }],
            },
            {
              id: "p4",
              sequence: 4,
              title: "Categorías en tienda top",
              status: partial ? "not_run" : "ready",
              visual: "horizontal_bar",
              metric_id: "venta_hora",
              metric_label: "Venta",
              unit: "currency",
              period: "2026-06-24..2026-06-30",
              filters: { categoria: "refrescos" },
              data_as_of: "2026-06-30",
              dimension: "categoria",
              finding: partial ? null : "Refrescos encabeza el ranking.",
              contradictions: [],
              state_message: partial
                ? "No se ejecutó: presupuesto agotado."
                : null,
              rows: partial
                ? []
                : [
                    {
                      label: "Refrescos",
                      value: 40,
                      dimension: "categoria",
                    },
                  ],
            },
          ],
        },
      },
      error: null,
      schema_version: "1",
      data_as_of: "2026-06-30",
      freshness: "day_closed",
    },
  };
}

describe("CompositionView", () => {
  it("presenta una secuencia total a categoría con contexto único", () => {
    render(<CompositionView chart={buildChart()} />);

    expect(
      screen.getByRole("region", { name: /recorrido analítico/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/lectura observacional/i)).toBeInTheDocument();
    expect(screen.getByText(/no demuestra causalidad/i)).toBeInTheDocument();
    expect(screen.getAllByText(/2026-06-24.*2026-06-30/i)).toHaveLength(2);
    expect(screen.getByText(/Categoría: refrescos/i)).toBeInTheDocument();
    expect(screen.getByText("Venta total: 200 MXN.")).toBeInTheDocument();
    expect(screen.getAllByTitle("Exportar CSV")).toHaveLength(1);
    expect(
      screen.getByRole("navigation", { name: /niveles del recorrido/i }),
    ).toHaveClass("overflow-x-auto");

    fireEvent.click(screen.getByRole("button", { name: /2.*región/i }));
    expect(screen.getByText("Norte concentra 150 MXN.")).toBeInTheDocument();
    expect(screen.getByText(/partición regional difiere/i)).toBeInTheDocument();
    expect(screen.getAllByText("Norte")).toHaveLength(2);
    expect(screen.getAllByText("$150.00")).toHaveLength(2);

    const table = screen.getByRole("table", { name: /datos del panel/i });
    expect(within(table).getByText("Sur")).toBeInTheDocument();
  });

  it("un panel no ejecutado no elimina los resultados anteriores", () => {
    render(<CompositionView chart={buildChart(true)} />);

    expect(screen.getByText("Venta total: 200 MXN.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^\d/ })).toHaveLength(4);

    fireEvent.click(screen.getByRole("button", { name: /4.*categoría/i }));
    expect(
      screen.getByText(/No se ejecutó: presupuesto agotado/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /1.*total/i }),
    ).toBeInTheDocument();
  });

  it("exporta todos los paneles listos con su contexto", () => {
    const chart = buildChart();
    const related = chart.analytics?.grounding.related_views;
    const csv = relatedViewsCsv(related);

    expect(csv).toContain('"panel_id","panel"');
    expect(csv).toContain('"p1","Magnitud y tendencia"');
    expect(csv).toContain('"p2","Concentración regional"');
    expect(csv).toContain('"2026-06-24..2026-06-30"');
    expect(csv).toContain('"categoria=refrescos"');
    expect(csv).toContain('"currency"');
  });
});
