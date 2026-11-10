/**
 * QA (2026-10-20, P2.7): al elegir una pregunta en la ayuda, el
 * texto llegaba al compositor pero el foco no; un Enter caía en el botón "?"
 * y volvía a abrir la ayuda en vez de enviar.
 */
import * as React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { CompactChatComposer } from "../ChatComposer/CompactChatComposer";
import { dispatchHelpOnboardingPrompt } from "@/lib/help-onboarding-events";

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
  }),
}));

jest.mock("../../../lib/store", () => ({
  useChat: () => ({
    currentChatId: "test-chat-123",
    finalizeCreation: jest.fn(),
  }),
}));

jest.mock("../../../hooks/useDocumentReview", () => ({
  useDocumentReview: () => ({
    uploadFile: jest.fn(),
  }),
}));

jest.mock("../../../lib/logger", () => ({
  logDebug: jest.fn(),
  logError: jest.fn(),
}));

describe("CompactChatComposer · pregunta elegida en la ayuda", () => {
  it("toma el foco para que Enter la envíe", async () => {
    render(
      <CompactChatComposer
        value=""
        onChange={jest.fn()}
        onSubmit={jest.fn(async () => {})}
      />,
    );
    const textarea = screen.getByPlaceholderText(/pregúntame algo/i);
    expect(document.activeElement).not.toBe(textarea);

    act(() => {
      dispatchHelpOnboardingPrompt(
        "¿Qué productos están en riesgo de faltante mañana?",
      );
    });

    await waitFor(() => expect(document.activeElement).toBe(textarea));
  });
});

describe("CompactChatComposer · un solo indicador de espera", () => {
  it("mientras responde no pinta su propia barra de 'Analizando con…'", () => {
    render(
      <CompactChatComposer
        value=""
        onChange={jest.fn()}
        onSubmit={jest.fn(async () => {})}
        loading
        showCancel
        onCancel={jest.fn()}
      />,
    );
    expect(screen.queryByText(/analizando con/i)).toBeNull();
    expect(screen.queryByText(/generando respuesta/i)).toBeNull();
  });
});
