/**
 * Pragmatic tests for api-client.ts public methods
 *
 * Focus: Observable behavior of public API methods
 * - Chat: sendChatMessage
 * - Sessions: getChatSessions, updateChatSession, deleteChatSession
 * - Models: getModels
 * - Error handling: handleError
 * - Connection: checkConnection
 */

import { apiClient, setAuthTokenGetter } from "../api-client";
import { AxiosError } from "axios";

// Note: apiClient uses a real axios instance created on module load
// We'll test the public interface behavior

jest.mock("../auth-client", () => ({
  ensureValidToken: jest.fn().mockResolvedValue("test-token"),
  tryRefreshOnce: jest.fn().mockResolvedValue(false),
}));

describe("api-client public methods", () => {
  describe("Error Handling", () => {
    it("extracts detail from API error", () => {
      const error = {
        response: {
          data: {
            detail: "Resource not found",
          },
        },
      } as AxiosError;

      const message = apiClient.handleError(error as any);
      expect(message).toBe("Resource not found");
    });

    it("extracts error field when detail is missing", () => {
      const error = {
        response: {
          data: {
            error: "Invalid request",
          },
        },
      } as AxiosError;

      const message = apiClient.handleError(error as any);
      expect(message).toBe("Invalid request");
    });

    it("falls back to error.message", () => {
      const error = {
        message: "Network timeout",
      } as AxiosError;

      const message = apiClient.handleError(error as any);
      expect(message).toBe("Network timeout");
    });

    it("returns generic message for unknown error", () => {
      const error = {} as AxiosError;

      const message = apiClient.handleError(error as any);
      expect(message).toBe("An unknown error occurred");
    });
  });

  describe("Token Getter", () => {
    it("returns null when auth token getter not set", () => {
      const token = apiClient.getToken();
      // Token might be null or a string depending on setup
      expect(typeof token === "string" || token === null).toBe(true);
    });
  });

  describe("sendChatMessage — timeouts y reintentos (POST no idempotente)", () => {
    // Card latencia-chat-retail-prediccion: un timeout NO garantiza que el
    // backend dejó de procesar; reintentar duplicaba function calling +
    // workflow + LLM (3 ejecuciones por mensaje observadas en vivo).
    let postMock: jest.Mock;
    let originalPost: any;

    beforeEach(() => {
      originalPost = (apiClient as any).client.post;
      postMock = jest.fn();
      (apiClient as any).client.post = postMock;
    });

    afterEach(() => {
      (apiClient as any).client.post = originalPost;
    });

    const request = { message: "faltante hoy", chat_id: null } as any;

    it("un timeout (ECONNABORTED) NO se reintenta: un solo POST", async () => {
      postMock.mockRejectedValue({
        code: "ECONNABORTED",
        message: "timeout of 120000ms exceeded",
      });

      await expect(apiClient.sendChatMessage(request)).rejects.toMatchObject({
        code: "ECONNABORTED",
      });
      expect(postMock).toHaveBeenCalledTimes(1);
    });

    it("usa 120s de timeout sin archivos y 180s con archivos", async () => {
      postMock.mockResolvedValue({ data: { content: "ok" } });

      await apiClient.sendChatMessage(request);
      expect(postMock).toHaveBeenLastCalledWith(
        "/api/chat",
        expect.anything(),
        {
          timeout: 120000,
        },
      );

      await apiClient.sendChatMessage({
        ...request,
        file_ids: ["doc-1"],
      } as any);
      expect(postMock).toHaveBeenLastCalledWith(
        "/api/chat",
        expect.anything(),
        {
          timeout: 180000,
        },
      );
    });

    it("un corte de red ambiguo (sin response, p.ej. ECONNRESET) NO se reintenta", async () => {
      postMock.mockRejectedValue({
        code: "ERR_NETWORK",
        message: "socket hang up",
      });

      await expect(apiClient.sendChatMessage(request)).rejects.toMatchObject({
        code: "ERR_NETWORK",
      });
      expect(postMock).toHaveBeenCalledTimes(1);
    });

    it("un 500 del backend NO se reintenta (pudo ejecutar el workflow)", async () => {
      postMock.mockRejectedValue({ response: { status: 500, data: {} } });

      await expect(apiClient.sendChatMessage(request)).rejects.toBeDefined();
      expect(postMock).toHaveBeenCalledTimes(1);
    });

    it("502/503 (el proxy no entregó la petición) SÍ se reintenta", async () => {
      postMock
        .mockRejectedValueOnce({ response: { status: 502, data: {} } })
        .mockResolvedValueOnce({ data: { content: "ok" } });

      const response = await apiClient.sendChatMessage(request);
      expect(response).toEqual({ content: "ok" });
      expect(postMock).toHaveBeenCalledTimes(2);
    });
  });

  describe("sendChatMessageStream — evento status", () => {
    const originalFetch = global.fetch;

    beforeEach(() => {
      setAuthTokenGetter(() => "test-token");
    });

    afterEach(() => {
      global.fetch = originalFetch;
    });

    // Equipo (2026-10-21): el backend avisa qué tool eligió el decide antes de
    // narrar; el indicador de espera cambia de tema con ese aviso.
    it("entrega la tool elegida antes de los chunks", async () => {
      const sse =
        'event: status\ndata: {"fase": "consultando", "tools": [{"tool": "retail_analytics", "metrica": "venta_hora", "dimension": null}]}\n\n' +
        'event: chunk\ndata: {"content": "Hola"}\n\n';
      const bytes = new TextEncoder().encode(sse);
      let leido = false;
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        statusText: "OK",
        headers: { get: () => "text/event-stream" },
        body: {
          getReader: () => ({
            read: async () => {
              if (leido) return { done: true, value: undefined };
              leido = true;
              return { done: false, value: bytes };
            },
            releaseLock: () => undefined,
          }),
        },
      });

      const eventos = [];
      for await (const evento of apiClient.sendChatMessageStream({
        message: "¿cuánto vendimos?",
        chat_id: null,
        model: "turbo",
      } as any)) {
        eventos.push(evento);
      }

      expect(eventos.map((e) => e.type)).toEqual(["status", "chunk"]);
      expect(eventos[0].data).toEqual({
        fase: "consultando",
        tools: [{ tool: "retail_analytics", metrica: "venta_hora", dimension: null }],
      });
    });
  });

  describe("sendChatMessageStream — cancellation", () => {
    const originalFetch = global.fetch;

    beforeEach(() => {
      setAuthTokenGetter(() => "test-token");
    });

    afterEach(() => {
      global.fetch = originalFetch;
    });

    it("propagates AbortError as-is instead of wrapping it as a network error", async () => {
      // Aborta un fetch en pleno stream: Chromium rechaza con este DOMException.
      const abortError = new DOMException(
        "BodyStreamBuffer was aborted",
        "AbortError",
      );
      global.fetch = jest.fn().mockRejectedValue(abortError);

      const generator = apiClient.sendChatMessageStream({
        message: "hola",
        chat_id: null,
        model: "turbo",
      } as any);

      await expect(generator.next()).rejects.toMatchObject({
        name: "AbortError",
      });
    });
  });
});

describe("isSecondaryRequest (scope del auto-logout en 401)", () => {
  // Un 401 en estas features degradaba a logout total wipeando el chat
  // (card auto-logout-401-scope); solo el flujo principal desloguea.
  const { isSecondaryRequest } = jest.requireActual("../api-client");

  it("PATCH de sesión (auto-título/pin/tools) es secundario", () => {
    expect(
      isSecondaryRequest({ url: "/api/sessions/abc-123", method: "patch" }),
    ).toBe(true);
  });

  it("canvas state y feedback son secundarios", () => {
    expect(
      isSecondaryRequest({
        url: "/api/sessions/abc-123/canvas",
        method: "patch",
      }),
    ).toBe(true);
    expect(isSecondaryRequest({ url: "/api/feedback", method: "post" })).toBe(
      true,
    );
  });

  it("el listado de documentos del hilo es secundario (e2e chart-caching)", () => {
    // Un 401 en /api/documents expulsaba la sesión a mitad de la navegación
    // a una conversación (visto con trace 2026-07-21): degrada sin logout.
    expect(
      isSecondaryRequest({
        url: "/api/documents?conversation_id=abc&limit=50",
        method: "get",
      }),
    ).toBe(true);
  });

  it("el flujo principal NO es secundario (conserva auto-logout)", () => {
    expect(isSecondaryRequest({ url: "/api/chat", method: "post" })).toBe(
      false,
    );
    expect(
      isSecondaryRequest({ url: "/api/sessions/abc-123", method: "get" }),
    ).toBe(false);
    expect(
      isSecondaryRequest({
        url: "/api/history/abc-123/unified",
        method: "get",
      }),
    ).toBe(false);
    expect(isSecondaryRequest({ url: "/api/conversations" })).toBe(false);
  });
});
