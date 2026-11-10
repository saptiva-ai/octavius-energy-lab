import { render, screen, waitFor } from "@testing-library/react";
import type { ChartData } from "@/lib/types";
import { PlotlyChartView } from "../PlotlyChartView";

jest.mock("next/dynamic", () => () => {
  const Plot = ({
    data,
    onInitialized,
  }: {
    data?: unknown[];
    onInitialized?: (figura: unknown, div: HTMLElement) => void;
  }) => {
    const React = jest.requireActual("react");
    const ref = React.useRef(null);
    React.useEffect(() => {
      if (ref.current) onInitialized?.({}, ref.current);
    }, [onInitialized]);
    // Plotly montado con el panel cerrado: dibujó a su ancho por omisión.
    return (
      <div ref={ref} data-testid="plot" data-figura={JSON.stringify(data ?? [])}>
        Gráfica
        <svg className="main-svg" width="700" />
      </div>
    );
  };
  return Plot;
});
jest.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "light" }) }));
// react-markdown es ESM y jest no lo transforma; el texto basta.
jest.mock("../ChartNarration", () => ({
  ChartNarration: ({ text }: { text: string }) => <p>{text}</p>,
}));

const TEXTO = "Tasa de quiebre probable por categoría, septiembre de 2026.";

function chart(data: unknown[]): ChartData {
  return {
    type: "chart",
    title: "Quiebre contra venta",
    plotly_config: { data, layout: {} },
    response_text: TEXTO,
  } as ChartData;
}

describe("PlotlyChartView", () => {
  // Equipo (2026-10-22): agosto contra septiembre y las ventas por categoría
  // salían con todas las barras en teal. Con una sola serie, cada barra lleva
  // su color de la paleta del tema.
  // GRA-2 (2026-11-08): un solo tono y la barra mayor en el teal de la marca.
  it("una sola serie de barras llega a Plotly con un color de la paleta por barra", () => {
    render(
      <PlotlyChartView
        chart={chart([{ type: "bar", x: ["agosto", "septiembre"], y: [205, 215] }])}
      />,
    );

    const [barra] = JSON.parse(
      screen.getByTestId("plot").getAttribute("data-figura") ?? "[]",
    );
    expect(barra.marker.color).toEqual(["#0f8a76", "#eb6834"]);
  });

  // Equipo (2026-10-21): el texto del plugin debajo de la gráfica repetía lo
  // que el chat ya narra y ocupaba medio panel. La gráfica va sola.
  it("no repite el texto de la respuesta debajo de la gráfica", () => {
    render(<PlotlyChartView chart={chart([{ type: "bar", x: ["a"], y: [1] }])} />);

    expect(screen.getByText("Gráfica")).toBeInTheDocument();
    expect(screen.queryByText(TEXTO)).not.toBeInTheDocument();
  });

  // Equipo (2026-10-21): al reabrir la gráfica desde "Ver gráfica", Plotly
  // medía el panel mientras todavía se acomodaba y la barra de la derecha
  // quedaba cortada. Plotly solo escucha el resize de la ventana.
  it("se reajusta cuando su contenedor ya no mide lo que Plotly dibujó", async () => {
    let avisar: ResizeObserverCallback = () => undefined;
    const original = global.ResizeObserver;
    global.ResizeObserver = class {
      constructor(cb: ResizeObserverCallback) {
        avisar = cb;
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
    const redimensionar = jest.fn();
    window.addEventListener("resize", redimensionar);
    const medida = (width: number) =>
      [{ contentRect: { width } }] as unknown as ResizeObserverEntry[];

    try {
      render(<PlotlyChartView chart={chart([{ type: "bar", x: ["a"], y: [1] }])} />);

      avisar(medida(700), {} as ResizeObserver);
      await new Promise((r) => requestAnimationFrame(r));
      expect(redimensionar).not.toHaveBeenCalled();

      avisar(medida(463), {} as ResizeObserver);
      await waitFor(() => expect(redimensionar).toHaveBeenCalledTimes(1));
    } finally {
      window.removeEventListener("resize", redimensionar);
      global.ResizeObserver = original;
    }
  });

  it("sin nada que graficar ni tabla, el texto sigue siendo el contenido", () => {
    render(<PlotlyChartView chart={chart([])} />);

    expect(screen.getByText(TEXTO)).toBeInTheDocument();
  });
});
