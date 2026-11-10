/**
 * feedback round 1 (2026-10-16, punto 9): en tema claro no se veían
 * COPY ni REGENERATE porque su color era un blanco fijo (`saptiva-light`).
 * Los botones de acción toman el color de los tokens del tema.
 */
import { render, screen } from "@testing-library/react";

import { ChatMessage } from "../ChatMessage";

// El markdown (react-markdown, ESM) no es parte de lo que se prueba aquí.
jest.mock("../StreamingMessage", () => ({
  StreamingMessage: ({ content }: { content: string }) => <div>{content}</div>,
}));

describe("ChatMessage · acciones en ambos temas", () => {
  it("Copy y Regenerate usan tokens del tema, no un color fijo claro", () => {
    render(
      <ChatMessage
        id="msg-1"
        role="assistant"
        content="Hola"
        onRegenerate={() => undefined}
      />,
    );

    const copiar = screen.getByRole("button", { name: /copiar mensaje/i });
    const regenerar = screen.getByRole("button", {
      name: /regenerar respuesta/i,
    });

    for (const boton of [copiar, regenerar]) {
      expect(boton.className).not.toMatch(/saptiva-light/);
      expect(boton.className).toMatch(/text-muted/);
    }
  });

  it("la fila de acciones sigue visible mientras tiene el foco (cuadro de feedback)", () => {
    render(<ChatMessage id="msg-1" role="assistant" content="Hola" />);
    const fila = screen.getByRole("button", {
      name: /copiar mensaje/i,
    }).parentElement as HTMLElement;
    expect(fila.className).toMatch(/focus-within:opacity-100/);
  });
});

describe("ChatMessage · mientras se prepara la respuesta", () => {
  it("la burbuja vacía es compacta y verde, y no repite el botón de detener", () => {
    render(
      <ChatMessage
        id="msg-2"
        role="assistant"
        content=""
        isStreaming
        onStop={() => undefined}
      />,
    );
    const burbuja = screen.getByRole("region", { name: /contenido del mensaje/i });
    expect(burbuja.className).toMatch(/bg-primary\/10/);
    expect(burbuja.className.split(/\s+/)).not.toContain("w-full");
    expect(burbuja.className.split(/\s+/)).toContain("w-fit");
    // El botón de detener vive en el compositor.
    expect(
      screen.queryByRole("button", { name: /detener generación/i }),
    ).toBeNull();
  });
});
