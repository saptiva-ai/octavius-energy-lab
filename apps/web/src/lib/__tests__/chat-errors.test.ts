/**
 * Mensajes de error del envío de chat: timeout ≠ indisponibilidad
 * (card latencia-chat-retail-prediccion).
 */

import { chatSendErrorMessage, isChatTimeoutError } from "../chat-errors";

describe("isChatTimeoutError", () => {
  it("detecta el timeout de axios (ECONNABORTED)", () => {
    expect(
      isChatTimeoutError({
        code: "ECONNABORTED",
        message: "timeout of 120000ms exceeded",
      }),
    ).toBe(true);
  });

  it("detecta timeouts por mensaje aunque no haya code", () => {
    expect(isChatTimeoutError(new Error("timeout of 30000ms exceeded"))).toBe(
      true,
    );
  });

  it("NO marca como timeout un error de red genérico", () => {
    expect(
      isChatTimeoutError({ code: "ERR_NETWORK", message: "socket hang up" }),
    ).toBe(false);
    expect(isChatTimeoutError(null)).toBe(false);
    expect(isChatTimeoutError("boom")).toBe(false);
  });
});

describe("chatSendErrorMessage", () => {
  it("con timeout avisa que el servidor puede seguir procesando (no reenviar)", () => {
    const mensaje = chatSendErrorMessage({
      code: "ECONNABORTED",
      message: "timeout of 120000ms exceeded",
    });
    expect(mensaje).toContain("tardando");
    expect(mensaje).toContain("seguir procesándola");
    expect(mensaje).not.toContain("no pude conectar");
  });

  it("con error de conexión conserva el mensaje de indisponibilidad", () => {
    const mensaje = chatSendErrorMessage({
      code: "ERR_NETWORK",
      message: "socket hang up",
    });
    expect(mensaje).toContain("no pude conectar");
  });
});
