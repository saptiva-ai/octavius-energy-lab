/**
 * QA (2026-10-20, P2.7): "dos veces el botón de enviar no funcionó y
 * hubo que recargar". Mientras la primera respuesta tardaba 10 a 20 s, el
 * botón de enviar seguía activo: ChatView descartaba el segundo envío en
 * silencio (`isSending`) y el texto se borraba. Mientras un mensaje se envía,
 * el compositor ofrece detener la generación y no borra lo que se escribe.
 */
import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { ChatInterface } from "../ChatInterface";

// Los mensajes no importan aquí (react-markdown es ESM y Jest no lo carga).
jest.mock("../ChatMessage", () => ({ ChatMessage: () => null }));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));

jest.mock("../../../lib/store", () => ({
  useChat: () => ({
    currentChatId: "chat-1",
    finalizeCreation: jest.fn(),
  }),
}));

jest.mock("../../../hooks/useDocumentReview", () => ({
  useDocumentReview: () => ({ startReview: jest.fn(), uploadFile: jest.fn() }),
}));

jest.mock("../../../lib/logger", () => ({
  logDebug: jest.fn(),
  logError: jest.fn(),
  logWarn: jest.fn(),
}));

beforeEach(() => {
  global.fetch = jest.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ tools: [] }) }),
  ) as jest.Mock;
});

describe("ChatInterface · mientras un mensaje se envía", () => {
  it("ofrece detener, no acepta otro envío y no borra lo escrito", async () => {
    const onSendMessage = jest.fn();
    const onStopStreaming = jest.fn();
    render(
      <ChatInterface
        messages={[]}
        onSendMessage={onSendMessage}
        onStopStreaming={onStopStreaming}
        currentChatId="chat-1"
        sending
      />,
    );
    const textarea = screen.getByPlaceholderText(/pregúntame algo/i);
    fireEvent.change(textarea, { target: { value: "¿y por tienda?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await new Promise((r) => setTimeout(r, 200));

    expect(onSendMessage).not.toHaveBeenCalled();
    expect(textarea).toHaveValue("¿y por tienda?");
    fireEvent.click(
      screen.getByRole("button", { name: /detener generación/i }),
    );
    expect(onStopStreaming).toHaveBeenCalled();
  });

  it("sin envío en curso, Enter manda el mensaje", async () => {
    const onSendMessage = jest.fn();
    render(
      <ChatInterface
        messages={[]}
        onSendMessage={onSendMessage}
        currentChatId="chat-1"
      />,
    );
    const textarea = screen.getByPlaceholderText(/pregúntame algo/i);
    fireEvent.change(textarea, { target: { value: "¿y por tienda?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await new Promise((r) => setTimeout(r, 200));

    expect(onSendMessage).toHaveBeenCalledWith("¿y por tienda?", undefined);
  });
});
