/**
 * Adaptador puro: AnalyticsResponse (contrato del plugin retail-advisor,
 * ver lib/contracts/analytics.ts) -> ChartData (contrato de transporte de
 * canvas/chat, ver lib/types.ts).
 *
 * Vive en el frontend a propósito (R2 del refactor: el backend no genera
 * shapes de presentación). El plugin solo garantiza datos + chart_type
 * explícito; cómo se ve el trace de Plotly es una decisión de UI.
 */
import type { AnalyticsResponse } from "@/lib/contracts";
import type { ChartData } from "@/lib/types";
// Estados de México simplificados (32 features, prop `name`; "Estado de
// México" parcheado para casar con dim_tienda.region). Empaquetado local:
// el canvas no puede depender de tiles/CDN externos.
import mexicoEstados from "./geo/mexico-estados.geo.json";

type PlotlyTrace = ChartData["plotly_config"]["data"][number];

// ---------------------------------------------------------------------------
// Defaults editoriales del canvas (card dataviz-nyt-canvas-retail).
// Benchmark: piezas de cancelaciones de vuelos del NYT (deck Marco Hernández)
// + método del skill dataviz: etiquetas directas SELECTIVAS (nunca un número
// en cada punto), leyenda solo con >=2 series, miles con separador, marcas
// delgadas, color de status únicamente cuando el color SIGNIFICA algo.
// ---------------------------------------------------------------------------

/** Puntos máximos para etiquetar cada punta de barra (rankings chicos). */
const MAX_PUNTOS_ETIQUETA_DIRECTA = 12;
/** Rankings de una serie con más barras que esto van horizontales: el nombre
 *  del artículo se lee completo en el eje. */
const MAX_PUNTOS_RANKING_VERTICAL = 6;

/** label (corta, eje) → label_completo (tooltip), desde table_data del plugin. */
function nombresCompletos(response: AnalyticsResponse): Map<string, string> {
  const mapa = new Map<string, string>();
  for (const row of (response.table_data ?? []) as Array<
    Record<string, unknown>
  >) {
    const label = row?.label;
    const completo = row?.label_completo;
    if (typeof label === "string" && typeof completo === "string") {
      mapa.set(label, completo);
    }
  }
  return mapa;
}

/** Ranking largo de una serie: se dibuja horizontal (ver seriesToTraces). */
/** Dimensiones con orden propio en el eje x (fechas, horas, meses): nunca
 * se voltean a horizontal aunque la etiqueta sea larga. */
const DIMENSIONES_TEMPORALES = new Set(["dia", "hora", "mes", "semana", "fecha"]);
/** Una categoría más larga que esto no cabe en vertical sin recortarse. */
export const MAX_ETIQUETA_VERTICAL = 14;

export function esRankingHorizontal(response: AnalyticsResponse): boolean {
  if (response.chart_type !== "bar" || response.series.length !== 1) return false;
  const points = response.series[0]?.points ?? [];
  if (points.length < 2) return false;
  if (DIMENSIONES_TEMPORALES.has(String(response.grounding?.dimension ?? ""))) {
    return false;
  }
  const muchas =
    response.visualization?.task === "ranking" &&
    points.length > MAX_PUNTOS_RANKING_VERTICAL;
  // GRA-4 (2026-11-08): "Brandy y coñac", "Coolers y bebidas preparadas"
  // salían en diagonal y cortadas; con nombres largos la barra va acostada.
  const largas = points.some((p) => p.label.length > MAX_ETIQUETA_VERTICAL);
  return muchas || largas;
}

/** Parte una etiqueta larga en renglones (`<br>`) para un eje x vertical de
 * varias series, donde no se puede acostar la barra (GRA-4). */
export function envolverEtiqueta(label: string, ancho = MAX_ETIQUETA_VERTICAL): string {
  const palabras = label.trim().split(/\s+/);
  const renglones: string[] = [];
  let actual = "";
  for (const palabra of palabras) {
    if (!actual) actual = palabra;
    else if ((actual + " " + palabra).length <= ancho) actual += " " + palabra;
    else {
      renglones.push(actual);
      actual = palabra;
    }
  }
  if (actual) renglones.push(actual);
  if (renglones.length <= 3) return renglones.join("<br>");
  return `${renglones.slice(0, 3).join("<br>")}…`;
}

const DIMENSION_LEGIBLE: Record<string, string> = {
  articulo: "artículo",
  categoria: "categoría",
  tienda: "tienda",
  region: "región",
  decil: "decil de venta",
  estatus: "estatus",
  dia: "día",
  hora: "hora",
  mes: "mes",
  semana: "semana",
};

/** Título del panel: el del plugin cuando lo manda; si solo llega la métrica
 * ("Venta", "Merma"), se le suma la dimensión ("Merma por categoría") para
 * que no haya títulos de una palabra (GRA-7). */
export function tituloGrafica(response: AnalyticsResponse): string {
  const propio = (
    response.visualization?.headline ??
    response.visualization?.title ??
    ""
  ).trim();
  if (propio) return propio;
  const dim = String(response.grounding?.dimension ?? "");
  if (!dim) return response.metric_name;
  return `${response.metric_name} por ${DIMENSION_LEGIBLE[dim] ?? dim}`;
}

/** Alto del lienzo según las barras (26 px por barra más ejes), acotado: una
 * gráfica de 14 tiendas no se aplasta y una de dos no flota en medio del
 * panel (GRA-9). */
export function alturaPorFilas(n: number): number {
  return Math.min(560, Math.max(240, 26 * n + 96));
}

/** Variación entre dos series del mismo eje ("agosto" contra "septiembre"):
 * una anotación por categoría con el cambio porcentual (GRA-10). */
export function anotacionesDelta(
  response: AnalyticsResponse,
): Array<Record<string, unknown>> {
  if (response.chart_type !== "bar" || response.series.length !== 2) return [];
  const [antes, despues] = response.series;
  const previos = new Map(antes.points.map((p) => [p.label, p.value]));
  return despues.points.flatMap((p) => {
    const base = previos.get(p.label);
    if (base == null || base === 0) return [];
    const delta = (100 * (p.value - base)) / Math.abs(base);
    return [
      {
        x: envolverEtiqueta(p.label),
        y: Math.max(base, p.value),
        text: `${delta >= 0 ? "+" : "−"}${Math.abs(delta).toFixed(1)}%`,
        showarrow: false,
        yanchor: "bottom",
        yshift: 6,
        font: { size: 11, color: delta >= 0 ? "#0f8a76" : "#e34948" },
      },
    ];
  });
}

const ROJO_STATUS = "#EF4444";

/** Formatea un valor para etiquetas directas/anotaciones (es-MX: 57,422). */
export function formatoValor(value: number, unit?: string | null): string {
  if (unit === "percent") return `${value.toFixed(1)}%`;
  const numero = new Intl.NumberFormat("es-MX", {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  }).format(value);
  return unit === "currency" ? `$${numero}` : numero;
}

/** Título legible del eje/colorbar según la unidad del catálogo. */
export function unidadLegible(unit?: string | null): string | undefined {
  if (unit === "percent") return "%";
  if (unit === "currency") return "MXN";
  if (unit === "count") return "unidades";
  return unit ?? undefined;
}

/** Título de eje en la forma que Plotly 2 acepta (`{ text }`): un string
 * suelto se ignoraba y el eje salía sin unidad (GRA-1, 2026-11-08). */
export function tituloEje(
  texto?: string | null,
): { text: string } | undefined {
  return texto ? { text: texto } : undefined;
}

/** Prefijo/sufijo de los ticks según la unidad: `$` en pesos, `%` en
 * porcentajes. Los ticks decían `0 2 4 6` junto a etiquetas `5.9%`. */
export function ticksUnidad(
  unit?: string | null,
): { tickprefix?: string; ticksuffix?: string } {
  if (unit === "percent") return { ticksuffix: "%" };
  if (unit === "currency") return { tickprefix: "$" };
  return {};
}

/** Etiqueta de categoría acortada por el final con "…" (Plotly recortaba
 * por el inicio: "sco Coca Cola Sin Azúcar 1.35 Lt"). El nombre completo
 * sigue en el hover (customdata). */
export const MAX_ETIQUETA_EJE = 30;
export function acortarEtiqueta(label: string, max = MAX_ETIQUETA_EJE): string {
  const limpio = label.trim();
  if (limpio.length <= max) return limpio;
  return `${limpio.slice(0, max - 1).trimEnd()}…`;
}

/** Margen izquierdo para que la etiqueta más larga quepa (≈6.4 px por
 * carácter a 12 px de Inter, más aire), acotado. */
export function margenParaEtiquetas(labels: string[]): number {
  const mas = Math.max(0, ...labels.map((l) => acortarEtiqueta(l).length));
  return Math.min(230, Math.max(90, Math.round(mas * 6.4 + 24)));
}

/** Orden ordinal cuando las categorías son deciles ("Decil 1".."Decil 10",
 * "Sin venta" al final): ordenarlos por valor perdía la escala (GRA-5). */
export function ordenOrdinal(labels: string[]): string[] | undefined {
  const decil = /^Decil (\d+)$/i;
  const sinVenta = /^sin venta$/i;
  if (!labels.length || !labels.every((l) => decil.test(l) || sinVenta.test(l))) {
    return undefined;
  }
  if (!labels.some((l) => decil.test(l))) return undefined;
  return [...labels].sort((a, b) => {
    const na = decil.exec(a)?.[1];
    const nb = decil.exec(b)?.[1];
    if (na == null) return 1;
    if (nb == null) return -1;
    return Number(na) - Number(nb);
  });
}

/** Hover con el valor formateado (d3-format de Plotly) + nombre de la serie. */
function hoverTemplate(unit?: string | null): string {
  if (unit === "percent") return "%{y:.1f}%<extra>%{fullData.name}</extra>";
  if (unit === "currency") return "%{y:$,.2f}<extra>%{fullData.name}</extra>";
  return "%{y:,.0f}<extra>%{fullData.name}</extra>";
}

/** Hover "nombre completo: valor" (customdata = label_completo del plugin). */
function hoverConNombre(
  unit: string | null | undefined,
  eje: "x" | "y",
): string {
  const valor =
    unit === "percent"
      ? `%{${eje}:.1f}%`
      : unit === "currency"
        ? `%{${eje}:$,.2f}`
        : `%{${eje}:,.0f}`;
  return `%{customdata}: ${valor}<extra>%{fullData.name}</extra>`;
}

/** Choropleth de México por estado: labels = dim_tienda.region, z = value. */
function buildRegionChoropleth(response: AnalyticsResponse): PlotlyTrace[] {
  const points = response.series.flatMap((s) => s.points);
  if (points.length === 0) return [];
  const higherIsBetter = response.visualization?.higher_is_better;
  const pointByLabel = new Map(points.map((point) => [point.label, point]));
  const rowByLabel = new Map(
    response.table_data.map((row) => [String(row.label ?? ""), row]),
  );
  const locations = (
    mexicoEstados as {
      features: Array<{ properties: { name: string } }>;
    }
  ).features.map((feature) => feature.properties.name);
  const hasExposure = response.table_data.some(
    (row) => Number.isFinite(row.numerator) && Number.isFinite(row.denominator),
  );
  return [
    {
      type: "choropleth",
      geojson: mexicoEstados as unknown as Record<string, unknown>,
      featureidkey: "properties.name",
      locations,
      z: locations.map((location) => pointByLabel.get(location)?.value ?? null),
      customdata: locations.map((location) => {
        const row = rowByLabel.get(location);
        return [
          Number.isFinite(row?.numerator) ? Number(row?.numerator) : null,
          Number.isFinite(row?.denominator) ? Number(row?.denominator) : null,
        ];
      }),
      zmin: 0,
      // La polaridad viene del contrato semántico; sin ella usamos azul neutro.
      colorscale: higherIsBetter === false ? "Reds" : "Blues",
      marker: { line: { color: "#ffffff", width: 0.5 } },
      colorbar: {
        thickness: 12,
        len: 0.8,
        title: { text: unidadLegible(response.grounding?.unit) },
      },
      hovertemplate: hasExposure
        ? "%{location}: %{z:.1f}%<br>Numerador: %{customdata[0]:,.0f}<br>Denominador: %{customdata[1]:,.0f}<extra></extra>"
        : `%{location}: ${
            response.grounding?.unit === "percent" ? "%{z:.1f}%" : "%{z:,.0f}"
          }<extra></extra>`,
      name: response.series[0]?.name || response.metric_name,
    } as unknown as PlotlyTrace,
  ];
}

function buildIntervalBand(response: AnalyticsResponse): PlotlyTrace[] {
  const forecast = response.series.find((serie) => serie.role === "forecast");
  if (!forecast || forecast.points.length === 0) return [];
  const valid = forecast.points.every(
    (point) =>
      Number.isFinite(point.interval_low) &&
      Number.isFinite(point.interval_high) &&
      Number(point.interval_low) <= point.value &&
      point.value <= Number(point.interval_high),
  );
  if (!valid) return [];
  const x = forecast.points.map((point) => point.label);
  const provider = String(response.grounding?.proveedor ?? "provider");
  return [
    {
      type: "scatter",
      mode: "lines",
      x,
      y: forecast.points.map((point) => point.interval_high),
      line: { width: 0 },
      hoverinfo: "skip",
      showlegend: false,
      name: `Límite superior · ${provider}`,
    } as unknown as PlotlyTrace,
    {
      type: "scatter",
      mode: "lines",
      x,
      y: forecast.points.map((point) => point.interval_low),
      line: { width: 0 },
      fill: "tonexty",
      fillcolor: "rgba(20, 168, 144, 0.18)",
      hoverinfo: "skip",
      name: "Intervalo del provider",
    } as unknown as PlotlyTrace,
  ];
}

function seriesToTraces(response: AnalyticsResponse): PlotlyTrace[] {
  const { chart_type, series } = response;
  const unit = response.grounding?.unit;
  const unaSerie = series.length === 1;
  // Status (rojo = malo) solo con una serie: con varias, el color es identidad.
  const colorStatus =
    unaSerie && response.visualization?.higher_is_better === false
      ? ROJO_STATUS
      : undefined;

  return series.map((serie) => {
    const x = serie.points.map((p) => p.label);
    const crudos = serie.points.map((p) => p.value);
    // Salidas con signo (la merma viene negativa de la fuente): se grafica la
    // magnitud, o las barras iban a la izquierda con "-27" encimado al nombre
    // (GRA-6, 2026-11-08). El sentido lo dice el texto del plugin.
    const todoNegativo =
      unaSerie &&
      chart_type === "bar" &&
      crudos.length > 0 &&
      crudos.every((v) => v <= 0) &&
      crudos.some((v) => v < 0);
    const y = todoNegativo ? crudos.map((v) => Math.abs(v)) : crudos;
    const name = serie.name || response.metric_name;
    const base = { name, hovertemplate: hoverTemplate(unit) };

    switch (chart_type) {
      case "bar": {
        // Etiqueta directa en la punta SOLO en rankings chicos de una serie
        // (Datawrapper/NYT); en series largas o comparativas el hover y el
        // eje cargan los valores.
        const etiquetas =
          unaSerie && serie.points.length <= MAX_PUNTOS_ETIQUETA_DIRECTA
            ? {
                text: y.map((v) => formatoValor(v, unit)),
                textposition: "outside" as const,
                cliponaxis: false,
              }
            : {};
        // Nombre completo del artículo en el hover (el eje lleva la etiqueta
        // corta que manda el plugin en `label`; `label_completo` va en la tabla).
        const completos = nombresCompletos(response);
        const customdata = x.map((label) => completos.get(label) ?? label);
        const hover = { customdata, hovertemplate: hoverConNombre(unit, "y") };
        // Ranking largo de una serie: barras horizontales para que el nombre
        // se lea completo en el eje (un top 10 vertical truncaba todo a
        // "Refresco C…", visto 2026-09-03).
        if (esRankingHorizontal(response)) {
          return {
            type: "bar",
            orientation: "h",
            x: y,
            y: x.map((label) => acortarEtiqueta(label)),
            ...base,
            customdata,
            hovertemplate: hoverConNombre(unit, "x"),
            text: y.map((v) => formatoValor(v, unit)),
            textposition: "outside" as const,
            cliponaxis: false,
            marker: {
              cornerradius: 4,
              ...(colorStatus ? { color: colorStatus } : {}),
            },
          } as unknown as PlotlyTrace;
        }
        return {
          type: "bar",
          // Varias series o pocas categorías: vertical con la etiqueta en
          // renglones (GRA-4); las temporales quedan tal cual.
          x: DIMENSIONES_TEMPORALES.has(String(response.grounding?.dimension ?? ""))
            ? x
            : x.map((label) => envolverEtiqueta(label)),
          y,
          ...base,
          ...etiquetas,
          ...hover,
          marker: {
            cornerradius: 4,
            ...(colorStatus ? { color: colorStatus } : {}),
          },
        };
      }
      case "scatter":
        return {
          type: "scatter",
          mode: "markers",
          x,
          y,
          ...base,
          marker: {
            size: 8,
            ...(colorStatus ? { color: colorStatus } : {}),
          },
        };
      case "line":
      default: {
        // Serie proyectada (forecast) punteada: la convención visual clásica
        // para distinguir lo observado de lo proyectado sobre la misma línea.
        const esForecast = serie.role === "forecast";
        return {
          type: "scatter",
          mode: "lines+markers",
          x,
          y,
          ...base,
          line: {
            width: 2,
            ...(esForecast ? { dash: "dot" } : {}),
            ...(colorStatus ? { color: colorStatus } : {}),
          },
          marker: {
            // Treinta marcadores del tamaño de la anotación hacían ruido:
            // chicos en series largas (GRA-11).
            size: serie.points.length > 20 ? 4 : 6,
            ...(esForecast ? { symbol: "circle-open" } : {}),
            ...(colorStatus ? { color: colorStatus } : {}),
          },
        };
      }
    }
  });
}

function isTargetDotPlot(response: AnalyticsResponse): boolean {
  return (
    response.chart_type === "bar" &&
    response.visualization?.task === "ranking" &&
    response.visualization.target_status === "configured" &&
    response.visualization.target != null
  );
}

function buildTargetDotPlot(response: AnalyticsResponse): PlotlyTrace[] {
  const target = response.visualization?.target;
  const points = response.series[0]?.points ?? [];
  if (!target || points.length === 0) return [];
  const deltaByLabel = new Map(
    response.table_data.map((row) => [
      String(row.label ?? ""),
      Number(row.delta_to_target ?? Number(row.value ?? 0) - target.value),
    ]),
  );

  return [
    {
      type: "scatter",
      mode: "markers+text",
      x: points.map((point) => point.value),
      y: points.map((point) => point.label),
      text: points.map((point) => {
        const delta =
          deltaByLabel.get(point.label) ?? point.value - target.value;
        const sign = delta > 0 ? "+" : "";
        return `${point.value.toFixed(1)}% (${sign}${delta.toFixed(1)} pp)`;
      }),
      textposition: "middle right",
      cliponaxis: false,
      marker: { color: "#14A890", size: 10 },
      hovertemplate: "%{y}: %{x:.1f}%<extra></extra>",
      name: response.series[0]?.name || response.metric_name,
    } as unknown as PlotlyTrace,
  ];
}

interface StoreComparisonRow {
  label: string;
  value: number;
  role: string;
}

function storeComparisonRows(
  response: AnalyticsResponse,
): StoreComparisonRow[] {
  if (
    response.chart_type !== "bar" ||
    response.visualization?.task !== "comparison"
  ) {
    return [];
  }
  return response.table_data.flatMap((row) => {
    if (
      typeof row.label !== "string" ||
      typeof row.value !== "number" ||
      !Number.isFinite(row.value)
    ) {
      return [];
    }
    return [
      {
        label: row.label,
        value: row.value,
        role:
          typeof row.comparison_role === "string" ? row.comparison_role : "",
      },
    ];
  });
}

function isStoreDumbbell(response: AnalyticsResponse): boolean {
  const rows = storeComparisonRows(response);
  return (
    rows.length === 2 &&
    rows.filter((row) => row.role === "focus").length === 1 &&
    rows.filter((row) => row.role === "control").length === 1
  );
}

function buildStoreDumbbell(response: AnalyticsResponse): PlotlyTrace[] {
  const rows = storeComparisonRows(response).sort((left, right) =>
    left.role === "control" && right.role !== "control" ? -1 : 1,
  );
  if (rows.length !== 2) return [];
  const x = rows.map((row) => row.value);
  const y = rows.map(() => "Comparación");
  const unit = response.grounding?.unit;
  return [
    {
      type: "scatter",
      mode: "lines",
      x,
      y,
      line: { color: "#94A3B8", width: 3 },
      hoverinfo: "skip",
      showlegend: false,
      name: "Distancia",
    } as unknown as PlotlyTrace,
    {
      type: "scatter",
      mode: "markers+text",
      x,
      y,
      text: rows.map((row) => `${row.label}: ${formatoValor(row.value, unit)}`),
      textposition: ["bottom left", "top right"],
      cliponaxis: false,
      customdata: rows.map((row) => row.label),
      marker: {
        color: rows.map((row) =>
          row.role === "control" ? "#64748B" : "#14A890",
        ),
        size: 12,
      },
      hovertemplate: "%{customdata}: %{x:,.1f}<extra></extra>",
      showlegend: false,
      name: response.series[0]?.name || response.metric_name,
    } as unknown as PlotlyTrace,
  ];
}

function isStoreRanking(response: AnalyticsResponse): boolean {
  return storeComparisonRows(response).length >= 3;
}

function buildStoreRanking(response: AnalyticsResponse): PlotlyTrace[] {
  const rows = storeComparisonRows(response).sort(
    (left, right) =>
      right.value - left.value || left.label.localeCompare(right.label, "es"),
  );
  const unit = response.grounding?.unit;
  return [
    {
      type: "bar",
      orientation: "h",
      x: rows.map((row) => row.value),
      y: rows.map((row) => row.label),
      text: rows.map((row) => formatoValor(row.value, unit)),
      textposition: "outside",
      cliponaxis: false,
      // Sin color fijo: cada tienda toma el suyo al dibujar (colorearBarras).
      marker: { cornerradius: 4 },
      hovertemplate:
        unit === "percent"
          ? "%{y}: %{x:.1f}%<extra></extra>"
          : "%{y}: %{x:,.0f}<extra></extra>",
      showlegend: false,
      name: response.series[0]?.name || response.metric_name,
    } as unknown as PlotlyTrace,
  ];
}

/** Anotación del PICO para series temporales de una sola serie (etiqueta
 * directa selectiva: el extremo, no un número por punto). */
function buildPeakAnnotation(
  response: AnalyticsResponse,
): Array<Record<string, unknown>> {
  if (response.chart_type !== "line" || response.series.length !== 1) return [];
  const points = response.series[0].points;
  if (points.length < 5) return []; // en series cortas el eje alcanza
  const unit = response.grounding?.unit;
  const pico = points.reduce((a, b) => (b.value > a.value ? b : a));
  const valle = points.reduce((a, b) => (b.value < a.value ? b : a));
  // Pico y valle anotados (GRA-11): el texto del chat nombra los dos y la
  // gráfica solo marcaba el máximo.
  return [
    {
      x: pico.label,
      y: pico.value,
      text: formatoValor(pico.value, unit),
      showarrow: false,
      yanchor: "bottom",
      yshift: 8,
      font: { size: 11 },
    },
    ...(valle !== pico
      ? [
          {
            x: valle.label,
            y: valle.value,
            text: formatoValor(valle.value, unit),
            showarrow: false,
            yanchor: "top",
            yshift: -8,
            font: { size: 11 },
          },
        ]
      : []),
  ];
}

/** Línea punteada del promedio de una serie temporal (GRA-11). */
export function formaPromedio(
  response: AnalyticsResponse,
): Array<Record<string, unknown>> {
  if (response.chart_type !== "line" || response.series.length !== 1) return [];
  const points = response.series[0].points;
  if (points.length < 5) return [];
  const promedio = points.reduce((s, p) => s + p.value, 0) / points.length;
  return [
    {
      type: "line",
      xref: "paper",
      x0: 0,
      x1: 1,
      y0: promedio,
      y1: promedio,
      line: { color: "#94a3b8", width: 1, dash: "dot" },
    },
  ];
}

// Riesgo de faltante (predecir_faltante_hoy): el backend ya filtra a
// cobertura_dias < 1.5 (su propio umbral, ver prediction_rules.py); estos
// sub-buckets son solo de presentación, no re-derivan el criterio de riesgo.
// Sin emoji en el label: el color codifica la severidad en PredictionList.
// Los buckets también mantienen legibles respuestas Sankey históricas.
export const RIESGO_BUCKETS = [
  {
    max: 0.5,
    label: "Riesgo alto",
    accion: "Resurtir ahora",
    color: "#EF4444",
  },
  {
    max: 1.0,
    label: "Riesgo medio",
    accion: "Resurtir hoy",
    color: "#F59E0B",
  },
  { max: 1.5, label: "Riesgo bajo", accion: "Monitorear", color: "#10B981" },
] as const;

export function bucketFor(coberturaDias: number) {
  return RIESGO_BUCKETS.find((b) => coberturaDias < b.max) ?? RIESGO_BUCKETS[2];
}

const UMBRAL_COBERTURA_DIAS = 1.5;

/** Compatibilidad con respuestas históricas de predicción tipo Sankey.
 * La vista activa usa lista. Si un consumidor aún muestra este trace, su ancho
 * representa unidades necesarias para recuperar 1.5 días de cobertura, no
 * stock restante ni una pérdida monetaria inferida. */
function buildPredictionSankey(
  tableData: AnalyticsResponse["table_data"],
): PlotlyTrace[] {
  if (tableData.length === 0) return [];

  const nodeIndex = new Map<string, number>();
  const nodeLabels: string[] = [];
  const nodeColors: string[] = [];

  const nodeFor = (label: string, color: string): number => {
    const existing = nodeIndex.get(label);
    if (existing !== undefined) return existing;
    const idx = nodeLabels.length;
    nodeIndex.set(label, idx);
    nodeLabels.push(label);
    nodeColors.push(color);
    return idx;
  };

  const links: {
    source: number;
    target: number;
    value: number;
    color: string;
  }[] = [];
  const accionTotals = new Map<
    string,
    { idx: number; total: number; color: string }
  >();

  for (const row of tableData) {
    const nombre = String(row.nombre ?? row.articulo_id ?? "SKU");
    const stock = Number(row.stock_cierre ?? 0);
    const ventaDiaria = Number(row.venta_diaria ?? 0);
    const cobertura = Number(row.cobertura_dias ?? 0);
    const unidadesParaUmbral = Math.max(
      0,
      ventaDiaria * UMBRAL_COBERTURA_DIAS - stock,
    );
    if (stock <= 0 || ventaDiaria <= 0 || unidadesParaUmbral <= 0) continue;

    const bucket = bucketFor(cobertura);
    const skuIdx = nodeFor(nombre, "#14A890");
    const riesgoIdx = nodeFor(bucket.label, bucket.color);

    links.push({
      source: skuIdx,
      target: riesgoIdx,
      value: unidadesParaUmbral,
      color: bucket.color,
    });

    const accionEntry = accionTotals.get(bucket.accion) ?? {
      idx: nodeFor(bucket.accion, bucket.color),
      total: 0,
      color: bucket.color,
    };
    accionEntry.total += unidadesParaUmbral;
    accionTotals.set(bucket.accion, accionEntry);
  }

  // Un link riesgo -> acción por bucket que tuvo candidatos (agregado).
  for (const bucket of RIESGO_BUCKETS) {
    const riesgoIdx = nodeIndex.get(bucket.label);
    const accionEntry = accionTotals.get(bucket.accion);
    if (riesgoIdx === undefined || !accionEntry) continue;
    links.push({
      source: riesgoIdx,
      target: accionEntry.idx,
      value: accionEntry.total,
      color: bucket.color,
    });
  }

  return [
    {
      type: "sankey",
      name: "Unidades para recuperar 1.5 días de cobertura",
      node: {
        label: nodeLabels,
        color: nodeColors,
        pad: 12,
        thickness: 16,
      },
      link: {
        source: links.map((l) => l.source),
        target: links.map((l) => l.target),
        value: links.map((l) => l.value),
        color: links.map((l) => `${l.color}66`), // alpha para que no tape el nodo
      },
    },
  ];
}

/** Una serie en el tiempo con un solo punto: Plotly dibuja el eje de fecha
 * en milisegundos (P3.3 del reporte de QA, 2026-10-20). La cifra va
 * en el texto; una barra sola sí se dibuja. */
function serieDeUnPunto(response: AnalyticsResponse): boolean {
  if (response.chart_type !== "line" && response.chart_type !== "scatter") {
    return false;
  }
  return (
    response.series.length > 0 &&
    response.series.every((serie) => serie.points.length <= 1)
  );
}

/** true si el chart_type produce un trace de Plotly (no tabla, no vacío). */
export function isPlottableChartType(
  chartType: AnalyticsResponse["chart_type"],
): boolean {
  return (
    chartType === "line" ||
    chartType === "bar" ||
    chartType === "scatter" ||
    chartType === "sankey" ||
    chartType === "map"
  );
}

export function analyticsResponseToChartData(
  response: AnalyticsResponse,
): ChartData {
  const isSankey = response.chart_type === "sankey";
  const isMap = response.chart_type === "map";
  const targetDotPlot = isTargetDotPlot(response);
  const storeDumbbell = isStoreDumbbell(response);
  const storeRanking = isStoreRanking(response);
  const rankingHorizontal = esRankingHorizontal(response);
  const intervalBand = buildIntervalBand(response);
  const isIntraday =
    response.grounding?.capability === "intraday_sales" &&
    response.chart_type === "line";
  const intradayCutoff =
    typeof response.grounding?.cutoff_hour === "number"
      ? response.grounding.cutoff_hour
      : null;
  const intradayFuture =
    Array.isArray(response.grounding?.future_hours) &&
    response.grounding.future_hours.length > 0;
  const rawIntradayGap = response.grounding?.largest_hourly_gap;
  const intradayGap =
    rawIntradayGap &&
    typeof rawIntradayGap === "object" &&
    typeof (rawIntradayGap as Record<string, unknown>).hour === "number" &&
    typeof (rawIntradayGap as Record<string, unknown>).actual === "number" &&
    typeof (rawIntradayGap as Record<string, unknown>).delta === "number"
      ? (rawIntradayGap as {
          hour: number;
          actual: number;
          delta: number;
        })
      : null;
  const traces = storeDumbbell
    ? buildStoreDumbbell(response)
    : storeRanking
      ? buildStoreRanking(response)
      : targetDotPlot
        ? buildTargetDotPlot(response)
        : isSankey
          ? buildPredictionSankey(response.table_data)
          : isMap
            ? buildRegionChoropleth(response)
            : isPlottableChartType(response.chart_type) &&
                !serieDeUnPunto(response)
              ? [...intervalBand, ...seriesToTraces(response)]
              : [];
  const unit = response.grounding?.unit ?? undefined;
  const etiquetasCategoria = (response.series[0]?.points ?? []).map(
    (p) => p.label,
  );

  return {
    type: "chart",
    title: tituloGrafica(response),
    chart_status: response.error
      ? "error"
      : traces.length === 0 && response.table_data.length === 0
        ? "empty"
        : "success",
    response_text: response.response_text,
    plotly_config: {
      data: traces,
      layout: storeDumbbell
        ? {
            xaxis: {
              title: tituloEje(unidadLegible(unit)),
              ...ticksUnidad(unit),
              range: [
                0,
                Math.round(
                  Math.max(
                    1,
                    ...storeComparisonRows(response).map((row) => row.value),
                  ) *
                    1.1 *
                    10,
                ) / 10,
              ],
              fixedrange: true,
            },
            yaxis: {
              title: undefined,
              showticklabels: false,
              fixedrange: true,
            },
            showlegend: false,
            margin: { l: 24, r: 120, t: 40, b: 48 },
          }
        : storeRanking || rankingHorizontal
          ? {
              xaxis: {
                title: tituloEje(unidadLegible(unit)),
                ...ticksUnidad(unit),
                rangemode: "tozero",
              },
              // El orden del ranking (mayor arriba) se conserva invirtiendo el
              // eje; los deciles van en su orden, no por valor (GRA-5).
              yaxis: {
                title: undefined,
                autorange: "reversed",
                ...(ordenOrdinal(etiquetasCategoria)
                  ? {
                      categoryorder: "array",
                      categoryarray: ordenOrdinal(etiquetasCategoria),
                    }
                  : {}),
              },
              showlegend: false,
              margin: { l: margenParaEtiquetas(etiquetasCategoria), r: 90 },
              bargap: 0.35,
              height: alturaPorFilas(etiquetasCategoria.length),
            }
          : targetDotPlot
            ? {
                xaxis: {
                  title: tituloEje("%"),
                  ticksuffix: "%",
                  range: [
                    Math.max(
                      0,
                      Math.min(
                        ...response.series.flatMap((series) =>
                          series.points.map((point) => point.value),
                        ),
                      ) - 5,
                    ),
                    102,
                  ],
                },
                yaxis: { title: undefined, autorange: "reversed" },
                showlegend: false,
                margin: { r: 110 },
                shapes: [
                  {
                    type: "line",
                    x0: response.visualization?.target?.value,
                    x1: response.visualization?.target?.value,
                    y0: 0,
                    y1: 1,
                    yref: "paper",
                    line: { color: "#64748B", width: 2, dash: "dot" },
                  },
                ],
                annotations: [
                  {
                    x: response.visualization?.target?.value,
                    y: 1,
                    yref: "paper",
                    text: `${response.visualization?.target?.label}: ${response.visualization?.target?.value}%`,
                    showarrow: false,
                    yanchor: "bottom",
                  },
                ],
              }
            : isSankey
              ? {}
              : isMap
                ? {
                    // fitbounds al geojson local: sin tiles externos ni proyección
                    // global (solo México).
                    geo: {
                      fitbounds: "locations",
                      visible: true,
                      showframe: false,
                      showcoastlines: false,
                      showland: true,
                      landcolor: "#CBD5E1",
                      bgcolor: "rgba(0,0,0,0)",
                    },
                    margin: { t: 8, b: 8, l: 8, r: 8 },
                  }
                : {
                    xaxis: {
                      title: tituloEje(
                        isIntraday
                          ? "Hora · America/Mexico_City"
                          : (response.grounding?.dimension ?? undefined),
                      ),
                      ...(isIntraday
                        ? {
                            type: "category",
                            categoryorder: "array",
                            categoryarray: Array.from(
                              { length: 24 },
                              (_, hour) => String(hour),
                            ),
                            tickvals: Array.from({ length: 24 }, (_, hour) =>
                              String(hour),
                            ),
                            ticktext: Array.from(
                              { length: 24 },
                              (_, hour) => `${hour}:00`,
                            ),
                          }
                        : {}),
                    },
                    yaxis: {
                      title: tituloEje(unidadLegible(unit)),
                      ...ticksUnidad(unit),
                    },
                    barmode:
                      response.visualization?.task === "composition"
                        ? "stack"
                        : response.series.length > 1
                          ? "group"
                          : undefined,
                    // Una serie no lleva leyenda: el título/métrica ya la nombra.
                    showlegend: response.series.length > 1,
                    // Barras delgadas con aire (marcas silenciosas, no bloques);
                    // con dos o tres categorías, más aire aún (GRA-9).
                    bargap: etiquetasCategoria.length <= 3 ? 0.6 : 0.35,
                    shapes: [
                      ...formaPromedio(response),
                      ...(isIntraday && intradayCutoff != null
                        ? [
                            {
                              type: "line",
                              x0: String(intradayCutoff),
                              x1: String(intradayCutoff),
                              y0: 0,
                              y1: 1,
                              yref: "paper",
                              line: {
                                color: "#64748B",
                                width: 1.5,
                                dash: "dash",
                              },
                            },
                            ...(intradayFuture
                              ? [
                                  {
                                    type: "rect",
                                    x0: intradayCutoff + 0.5,
                                    x1: 23.5,
                                    y0: 0,
                                    y1: 1,
                                    yref: "paper",
                                    fillcolor: "rgba(100, 116, 139, 0.10)",
                                    line: { width: 0 },
                                    layer: "below",
                                  },
                                ]
                              : []),
                          ]
                        : response.grounding?.capability ===
                              "demand_forecast" &&
                            response.grounding.forecast_cutoff
                          ? [
                              {
                                type: "line",
                                x0: response.grounding.forecast_cutoff,
                                x1: response.grounding.forecast_cutoff,
                                y0: 0,
                                y1: 1,
                                yref: "paper",
                                line: {
                                  color: "#64748B",
                                  width: 1.5,
                                  dash: "dash",
                                },
                              },
                            ]
                          : []),
                    ],
                    annotations: [
                      ...buildPeakAnnotation(response),
                      ...anotacionesDelta(response),
                      ...(isIntraday && intradayCutoff != null
                        ? [
                            {
                              x: String(intradayCutoff),
                              y: 1,
                              yref: "paper",
                              text: `Corte ${String(intradayCutoff).padStart(2, "0")}:00`,
                              showarrow: false,
                              yanchor: "bottom",
                            },
                          ]
                        : []),
                      ...(isIntraday && intradayGap != null
                        ? [
                            {
                              x: String(intradayGap.hour),
                              y: intradayGap.actual,
                              text: `Mayor brecha: ${intradayGap.delta >= 0 ? "+" : ""}${formatoValor(intradayGap.delta, unit)}`,
                              showarrow: false,
                              yanchor: "bottom",
                              yshift: 8,
                              font: { size: 11 },
                            },
                          ]
                        : []),
                      ...(response.grounding?.capability ===
                        "demand_forecast" && response.grounding.forecast_cutoff
                        ? [
                            {
                              x: response.grounding.forecast_cutoff,
                              y: 1,
                              yref: "paper",
                              text: "Corte observado",
                              showarrow: false,
                              yanchor: "bottom",
                            },
                          ]
                        : []),
                    ],
                  },
      config: { responsive: true, displayModeBar: false },
    },
    data_as_of: response.data_as_of ?? undefined,
    source: response.grounding?.source ?? "retail-advisor",
    analytics: response,
  };
}
