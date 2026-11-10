import { render, screen } from "@testing-library/react";
import type { ChartData } from "@/lib/types";
import { PredictionView } from "../PredictionView";

jest.mock("../PredictionList", () => ({
  PredictionList: () => <div>Lista priorizada</div>,
}));
jest.mock("../PlotlyChartView", () => ({
  PlotlyChartView: () => <div>Sankey de predicción</div>,
}));

const chart: ChartData = {
  type: "chart",
  plotly_config: { data: [], layout: {} },
};

describe("PredictionView", () => {
  it("CA-01 presenta la lista priorizada como única vista inicial", () => {
    render(<PredictionView chart={chart} />);

    expect(screen.getByText("Lista priorizada")).toBeInTheDocument();
    expect(screen.queryByText("Sankey de predicción")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Sankey" }),
    ).not.toBeInTheDocument();
  });
});
