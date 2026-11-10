/**
 * Preset de layout de Plotly compartido por todos los charts del canvas.
 *
 * Centraliza el look & feel (colores, fuente, márgenes) para que agregar un
 * chart nuevo no implique reinventar el estilo — coincide con los design
 * tokens de globals.css (mismo teal/superficie que el resto de la UI).
 */
import type { Layout } from "plotly.js";

/**
 * Colores de las series, en orden fijo: el teal de la marca primero y luego
 * tonos que se distinguen entre sí (Equipo, 2026-10-22: barras y líneas
 * comparativas de diferente color). Validada con el validador del skill
 * dataviz contra la superficie de cada tema: banda de luminosidad, croma,
 * separación para daltonismo (ΔE ≥ 8.5) y visión normal (ΔE ≥ 19). La de
 * antes ponía teal y celeste juntos (ΔE 12: se confundían). En claro, el
 * amarillo y el magenta quedan bajo 3:1 contra el fondo; los compensan las
 * etiquetas de valor y la vista de tabla.
 */
export const PALETA_SERIES = {
  light: [
    "#0f8a76",
    "#eb6834",
    "#6250d6",
    "#eda100",
    "#e87ba4",
    "#2a78d6",
    "#e34948",
    "#008300",
  ],
  dark: [
    "#14A890",
    "#d95926",
    "#9085e9",
    "#c98500",
    "#d55181",
    "#3987e5",
    "#e66767",
    "#008300",
  ],
} as const;

const PALETTE = {
  light: {
    paper: "#F9FAFB",
    plot: "#F9FAFB",
    font: "#111827",
    muted: "#6B7280",
    grid: "#E5E7EB",
    colorway: PALETA_SERIES.light,
  },
  dark: {
    paper: "#1e293b",
    plot: "#1e293b",
    font: "#F9FAFB",
    muted: "#94a3b8",
    // Un paso sobre la superficie (grid recesivo, hairline): el dato es lo
    // único que puede ser "ruidoso" (benchmark NYT/Datawrapper).
    grid: "#2b3649",
    colorway: PALETA_SERIES.dark,
  },
} as const;

export function getPlotlyLayoutTheme(theme: "light" | "dark"): Partial<Layout> {
  const c = PALETTE[theme];

  return {
    paper_bgcolor: c.paper,
    plot_bgcolor: c.plot,
    font: { family: "Inter, system-ui, sans-serif", size: 12, color: c.font },
    colorway: [...c.colorway],
    margin: { t: 32, r: 16, b: 40, l: 48 },
    // es-MX: decimal "." y miles "," (57,422 — como las piezas del NYT).
    separators: ".,",
    hovermode: "x unified",
    showlegend: true,
    legend: {
      orientation: "h",
      x: 0,
      y: 1.15,
      font: { color: c.muted, size: 11 },
    },
    xaxis: {
      gridcolor: c.grid,
      linecolor: c.grid,
      tickfont: { color: c.muted },
      zeroline: false,
    },
    yaxis: {
      gridcolor: c.grid,
      linecolor: c.grid,
      tickfont: { color: c.muted },
      zeroline: false,
    },
  };
}

/** Merge de un nivel: el tema pone la base, layout de datos gana en leaf keys
 * ya seteados (title de eje, barmode) sin perder el resto del tema. */
export function mergePlotlyLayout(
  theme: Partial<Layout>,
  dataLayout: Partial<Layout>,
): Partial<Layout> {
  // Charts geo (choropleth): NO llevar ejes cartesianos ni hover "x unified"
  // del tema — Plotly truena en el resize responsivo (_axisMatchGroups de
  // undefined) cuando el layout declara xaxis/yaxis sin traces cartesianos.
  if (dataLayout.geo) {
    const { xaxis: _x, yaxis: _y, hovermode: _h, ...base } = theme;
    return {
      ...base,
      ...dataLayout,
      legend: { ...theme.legend, ...dataLayout.legend },
    };
  }
  return {
    ...theme,
    ...dataLayout,
    xaxis: { ...theme.xaxis, ...dataLayout.xaxis },
    yaxis: { ...theme.yaxis, ...dataLayout.yaxis },
    legend: { ...theme.legend, ...dataLayout.legend },
  };
}

type Traza = Record<string, unknown>;

/** Una sola serie de barras: cada barra con su color de la paleta del tema,
 * en el orden de los datos, repitiendo desde el primero si hay más de ocho.
 * Decisión del equipo del 2026-10-22, confirmada el 2026-11-08 al revisar el
 * video de producto: GRA-2 había puesto un solo tono con el líder resaltado
 * y todas las gráficas se veían iguales; se regresa a un color por barra.
 * Con varias series el color ya identifica cada serie (colorway) y no se
 * toca; tampoco el rojo de alerta que el adaptador pone a las medidas donde
 * más es peor. */
export function colorearBarras<T>(data: T[], theme: "light" | "dark"): T[] {
  const barras = data.filter((traza) => (traza as Traza).type === "bar");
  if (barras.length !== 1) return data;
  const barra = barras[0] as Traza;
  const marker = (barra.marker ?? {}) as Traza;
  if (marker.color !== undefined) return data;
  const horizontal = barra.orientation === "h";
  const categorias = (horizontal ? barra.y : barra.x) as unknown[] | undefined;
  if (!Array.isArray(categorias) || categorias.length === 0) return data;
  const paleta = PALETA_SERIES[theme];
  const color = categorias.map((_, i) => paleta[i % paleta.length]);
  return data.map((traza) =>
    traza === barras[0]
      ? ({ ...barra, marker: { ...marker, color } } as T)
      : traza,
  );
}
