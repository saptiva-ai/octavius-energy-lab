/**
 * P2.7 del reporte de QA (2026-10-20): lo escrito en el compositor y
 * la ayuda abierta sobreviven a que la vista se vuelva a montar cuando un chat
 * nuevo pasa de su id temporal al id real.
 */
import { textoPara, useComposerStore } from "../composer-store";

describe("borrador del compositor", () => {
  beforeEach(() => {
    useComposerStore.getState().limpiarTexto();
    useComposerStore.getState().cerrarAyuda();
  });

  it("el texto de un chat temporal pasa al chat real", () => {
    useComposerStore.getState().fijarTexto("hola", "temp-abc");
    expect(textoPara(useComposerStore.getState(), "3f6c2a10-real")).toBe("hola");
  });

  it("el texto sin chat (elegido en la ayuda) va al chat abierto", () => {
    useComposerStore.getState().fijarTexto("¿Cuánto vendimos?", null);
    expect(textoPara(useComposerStore.getState(), "temp-xyz")).toBe("¿Cuánto vendimos?");
    expect(textoPara(useComposerStore.getState(), "3f6c2a10-real")).toBe("¿Cuánto vendimos?");
  });

  it("el texto de un chat no aparece en otro chat ya creado", () => {
    useComposerStore.getState().fijarTexto("solo para A", "chat-a");
    expect(textoPara(useComposerStore.getState(), "chat-b")).toBe("");
    expect(textoPara(useComposerStore.getState(), "chat-a")).toBe("solo para A");
  });

  it("un chat nuevo no hereda lo escrito en otro chat ya creado", () => {
    useComposerStore.getState().fijarTexto("borrador de A", "chat-a");
    expect(textoPara(useComposerStore.getState(), "temp-nuevo")).toBe("");
  });

  it("limpiar deja el compositor vacío", () => {
    useComposerStore.getState().fijarTexto("enviado", "chat-a");
    useComposerStore.getState().limpiarTexto();
    expect(textoPara(useComposerStore.getState(), "chat-a")).toBe("");
  });

  it("la ayuda abierta se recuerda por ubicación del botón", () => {
    useComposerStore.getState().abrirAyuda("encabezado");
    expect(useComposerStore.getState().ayudaAbierta).toBe("encabezado");
    useComposerStore.getState().cerrarAyuda();
    expect(useComposerStore.getState().ayudaAbierta).toBeNull();
  });
});
