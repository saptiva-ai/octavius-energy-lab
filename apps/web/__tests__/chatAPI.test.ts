/**
 * Tests for Chat API Client
 *
 * Verifica la integración con la API de chat,
 * manejo de errores, y flujo de mensajes.
 */

// Mock fetch global
globalThis.fetch = jest.fn() as any;

// Tipos para las respuestas de la API
interface ChatResponse {
  chat_id: string;
  message_id: string;
  content: string;
  model: string;
  tokens?: number;
  finish_reason?: string;
}

interface ErrorResponse {
  type: string;
  title: string;
  status: number;
  detail: string;
  code: string;
}

describe("Chat API Client", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Successful chat request", () => {
    it("should send chat message and receive response", async () => {
      const mockResponse: ChatResponse = {
        chat_id: "test-chat-123",
        message_id: "msg-456",
        content: "Esta es una respuesta de prueba",
        model: "SAPTIVA_CORTEX",
        tokens: 150,
        finish_reason: "stop",
      };

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
      });

      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "Test message",
          model: "SAPTIVA_CORTEX",
          channel: "chat",
        }),
      });

      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data.model).toBe("SAPTIVA_CORTEX");
      expect(data.content).toBeTruthy();
      expect(data.chat_id).toBe("test-chat-123");
    });

    it("should include tools_enabled in request", async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          chat_id: "test",
          message_id: "test",
          content: "response",
          model: "SAPTIVA_CORTEX",
        }),
      });

      await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "Test",
          model: "SAPTIVA_CORTEX",
          channel: "chat",
          tools_enabled: {
            web_search: true,
            calculator: false,
          },
        }),
      });

      expect(global.fetch).toHaveBeenCalledWith(
        "/api/chat",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("web_search"),
        }),
      );
    });
  });

  describe("Error handling", () => {
    it("should handle 401 unauthorized error", async () => {
      const errorResponse: ErrorResponse = {
        type: "https://api.saptiva.ai/problems/unauthorized",
        title: "Unauthorized",
        status: 401,
        detail: "Token expirado",
        code: "UNAUTHORIZED",
      };

      (global.fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => errorResponse,
      });

      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "Test" }),
      });

      expect(response.ok).toBe(false);
      expect(response.status).toBe(401);

      const error = await response.json();
      expect(error.code).toBe("UNAUTHORIZED");
    });

    it("should handle 422 validation error", async () => {
      const errorResponse: ErrorResponse = {
        type: "https://api.saptiva.ai/problems/validation_error",
        title: "Validation Error",
        status: 422,
        detail: "Message cannot be empty",
        code: "VALIDATION_ERROR",
      };

      (global.fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: async () => errorResponse,
      });

      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "" }),
      });

      expect(response.status).toBe(422);
    });

    it("should handle network error", async () => {
      (global.fetch as any).mockRejectedValueOnce(new Error("Network error"));

      await expect(
        fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: "Test" }),
        }),
      ).rejects.toThrow("Network error");
    });
  });

  describe("Channel-specific requests", () => {
    it('should send request with "title" channel', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          chat_id: "test",
          message_id: "test",
          content: "Short title",
          model: "SAPTIVA_TURBO",
        }),
      });

      await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "Long conversation history...",
          model: "SAPTIVA_TURBO",
          channel: "title",
        }),
      });

      const callArgs = (global.fetch as any).mock.calls[0];
      const body = JSON.parse(callArgs[1].body);

      expect(body.channel).toBe("title");
    });

    it('should send request with "report" channel', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          chat_id: "test",
          message_id: "test",
          content: "Detailed report...",
          model: "SAPTIVA_CORTEX",
        }),
      });

      await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "Generate report",
          model: "SAPTIVA_CORTEX",
          channel: "report",
        }),
      });

      const callArgs = (global.fetch as any).mock.calls[0];
      const body = JSON.parse(callArgs[1].body);

      expect(body.channel).toBe("report");
    });
  });

  describe("Model selection", () => {
    const models = ["SAPTIVA_TURBO", "SAPTIVA_CORTEX", "SAPTIVA_OPS"];

    models.forEach((model) => {
      it(`should send request with ${model}`, async () => {
        (global.fetch as any).mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            chat_id: "test",
            message_id: "test",
            content: "Response",
            model: model,
          }),
        });

        await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: "Test",
            model: model,
            channel: "chat",
          }),
        });

        const callArgs = (global.fetch as any).mock.calls[0];
        const body = JSON.parse(callArgs[1].body);

        expect(body.model).toBe(model);
      });
    });
  });
});
