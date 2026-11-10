"use client";

import * as React from "react";

/**
 * Guía rápida del modal de ayuda: qué puede responder el chat, de qué meses
 * y categorías, y qué no tiene. La declara el plugin de dominio con los datos
 * de la base y el backend la relaya en /api/features/guide (QA,
 * P2.2, 2026-10-21: estaba fija aquí y no decía el pronóstico ni los meses).
 * Tolerante: sin backend o sin plugin las listas quedan vacías y el modal no
 * muestra la guía.
 */
export interface GuiaAyuda {
  puedes: string[];
  no_tiene: string[];
}

const VACIA: GuiaAyuda = { puedes: [], no_tiene: [] };

function textos(valor: unknown): string[] {
  return Array.isArray(valor)
    ? valor.filter((t): t is string => typeof t === "string" && t.length > 0)
    : [];
}

/** Carga la guía cuando `activo` (el modal abierto). */
export function useGuiaAyuda(activo: boolean): GuiaAyuda {
  const [guia, setGuia] = React.useState<GuiaAyuda>(VACIA);

  React.useEffect(() => {
    if (!activo) return;
    let vigente = true;
    fetch("/api/features/guide", { headers: { Accept: "application/json" } })
      .then((res) => (res.ok ? res.json() : { guide: VACIA }))
      .then((data: { guide?: Partial<GuiaAyuda> }) => {
        if (!vigente) return;
        setGuia({
          puedes: textos(data?.guide?.puedes),
          no_tiene: textos(data?.guide?.no_tiene),
        });
      })
      .catch(() => {
        if (vigente) setGuia(VACIA);
      });
    return () => {
      vigente = false;
    };
  }, [activo]);

  return guia;
}
