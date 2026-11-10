/**
 * Tipos del modal de ayuda. Las vistas las declara el plugin de dominio y
 * llegan por /api/features/views (feedback round 1, 2026-10-16,
 * punto 14); la guía rápida, por /api/features/guide (QA, P2.2,
 * 2026-10-21: aquí estaba fija y no decía el pronóstico ni los meses).
 */

export interface VistaPredefinida {
  id: string;
  titulo: string;
  descripcion?: string;
  prompt: string;
  icono?: string;
  perfiles?: string[];
}
