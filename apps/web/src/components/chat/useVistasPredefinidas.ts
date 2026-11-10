"use client";

import * as React from "react";

import type { VistaPredefinida } from "./help-onboarding-content";

/**
 * Vistas predefinidas declaradas por el plugin de dominio y relevadas por el
 * backend (mismo patrón que las sugerencias). Tolerante: sin backend o sin
 * plugin la lista queda vacía y el modal lo dice.
 */
export function useVistasPredefinidas(abierto: boolean): {
  vistas: VistaPredefinida[];
  cargando: boolean;
} {
  const [vistas, setVistas] = React.useState<VistaPredefinida[]>([]);
  const [cargando, setCargando] = React.useState(false);

  React.useEffect(() => {
    if (!abierto) return;
    let activo = true;
    setCargando(true);
    fetch("/api/features/views", { headers: { Accept: "application/json" } })
      .then((res) => (res.ok ? res.json() : { views: [] }))
      .then((data: { views?: VistaPredefinida[] }) => {
        if (!activo) return;
        const items = Array.isArray(data?.views) ? data.views : [];
        setVistas(items.filter((v) => v?.id && v?.titulo && v?.prompt));
      })
      .catch(() => {
        if (activo) setVistas([]);
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, [abierto]);

  return { vistas, cargando };
}
