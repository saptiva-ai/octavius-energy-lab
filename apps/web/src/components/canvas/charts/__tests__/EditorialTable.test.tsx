import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ChartData } from "@/lib/types";
import { EditorialTable } from "../EditorialTable";

function buildChart(rows: Array<Record<string, unknown>>): ChartData {
  return {
    type: "chart",
    plotly_config: { data: [], layout: {} },
    analytics: {
      metric_name: "consulta_exploratoria",
      chart_type: "table",
      series: [],
      table_data: rows,
      response_text: "Respuesta EXPLORATORIA.",
      visualization: {
        task: "table",
        title: "Resultado exploratorio",
      },
      grounding: {
        source: "retail-advisor",
        capability: "exploration",
        table_contract: {
          columns: [
            {
              key: "fecha",
              label: "Fecha",
              data_type: "date",
              unit: null,
              format: "date",
              align: "left",
              role: "time",
              nullable: false,
            },
            {
              key: "importe_pesos",
              label: "Venta",
              data_type: "number",
              unit: "MXN",
              format: "currency_mxn",
              align: "right",
              role: "measure",
              nullable: false,
            },
            {
              key: "porcentaje",
              label: "Participación",
              data_type: "number",
              unit: "%",
              format: "percent",
              align: "right",
              role: "measure",
              nullable: true,
            },
            {
              key: "unidades",
              label: "Unidades",
              data_type: "number",
              unit: "unidades",
              format: "integer",
              align: "right",
              role: "measure",
              nullable: false,
            },
            {
              key: "detalle_x",
              label: "Detalle x",
              data_type: "text",
              unit: null,
              format: "text",
              align: "left",
              role: "unknown",
              nullable: false,
            },
          ],
          observation: "La primera fila responde la pregunta.",
          primary_row_indices: [0],
          primary_columns: ["importe_pesos"],
          order: {
            status: "query_order",
            label: "Orden devuelto por la consulta",
          },
          pagination: {
            page_size: 25,
            returned_rows: rows.length,
            total_rows: rows.length,
            truncated: false,
          },
          visualization_recommendation: {
            status: "validated",
            shape: "line",
            x: "fecha",
            y: ["importe_pesos"],
            reason: "roles y tipos de columna validados",
          },
        },
        exploratory: {
          supuestos: ["Periodo solicitado por el usuario"],
          caveats: ["No es una métrica validada del catálogo"],
        },
      },
      error: null,
      schema_version: "1",
      data_as_of: "2026-06-30",
      freshness: "day_closed",
    },
  };
}

describe("EditorialTable", () => {
  it("formatea, contextualiza, resalta evidencia y pagina", () => {
    const rows = Array.from({ length: 27 }, (_, index) => ({
      fecha: `2026-06-${String((index % 30) + 1).padStart(2, "0")}`,
      importe_pesos: index === 0 ? 1234.5 : index * 10,
      porcentaje: index === 0 ? 82.5 : null,
      unidades: index === 0 ? 1200 : index,
      detalle_x: `fila ${index + 1}`,
    }));
    render(<EditorialTable chart={buildChart(rows)} />);

    expect(
      screen.getByText("La primera fila responde la pregunta."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Respuesta principal: fila 1/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Fuente: retail-advisor/i)).toBeInTheDocument();
    expect(screen.getByText(/Corte: 2026-06-30/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Orden devuelto por la consulta/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Periodo solicitado/i)).toBeInTheDocument();
    expect(screen.getByText(/No es una métrica validada/i)).toBeInTheDocument();
    expect(screen.getByText(/Gráfica sugerida: línea/i)).toBeInTheDocument();
    expect(screen.getByText("MXN")).toBeInTheDocument();

    const firstRow = screen.getByTestId("editorial-row-0");
    expect(firstRow).toHaveAttribute("data-primary", "true");
    expect(firstRow).toHaveAccessibleName("Respuesta principal");
    expect(within(firstRow).getByText("$1,234.50")).toBeInTheDocument();
    expect(within(firstRow).getByText("82.5%")).toBeInTheDocument();
    expect(within(firstRow).getByText("1,200")).toBeInTheDocument();
    expect(screen.getAllByText("Sin dato").length).toBeGreaterThan(0);
    expect(screen.queryByText("fila 26")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /siguiente/i }));
    expect(screen.getByText("fila 26")).toBeInTheDocument();
    expect(screen.queryByText("fila 1")).not.toBeInTheDocument();
    expect(screen.getByText(/Página 2 de 2/i)).toBeInTheDocument();
  });

  it("sin contrato conserva fallback seguro para columnas desconocidas", () => {
    const chart = buildChart([{ codigo_raro: "A-1", valor_raro: 12.34 }]);
    if (chart.analytics) delete chart.analytics.grounding.table_contract;

    render(<EditorialTable chart={chart} />);

    expect(screen.getByText("Codigo raro")).toBeInTheDocument();
    expect(screen.getByText("Valor raro")).toBeInTheDocument();
    expect(screen.getByText("A-1")).toBeInTheDocument();
    expect(screen.getByText("12.34")).toBeInTheDocument();
    expect(screen.getByText(/Vista segura: tabla/i)).toBeInTheDocument();
  });
});
