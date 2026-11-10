/**
 * Equipo (2026-10-21): mientras se prepara la respuesta, la burbuja dice qué
 * está haciendo según la consulta. El backend avisa qué tool eligió el decide
 * (evento `status`) y ChatView lo guarda en `metadata.espera`.
 */
import { render, screen } from "@testing-library/react";

import { ChatMessage } from "../ChatMessage";

// react-markdown es ESM y jest no lo transforma; mientras espera no se usa.
jest.mock("../MarkdownMessage", () => ({
  MarkdownMessage: ({ content }: { content: string }) => <div>{content}</div>,
}));

describe("ChatMessage · indicador de espera según la consulta", () => {
  it("antes del aviso del backend: 'Pensando'", () => {
    render(<ChatMessage id="m1" role="assistant" content="" isStreaming />);
    expect(screen.getByRole("status")).toHaveAccessibleName("Pensando");
  });

  it("con la tool elegida: frase e ícono del tema", () => {
    render(
      <ChatMessage
        id="m1"
        role="assistant"
        content=""
        isStreaming
        metadata={{
          espera: {
            fase: "consultando",
            tools: [{ tool: "retail_analytics", metrica: "faltante", dimension: null }],
          },
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveAccessibleName("Revisando inventario");
    expect(screen.getByTestId("icono-espera")).toHaveAttribute("data-tema", "inventario");
  });

  it("en cuanto llega texto, el indicador se va", () => {
    render(
      <ChatMessage
        id="m1"
        role="assistant"
        content="Polanco vendió 782,847 piezas."
        isStreaming
        metadata={{
          espera: { fase: "consultando", tools: [{ tool: "retail_analytics" }] },
        }}
      />,
    );
    expect(screen.queryByRole("status", { name: /consultando ventas/i })).toBeNull();
  });
});
