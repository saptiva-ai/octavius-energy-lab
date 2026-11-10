/**
 * feedback round 1 (2026-10-16, punto 8): en la respuesta de
 * alertas no se podía leer el inicio ("no me deja verlo"): cada fragmento del
 * streaming forzaba el scroll al fondo. La lista solo baja sola si el usuario
 * ya estaba abajo o si acaba de enviar su mensaje.
 */
import { debeBajarAlFondo, estaCercaDelFondo } from "../scroll-chat";

describe("estaCercaDelFondo", () => {
  it("abajo del todo o a pocos píxeles cuenta como fondo", () => {
    expect(
      estaCercaDelFondo({
        scrollTop: 900,
        scrollHeight: 1500,
        clientHeight: 600,
      }),
    ).toBe(true);
    expect(
      estaCercaDelFondo({
        scrollTop: 850,
        scrollHeight: 1500,
        clientHeight: 600,
      }),
    ).toBe(true);
  });

  it("si subió a leer, no está en el fondo", () => {
    expect(
      estaCercaDelFondo({
        scrollTop: 200,
        scrollHeight: 1500,
        clientHeight: 600,
      }),
    ).toBe(false);
  });
});

describe("debeBajarAlFondo", () => {
  it("baja si estaba en el fondo", () => {
    expect(
      debeBajarAlFondo({ estabaEnElFondo: true, ultimoEsDelUsuario: false }),
    ).toBe(true);
  });

  it("baja si el último mensaje es del usuario (acaba de enviar)", () => {
    expect(
      debeBajarAlFondo({ estabaEnElFondo: false, ultimoEsDelUsuario: true }),
    ).toBe(true);
  });

  it("no baja mientras el usuario lee arriba y llega la respuesta", () => {
    expect(
      debeBajarAlFondo({ estabaEnElFondo: false, ultimoEsDelUsuario: false }),
    ).toBe(false);
  });
});
