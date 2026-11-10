import {
  PALETA_SERIES,
  colorearBarras,
  getPlotlyLayoutTheme,
} from "../plotly-theme";

// Equipo (2026-10-22): "cuando sean gráficas de barra, o varias líneas
// comparativas, ponlas de diferente color". En producción las barras de una
// sola serie (agosto contra septiembre, ventas por categoría, ranking de
// tiendas) salían todas en teal, y las dos primeras líneas de un comparativo
// eran teal y celeste (ΔE 12, se confunden aun con visión normal).
const marcador = (traza: unknown) =>
  (traza as { marker: Record<string, unknown> }).marker;

describe("colores de las series", () => {
  const barras = (n: number, extra: Record<string, unknown> = {}) => ({
    type: "bar",
    x: Array.from({ length: n }, (_, i) => `barra ${i + 1}`),
    y: Array.from({ length: n }, (_, i) => i + 1),
    marker: { cornerradius: 4 },
    ...extra,
  });

  // GRA-2 (2026-11-08) había puesto un solo tono con el líder resaltado;
  // Se revirtió el mismo día al ver todas las gráficas iguales en el
  // video de producto: cada barra con su color de la paleta.
  it("una sola serie de barras: cada barra con su color de la paleta, en orden", () => {
    for (const tema of ["light", "dark"] as const) {
      const [traza] = colorearBarras([barras(3)], tema);
      const marker = marcador(traza);
      expect(marker.color).toEqual(PALETA_SERIES[tema].slice(0, 3));
      expect(marker.cornerradius).toBe(4);
    }
  });

  it("con más de ocho barras la paleta se repite desde el primer color", () => {
    const [traza] = colorearBarras([barras(10)], "dark");
    const colores = marcador(traza).color as string[];
    expect(colores).toHaveLength(10);
    expect(colores.slice(0, 8)).toEqual([...PALETA_SERIES.dark]);
    expect(colores.slice(8)).toEqual(PALETA_SERIES.dark.slice(0, 2));
  });

  it("barras horizontales: el color sigue el orden de las categorías (eje y)", () => {
    const horizontal = {
      type: "bar",
      orientation: "h",
      x: [5, 4],
      y: ["Mundo E", "Polanco"],
      marker: {},
    };
    const [traza] = colorearBarras([horizontal], "light");
    expect(marcador(traza).color).toEqual(PALETA_SERIES.light.slice(0, 2));
  });

  it("el rojo de alerta (más es peor) se respeta", () => {
    const alerta = barras(3, { marker: { color: "#EF4444" } });
    const [traza] = colorearBarras([alerta], "dark");
    expect(marcador(traza).color).toBe("#EF4444");
  });

  it("varias series de barras: el color identifica la serie, no la barra", () => {
    const data = [
      barras(3, { name: "agosto" }),
      barras(3, { name: "septiembre" }),
    ];
    const resultado = colorearBarras(data, "dark");
    for (const traza of resultado) {
      expect(marcador(traza)).not.toHaveProperty("color");
    }
  });

  it("las líneas no se tocan: las colorea la paleta del tema por serie", () => {
    const linea = { type: "scatter", mode: "lines+markers", x: [1], y: [2] };
    expect(colorearBarras([linea], "dark")).toEqual([linea]);
  });

  it("la paleta del tema es la de las series, con los dos primeros colores bien distintos", () => {
    for (const tema of ["light", "dark"] as const) {
      expect(getPlotlyLayoutTheme(tema).colorway).toEqual([
        ...PALETA_SERIES[tema],
      ]);
      expect(PALETA_SERIES[tema]).toHaveLength(8);
      expect(new Set(PALETA_SERIES[tema]).size).toBe(8);
    }
    // Teal de la marca y naranja: ya no teal y celeste.
    expect(PALETA_SERIES.dark.slice(0, 2)).toEqual(["#14A890", "#d95926"]);
  });
});
