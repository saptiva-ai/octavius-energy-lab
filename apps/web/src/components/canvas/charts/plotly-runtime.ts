/**
 * Import perezoso + cacheado de plotly.js-dist-min. Solo lo necesitan las
 * acciones del toolbar (PNG/reset zoom) — react-plotly.js ya trae su propio
 * bundle de Plotly para el render, este import separado es para llamar a la
 * API estática (`downloadImage`, `relayout`) sin duplicar el peso en el
 * bundle inicial del chat.
 */
let runtimePromise: Promise<typeof import("plotly.js-dist-min")> | null = null;

export function getPlotlyRuntime() {
  if (!runtimePromise) {
    runtimePromise = import("plotly.js-dist-min");
  }
  return runtimePromise;
}
