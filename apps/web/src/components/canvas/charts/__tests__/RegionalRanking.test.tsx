import { render, screen } from "@testing-library/react";
import { RegionalRanking } from "../RegionalRanking";

describe("RegionalRanking", () => {
  it("ordena peor primero y distingue cero de regiones sin dato", () => {
    render(
      <RegionalRanking
        rows={[
          { label: "Yucatán", value: 0, numerator: 0, denominator: 20 },
          { label: "Jalisco", value: 10, numerator: 10, denominator: 100 },
        ]}
      />,
    );

    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Jalisco");
    expect(items[0]).toHaveTextContent("10.0%");
    expect(items[0]).toHaveTextContent("10 / 100");
    expect(items[1]).toHaveTextContent("Yucatán");
    expect(screen.getByText(/gris: sin datos/i)).toBeInTheDocument();
  });
});
