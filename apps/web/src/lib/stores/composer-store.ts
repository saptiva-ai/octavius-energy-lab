/**
 * Borrador del compositor y ayuda abierta, fuera de los componentes.
 *
 * P2.7 del reporte de QA (2026-10-20): "dos veces el botón de enviar
 * no funcionó y hubo que recargar; la ventana de ayuda se quedó encima del
 * chat". Un chat nuevo nace con id temporal y, cuando el servidor responde,
 * cambian la ruta y la llave de ChatInterface: la vista se vuelve a montar.
 * Lo escrito, la pregunta elegida en la ayuda y la ayuda abierta vivían en
 * estado local y se perdían en ese segundo.
 */
import { create } from "zustand";

interface ComposerState {
  /** Texto del compositor. */
  texto: string;
  /** Chat al que pertenece el texto; null = el chat que esté abierto. */
  chatId: string | null;
  /** Ubicación del botón de ayuda abierto (hay uno por layout); null = cerrada. */
  ayudaAbierta: string | null;
  fijarTexto: (texto: string, chatId: string | null) => void;
  limpiarTexto: () => void;
  abrirAyuda: (ubicacion: string) => void;
  cerrarAyuda: () => void;
}

export const useComposerStore = create<ComposerState>()((set) => ({
  texto: "",
  chatId: null,
  ayudaAbierta: null,
  fijarTexto: (texto, chatId) => set({ texto, chatId }),
  limpiarTexto: () => set({ texto: "", chatId: null }),
  abrirAyuda: (ubicacion) => set({ ayudaAbierta: ubicacion }),
  cerrarAyuda: () => set({ ayudaAbierta: null }),
}));

/** Texto que le toca al compositor de `chatId`: el suyo, el que no tiene chat
 * (elegido en la ayuda) o el de un chat temporal que ya recibió su id real.
 * Un chat ya creado no hereda lo escrito en otro. */
export function textoPara(
  estado: Pick<ComposerState, "texto" | "chatId">,
  chatId: string | null,
): string {
  if (!estado.texto) return "";
  if (estado.chatId === null || estado.chatId === chatId) return estado.texto;
  const deUnChatTemporal = estado.chatId.startsWith("temp-");
  const alChatReal = chatId !== null && !chatId.startsWith("temp-");
  return deUnChatTemporal && alChatReal ? estado.texto : "";
}
