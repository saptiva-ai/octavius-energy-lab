import { render, screen, within } from "@testing-library/react";
import type { ChartData } from "@/lib/types";
import { ReliabilityView } from "../ReliabilityView";

function buildChart(
  rows: Array<Record<string, unknown>>,
  configuredTarget = false,
): ChartData {
  return {
    type: "chart",
    plotly_config: { data: [], layout: {} },
    analytics: {
      metric_name: "confiabilidad_inventario",
      chart_type: "bar",
      series: [],
      table_data: rows,
      response_text: "",
      visualization: {
        task: "ranking",
        title: "Confiabilidad de inventario",
        target_status: configuredTarget ? "configured" : "not_configured",
        ...(configuredTarget
          ? {
              target: {
                label: "Umbral auditado",
                value: 90,
                source: "Política operativa",
                version: "v1",
              },
            }
          : {}),
      },
      grounding: {
        source: "retail-advisor",
        capability: "inventory_reliability",
        formula_status: "draft",
        formula: "AVG(auditoria_faltante.confiabilidad_pct)",
        caveats: ["La fórmula de origen debe confirmarse con el cliente."],
        staleness_max_age_days: 31,
      },
      error: null,
      schema_version: "1",
      data_as_of: "2026-07-20",
      freshness: "monthly",
    },
  };
}

describe("ReliabilityView", () => {
  it("separa valor, muestra, cobertura, fecha y caveat draft", () => {
    render(
      <ReliabilityView
        chart={buildChart([
          {
            label: "Bebidas",
            value: 92,
            audit_count: 4,
            sample_size: 4,
            audited_skus: 3,
            eligible_skus: 5,
            sample_coverage_pct: 60,
            last_audit_date: "2026-07-20",
            audit_age_days: 11,
            estado_evidencia: "observada",
            prioridad: 1,
          },
        ])}
      />,
    );

    expect(
      screen.getByText(/fórmula de origen debe confirmarse/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/sin umbral configurado/i)).toBeInTheDocument();
    expect(screen.getByText("92.0%")).toBeInTheDocument();
    expect(screen.getByText("4 auditorías")).toBeInTheDocument();
    expect(screen.getByText(/3 de 5 SKU.*60.0%/i)).toBeInTheDocument();
    expect(
      screen.getByText(/última auditoría: 20 jul 2026/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "92",
    );
  });

  it("muestra umbral con procedencia y ausencia como sin evidencia", () => {
    render(
      <ReliabilityView
        chart={buildChart(
          [
            {
              label: "Bajo umbral",
              value: 84,
              audit_count: 2,
              sample_size: 2,
              audited_skus: 2,
              eligible_skus: 5,
              sample_coverage_pct: 40,
              last_audit_date: "2026-07-20",
              estado_evidencia: "bajo_umbral",
              prioridad: 1,
              delta_to_target: -6,
            },
            {
              label: "Sin auditoría",
              value: null,
              audit_count: 0,
              sample_size: 0,
              audited_skus: 0,
              eligible_skus: 4,
              sample_coverage_pct: 0,
              last_audit_date: null,
              estado_evidencia: "sin_evidencia",
              prioridad: 2,
            },
          ],
          true,
        )}
      />,
    );

    expect(
      screen.getByText(/umbral auditado: 90.0%.*política operativa.*v1/i),
    ).toBeInTheDocument();
    const cards = screen.getAllByTestId("reliability-card");
    expect(within(cards[0]).getByText(/-6.0 pp/i)).toBeInTheDocument();
    expect(
      within(cards[1]).getAllByText(/sin evidencia/i).length,
    ).toBeGreaterThan(0);
    expect(within(cards[1]).queryByText("0.0%")).not.toBeInTheDocument();
  });
});
