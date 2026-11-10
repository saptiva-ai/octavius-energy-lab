import { render, screen } from "@testing-library/react";
import { StoreComparisonSummary } from "../StoreComparisonSummary";

describe("StoreComparisonSummary", () => {
  it("muestra magnitud, porcentaje, unidad, periodo y nombres", () => {
    render(
      <StoreComparisonSummary
        rows={[
          {
            label: "Control Norte",
            value: 100,
            comparison_role: "control",
          },
          {
            label: "Mundo E",
            value: 110,
            comparison_role: "focus",
            delta_absolute: 10,
            delta_percent: 10,
            delta_denominator: 100,
          },
        ]}
        unit="count"
        period="last_7_days"
      />,
    );

    expect(screen.getByText("Mundo E")).toBeInTheDocument();
    expect(screen.getByText(/vs Control Norte/i)).toBeInTheDocument();
    expect(screen.getByText("+10 unidades")).toBeInTheDocument();
    expect(screen.getByText("+10.0%")).toBeInTheDocument();
    expect(screen.getByText(/últimos 7 días/i)).toBeInTheDocument();
  });

  it("control cero declara porcentaje no disponible", () => {
    render(
      <StoreComparisonSummary
        rows={[
          { label: "Control", value: 0, comparison_role: "control" },
          {
            label: "Mundo E",
            value: 10,
            comparison_role: "focus",
            delta_absolute: 10,
            delta_percent: null,
            delta_denominator: 0,
          },
        ]}
        unit="count"
        period="today"
      />,
    );

    expect(screen.getByText(/porcentaje no disponible/i)).toBeInTheDocument();
    expect(screen.getByText(/control en cero/i)).toBeInTheDocument();
  });
});
