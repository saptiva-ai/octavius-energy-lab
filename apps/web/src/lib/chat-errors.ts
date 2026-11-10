/**
 * Mensajes de error del envío de chat (card latencia-chat-retail-prediccion).
 *
 * Un timeout NO es lo mismo que indisponibilidad: cuando el cliente corta por
 * tiempo, el backend normalmente SIGUE procesando la consulta y reenviar
 * duplica la ejecución. El mensaje al usuario debe reflejarlo en vez del
 * falso "no pude conectar".
 */

/** ¿El error del envío fue un timeout del cliente (axios ECONNABORTED)? */
export function isChatTimeoutError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const e = error as { code?: string; message?: string };
  if (e.code === "ECONNABORTED") return true;
  return /timeout/i.test(e.message ?? "");
}

/** Mensaje para la burbuja de error del asistente según el tipo de fallo. */
export function chatSendErrorMessage(error: unknown): string {
  if (isChatTimeoutError(error)) {
    return (
      "La consulta está tardando más de lo esperado y se agotó el tiempo de " +
      "espera. El servidor puede seguir procesándola: espera unos segundos y " +
      "recarga la conversación antes de reenviar el mensaje."
    );
  }
  return (
    "Lo siento, no pude conectar con el servidor de chat en este momento. " +
    "Intenta nuevamente en unos segundos."
  );
}
