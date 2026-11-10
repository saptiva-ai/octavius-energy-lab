/**
 * Equipo (2026-10-21): al cerrar la gráfica con la X desaparecía y no había
 * forma de volver a verla ni de regresar a las de mensajes anteriores. Cada
 * respuesta con gráfica lleva un botón que la vuelve a abrir en el panel.
 */
import { fireEvent, render, screen } from "@testing-library/react";

import { ChatMessage } from "../ChatMessage";
import { useCanvasStore } from "@/lib/stores/canvas-store";

jest.mock("../StreamingMessage", () => ({
  StreamingMessage: ({ content }: { content: string }) => <div>{content}</div>,
}));

const ANALYTICS = {
  metric_name: "venta_hora",
  chart_type: "bar",
  series: [
    {
      name: "Venta",
      points: [
        { label: "Polanco", value: 782847, dimension: null },
        { label: "Mundo E", value: 375403, dimension: null },
      ],
    },
  ],
  table_data: [],
  response_text: "Venta por tienda.",
  grounding: { source: "retail-advisor", unit: "count" },
  error: null,
  schema_version: "1",
  data_as_of: "2026-09-30",
  freshness: "day_closed",
  visualization: { title: "Venta por tienda", task: "ranking" },
};

beforeEach(() => {
  useCanvasStore.getState().reset();
});

describe("ChatMessage · volver a ver la gráfica", () => {
  it("una respuesta con gráfica lleva el botón y al pulsarlo la abre en el panel", () => {
    render(
      <ChatMessage
        id="msg-grafica"
        role="assistant"
        content="Venta por tienda."
        metadata={{ retail_analytics: ANALYTICS } as never}
      />,
    );
    const boton = screen.getByRole("button", { name: /ver gráfica/i });
    expect(boton).toHaveTextContent("Venta por tienda");

    fireEvent.click(boton);
    const estado = useCanvasStore.getState();
    expect(estado.isSidebarOpen).toBe(true);
    expect(estado.activeMessageId).toBe("msg-grafica");
    expect(estado.activeChart?.title).toBe("Venta por tienda");
  });

  it("vuelve a abrirla después de cerrar el panel con la X", () => {
    render(
      <ChatMessage
        id="msg-grafica"
        role="assistant"
        content="Venta por tienda."
        metadata={{ retail_analytics: ANALYTICS } as never}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /ver gráfica/i }));
    useCanvasStore.getState().toggleSidebar();
    expect(useCanvasStore.getState().isSidebarOpen).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /ver gráfica/i }));
    expect(useCanvasStore.getState().isSidebarOpen).toBe(true);
    expect(useCanvasStore.getState().activeMessageId).toBe("msg-grafica");
  });

  it("una respuesta sin gráfica no lleva el botón", () => {
    render(<ChatMessage id="msg-texto" role="assistant" content="Hola" />);
    expect(screen.queryByRole("button", { name: /ver gráfica/i })).toBeNull();
  });

  it("una gráfica que ya es la abierta se marca como tal", () => {
    render(
      <ChatMessage
        id="msg-grafica"
        role="assistant"
        content="Venta por tienda."
        metadata={{ retail_analytics: ANALYTICS } as never}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /ver gráfica/i }));
    expect(screen.getByRole("button", { name: /ver gráfica/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
