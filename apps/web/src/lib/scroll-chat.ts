/**
 * Regla de auto-scroll de la lista de mensajes (feedback round 1,
 * 2026-10-16, punto 8): antes cada cambio de mensajes y cada fragmento del
 * streaming bajaban al fondo, y el inicio de una respuesta larga (alertas)
 * quedaba fuera de vista sin poder subir a leerlo.
 */

/** Píxeles desde el fondo que todavía cuentan como "estar abajo". */
export const UMBRAL_FONDO_PX = 80;

export interface MedidasScroll {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}

export function estaCercaDelFondo(
  m: MedidasScroll,
  umbral: number = UMBRAL_FONDO_PX,
): boolean {
  return m.scrollHeight - (m.scrollTop + m.clientHeight) <= umbral;
}

export function debeBajarAlFondo(estado: {
  estabaEnElFondo: boolean;
  ultimoEsDelUsuario: boolean;
}): boolean {
  return estado.estabaEnElFondo || estado.ultimoEsDelUsuario;
}
