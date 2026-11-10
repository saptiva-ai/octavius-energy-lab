"use client";

import * as React from "react";

/**
 * Preguntas sugeridas declaradas por los plugins de dominio (server-driven).
 *
 * La web NO conoce el dominio: el plugin declara sus sugerencias en su catálogo
 * YAML, el backend las relaya en /api/features/suggestions y la web solo las
 * muestra. Desde el 2026-10-19 viven en el modal de ayuda, no como chips bajo
 * el compositor. Agregar o editar una sugerencia = editar el YAML del plugin.
 */
export interface ToolSuggestion {
  id: string;
  titulo: string;
  prompt: string;
  icono?: string;
  categoria?: string;
  descripcion?: string;
  /** ToolId que la sugerencia necesita (la herramienta de datos va fija). */
  tool_id?: string;
}

/** Carga las sugerencias cuando `activo` (el modal abierto); tolerante a fallas. */
export function useToolSuggestions(activo: boolean): ToolSuggestion[] {
  const [suggestions, setSuggestions] = React.useState<ToolSuggestion[]>([]);

  React.useEffect(() => {
    if (!activo) return;
    let vigente = true;
    fetch("/api/features/suggestions", {
      headers: { Accept: "application/json" },
    })
      .then((res) => (res.ok ? res.json() : { suggestions: [] }))
      .then((data: { suggestions?: ToolSuggestion[] }) => {
        if (!vigente) return;
        const items = Array.isArray(data?.suggestions) ? data.suggestions : [];
        setSuggestions(items.filter((s) => s?.id && s?.titulo && s?.prompt));
      })
      .catch(() => {
        if (vigente) setSuggestions([]);
      });
    return () => {
      vigente = false;
    };
  }, [activo]);

  return suggestions;
}
