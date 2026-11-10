import {
  analyticsResponseToChartData,
  isPlottableChartType,
  bucketFor,
  formatoValor,
  unidadLegible,
  acortarEtiqueta,
  margenParaEtiquetas,
  ordenOrdinal,
  ticksUnidad,
  tituloEje,
  esRankingHorizontal,
  envolverEtiqueta,
  tituloGrafica,
  alturaPorFilas,
} from "../analytics-to-chart-data";
import { getPlotlyLayoutTheme, mergePlotlyLayout } from "../plotly-theme";
import type { Layout as PlotlyLayout } from "plotly.js";
import type { AnalyticsResponse } from "@/lib/contracts";

function buildResponse(
  overrides: Partial<AnalyticsResponse> = {},
): AnalyticsResponse {
  return {
    metric_name: "disponibilidad",
    chart_type: "bar",
    series: [
      {
        name: "Inventario de sistema con existencia",
        points: [
          { label: "control", value: 82.89, dimension: null },
          { label: "mundo_e", value: 82.78, dimension: null },
        ],
      },
    ],
    table_data: [],
    response_text: "Disponibilidad estable.",
    grounding: {
      source: "retail-advisor",
      unit: "percent",
      dimension: "tienda",
    },
    error: null,
    schema_version: "1",
    data_as_of: "2026-06-30",
    freshness: "day_closed",
    ...overrides,
  };
}

describe("defaults editoriales (card dataviz-nyt-canvas-retail)", () => {
  const puntos = (n: number) =>
    Array.from({ length: n }, (_, i) => ({
      label: `item ${i}`,
      value: 1000 + i * 137,
      dimension: null,
    }));

  it("una serie: sin leyenda; dos series: con leyenda", () => {
    const una = analyticsResponseToChartData(buildResponse({}));
    expect(
      (una.plotly_config.layout as Record<string, unknown>).showlegend,
    ).toBe(false);

    const dos = analyticsResponseToChartData(
      buildResponse({
        series: [
          { name: "Mundo E", points: puntos(3) },
          { name: "Control", points: puntos(3) },
        ],
      }),
    );
    expect(
      (dos.plotly_config.layout as Record<string, unknown>).showlegend,
    ).toBe(true);
  });

  it("ranking chico de una serie: etiqueta directa en la punta de cada barra", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        chart_type: "bar",
        grounding: { source: "retail-advisor", unit: "count" },
        series: [{ name: "Venta", points: puntos(8) }],
      }),
    );
    const trace = chart.plotly_config.data[0] as Record<string, unknown>;
    expect(trace.textposition).toBe("outside");
    expect((trace.text as string[])[0]).toBe("1,000"); // miles con coma
  });

  it("ranking largo por artículo: barras horizontales, nombre completo en hover", () => {
    // Card 2026-09-03__FEAT__canvas-etiquetas-legibles-y-frescura: un top 10
    // vertical truncaba todos los nombres a "Refresco C…".
    const articulos = Array.from({ length: 10 }, (_, i) => ({
      label: `Marca ${i} 600 Ml`,
      value: 500 - i * 40,
      dimension: null,
    }));
    const chart = analyticsResponseToChartData(
      buildResponse({
        chart_type: "bar",
        grounding: { source: "retail-advisor", unit: "count" },
        visualization: {
          task: "ranking",
          title: "Venta por artículo: Refrescos y sodas",
        } as AnalyticsResponse["visualization"],
        series: [{ name: "Venta", points: articulos }],
        table_data: articulos.map((p) => ({
          label: p.label,
          value: p.value,
          label_completo: `Refresco ${p.label} Pet Nr`,
        })),
      }),
    );
    const trace = chart.plotly_config.data[0] as Record<string, unknown>;
    expect(trace.orientation).toBe("h");
    expect((trace.y as string[])[0]).toBe("Marca 0 600 Ml"); // eje = etiqueta corta
    expect((trace.x as number[])[0]).toBe(500);
    expect((trace.customdata as string[])[0]).toBe(
      "Refresco Marca 0 600 Ml Pet Nr",
    );
    expect(String(trace.hovertemplate)).toContain("%{customdata}");
    const layout = chart.plotly_config.layout as Record<string, any>;
    expect(layout.yaxis.autorange).toBe("reversed");

    // Con pocas barras sigue vertical.
    const chico = analyticsResponseToChartData(
      buildResponse({
        chart_type: "bar",
        visualization: {
          task: "ranking",
          title: "x",
        } as AnalyticsResponse["visualization"],
        series: [{ name: "Venta", points: articulos.slice(0, 5) }],
      }),
    );
    expect(
      (chico.plotly_config.data[0] as Record<string, unknown>).orientation,
    ).toBeUndefined();
  });

  it("ranking largo o comparativa: SIN número en cada punto", () => {
    const largo = analyticsResponseToChartData(
      buildResponse({
        chart_type: "bar",
        series: [{ name: "Venta", points: puntos(20) }],
      }),
    );
    expect(
      (largo.plotly_config.data[0] as Record<string, unknown>).text,
    ).toBeUndefined();

    const comparativa = analyticsResponseToChartData(
      buildResponse({
        chart_type: "bar",
        series: [
          { name: "Mundo E", points: puntos(3) },
          { name: "Control", points: puntos(3) },
        ],
      }),
    );
    expect(
      (comparativa.plotly_config.data[0] as Record<string, unknown>).text,
    ).toBeUndefined();
  });

  it("serie temporal de una serie: anota SOLO el pico", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        chart_type: "line",
        grounding: { source: "retail-advisor", unit: "count" },
        series: [{ name: "Venta por hora", points: puntos(14) }],
      }),
    );
    const annotations = (chart.plotly_config.layout as Record<string, unknown>)
      .annotations as Array<Record<string, unknown>>;
    // GRA-11 (2026-11-08): pico y valle, nunca un número en cada punto.
    expect(annotations).toHaveLength(2);
    expect(annotations[0].x).toBe("item 13"); // el máximo
    expect(annotations[0].text).toBe("2,781");
    expect(annotations[1].text).toBe("1,000"); // el mínimo
    const shapes = (chart.plotly_config.layout as Record<string, unknown>)
      .shapes as Array<Record<string, unknown>>;
    expect(shapes).toHaveLength(1); // el promedio, punteado
    expect(shapes[0].line).toMatchObject({ dash: "dot" });
  });

  it("venta intradía marca corte y futuro sin imputar horas como cero", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        metric_name: "venta_hora",
        chart_type: "line",
        freshness: "intraday",
        grounding: {
          source: "retail-advisor",
          capability: "intraday_sales",
          unit: "count",
          cutoff_hour: 14,
          partial_hour: 14,
          future_hours: [15, 16, 17, 18, 19, 20, 21, 22, 23],
          largest_hourly_gap: {
            hour: 14,
            actual: 40,
            benchmark: 35,
            delta: 5,
          },
        },
        series: [
          {
            name: "Mundo E · 2026-07-31",
            points: [
              { label: "10", value: 20 },
              { label: "14", value: 40 },
            ],
          },
          {
            name: "Mismo día de semana anterior · 2026-07-24",
            points: [
              { label: "10", value: 10 },
              { label: "14", value: 35 },
            ],
          },
        ],
      }),
    );

    const layout = chart.plotly_config.layout as Record<string, unknown>;
    const xaxis = layout.xaxis as Record<string, unknown>;
    const shapes = layout.shapes as Array<Record<string, unknown>>;
    const annotations = layout.annotations as Array<Record<string, unknown>>;
    expect(xaxis.categoryarray).toEqual(
      Array.from({ length: 24 }, (_, hour) => String(hour)),
    );
    expect(shapes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ type: "line", x0: "14", x1: "14" }),
        expect.objectContaining({ type: "rect", x0: 14.5, x1: 23.5 }),
      ]),
    );
    expect(annotations).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ x: "14", text: "Corte 14:00" }),
        expect.objectContaining({ x: "14", text: "Mayor brecha: +5" }),
      ]),
    );
    expect(chart.plotly_config.data[0].x).toEqual(["10", "14"]);
    expect(chart.plotly_config.data[0].y).toEqual([20, 40]);
  });

  it("higher_is_better=false usa rojo de status sin hardcodear la métrica", () => {
    const diasSinVenta = analyticsResponseToChartData(
      buildResponse({
        chart_type: "bar",
        grounding: {
          source: "retail-advisor",
          metric: "dias_sin_venta",
          unit: "count",
        },
        visualization: {
          task: "ranking",
          title: "Días sin venta",
          higher_is_better: false,
        },
        series: [{ name: "Días sin venta", points: puntos(3) }],
      }),
    );
    const marker = (
      diasSinVenta.plotly_config.data[0] as Record<string, unknown>
    ).marker as Record<string, unknown>;
    expect(marker.color).toBe("#EF4444");

    const comparativa = analyticsResponseToChartData(
      buildResponse({
        chart_type: "bar",
        grounding: {
          source: "retail-advisor",
          metric: "faltante",
          unit: "count",
        },
        visualization: {
          task: "comparison",
          title: "Faltante por tienda",
          higher_is_better: false,
        },
        series: [
          { name: "Mundo E", points: puntos(3) },
          { name: "Control", points: puntos(3) },
        ],
      }),
    );
    const markerComp = (
      comparativa.plotly_config.data[0] as Record<string, unknown>
    ).marker as Record<string, unknown>;
    expect(markerComp.color).toBeUndefined(); // 2 series: color = identidad
  });

  it("hover y unidades legibles por tipo de unidad", () => {
    const pct = analyticsResponseToChartData(buildResponse({}));
    const tracePct = pct.plotly_config.data[0] as Record<string, unknown>;
    expect(tracePct.hovertemplate).toContain("%{y:.1f}%");
    expect(
      (
        (pct.plotly_config.layout as Record<string, unknown>).yaxis as Record<
          string,
          unknown
        >
      ).title,
    ).toEqual({ text: "%" });

    expect(formatoValor(57422, "count")).toBe("57,422");
    expect(formatoValor(13489.5, "currency")).toBe("$13,489.5");
    expect(formatoValor(84.57, "percent")).toBe("84.6%");
    expect(unidadLegible("count")).toBe("unidades");
    expect(unidadLegible("currency")).toBe("MXN");
  });

  it("el tema trae separadores es-MX (decimal punto, miles coma)", () => {
    const tema = getPlotlyLayoutTheme("dark") as Record<string, unknown>;
    expect(tema.separators).toBe(".,");
  });
});

describe("disponibilidad con meta opcional", () => {
  it("con meta construye dot plot, brechas visibles y línea objetivo", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        metric_name: "disponibilidad",
        chart_type: "bar",
        series: [
          {
            name: "Inventario de sistema con existencia",
            points: [
              { label: "Bebidas", value: 91, dimension: "categoria" },
              { label: "Botanas", value: 95.5, dimension: "categoria" },
              { label: "Lácteos", value: 98.2, dimension: "categoria" },
            ],
          },
        ],
        table_data: [
          { label: "Bebidas", value: 91, delta_to_target: -5 },
          { label: "Botanas", value: 95.5, delta_to_target: -0.5 },
          { label: "Lácteos", value: 98.2, delta_to_target: 2.2 },
        ],
        visualization: {
          task: "ranking",
          title: "Inventario de sistema con existencia",
          higher_is_better: true,
          target_status: "configured",
          target: {
            label: "Objetivo acordado",
            value: 96,
            source: "Comité operativo",
            version: "2026-Q3",
          },
        },
      }),
    );

    const trace = chart.plotly_config.data[0] as Record<string, unknown>;
    expect(trace.type).toBe("scatter");
    expect(trace.mode).toBe("markers+text");
    expect(trace.x).toEqual([91, 95.5, 98.2]);
    expect(trace.y).toEqual(["Bebidas", "Botanas", "Lácteos"]);
    expect(trace.text).toEqual([
      "91.0% (-5.0 pp)",
      "95.5% (-0.5 pp)",
      "98.2% (+2.2 pp)",
    ]);
    expect(chart.plotly_config.layout.shapes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ type: "line", x0: 96, x1: 96 }),
      ]),
    );
  });

  it("sin meta conserva barras neutrales sin línea ni color de cumplimiento", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        metric_name: "disponibilidad",
        chart_type: "bar",
        series: [
          {
            name: "Inventario de sistema con existencia",
            points: [{ label: "Bebidas", value: 91, dimension: "categoria" }],
          },
        ],
        visualization: {
          task: "ranking",
          title: "Inventario de sistema con existencia",
          higher_is_better: true,
          target_status: "not_configured",
        },
      }),
    );

    const trace = chart.plotly_config.data[0] as Record<string, unknown>;
    expect(trace.type).toBe("bar");
    expect(trace.marker).not.toHaveProperty("color");
    expect(chart.plotly_config.layout.shapes ?? []).toHaveLength(0);
  });
});

// P3.3 del reporte de QA (2026-10-20): con un solo dato, la línea
// mostraba el eje de tiempo en milisegundos. La cifra va en el texto.
describe("una serie en el tiempo con un solo punto", () => {
  it("no produce trazo: el panel muestra el texto", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        chart_type: "line",
        grounding: { source: "retail-advisor", unit: "count" },
        series: [{ name: "Venta", points: [{ label: "2026-09-30", value: 152063, dimension: null }] }],
        response_text: "La venta del 30 de septiembre de 2026 fue de 152,063 piezas.",
      }),
    );
    expect(chart.plotly_config.data).toHaveLength(0);
    expect(chart.chart_status).toBe("empty");
  });

  it("una barra sola sí se dibuja", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        series: [{ name: "Venta", points: [{ label: "Centro", value: 1, dimension: null }] }],
      }),
    );
    expect(chart.plotly_config.data).toHaveLength(1);
  });
});

describe("isPlottableChartType", () => {
  it("returns true for line/bar/scatter", () => {
    expect(isPlottableChartType("line")).toBe(true);
    expect(isPlottableChartType("bar")).toBe(true);
    expect(isPlottableChartType("scatter")).toBe(true);
  });

  it("returns false for table/none", () => {
    expect(isPlottableChartType("table")).toBe(false);
    expect(isPlottableChartType("none")).toBe(false);
  });
});

describe("analyticsResponseToChartData", () => {
  it("maps a bar chart_type to a single Plotly bar trace per series", () => {
    const chart = analyticsResponseToChartData(buildResponse());

    expect(chart.chart_status).toBe("success");
    expect(chart.plotly_config.data).toHaveLength(1);
    expect(chart.plotly_config.data[0].type).toBe("bar");
    expect(chart.plotly_config.data[0].x).toEqual(["control", "mundo_e"]);
    expect(chart.plotly_config.data[0].y).toEqual([82.89, 82.78]);
  });

  it("usa dumbbell con eje desde cero para una tienda foco y un control", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        metric_name: "venta_hora",
        visualization: {
          task: "comparison",
          title: "Venta por hora",
          headline: "Mundo E está 1.0% sobre Control Norte",
          benchmark: { label: "Control Norte", value: 100 },
        },
        grounding: {
          source: "retail-advisor",
          unit: "count",
          dimension: "tienda",
          period: "last_7_days",
        },
        series: [
          {
            name: "Venta por hora",
            points: [
              { label: "Control Norte", value: 100, dimension: null },
              { label: "Mundo E", value: 101, dimension: null },
            ],
          },
        ],
        table_data: [
          {
            label: "Control Norte",
            value: 100,
            comparison_role: "control",
          },
          {
            label: "Mundo E",
            value: 101,
            comparison_role: "focus",
            delta_absolute: 1,
            delta_percent: 1,
          },
        ],
      }),
    );

    expect(chart.plotly_config.data).toHaveLength(2);
    expect(chart.plotly_config.data[0]).toMatchObject({
      type: "scatter",
      mode: "lines",
      x: [100, 101],
    });
    expect(chart.plotly_config.data[1]).toMatchObject({
      type: "scatter",
      mode: "markers+text",
      text: ["Control Norte: 100", "Mundo E: 101"],
    });
    expect(chart.plotly_config.layout.xaxis).toMatchObject({
      range: [0, 111.1],
      title: { text: "unidades" },
    });
  });

  it("usa ranking horizontal ordenado para tres o más tiendas", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        visualization: { task: "comparison", title: "Venta por tienda" },
        grounding: {
          source: "retail-advisor",
          unit: "count",
          dimension: "tienda",
          period: "last_7_days",
        },
        series: [
          {
            name: "Venta",
            points: [
              { label: "Tienda con nombre largo", value: 90, dimension: null },
              { label: "Mundo E", value: 110, dimension: null },
              { label: "Control Norte", value: 100, dimension: null },
            ],
          },
        ],
        table_data: [
          { label: "Tienda con nombre largo", value: 90 },
          { label: "Mundo E", value: 110 },
          { label: "Control Norte", value: 100 },
        ],
      }),
    );

    expect(chart.plotly_config.data).toHaveLength(1);
    expect(chart.plotly_config.data[0]).toMatchObject({
      type: "bar",
      orientation: "h",
      x: [110, 100, 90],
      y: ["Mundo E", "Control Norte", "Tienda con nombre largo"],
    });
    // Sin color fijo: al dibujar, cada tienda toma su color de la paleta del
    // tema (colorearBarras; Equipo, 2026-10-22).
    expect(
      (chart.plotly_config.data[0] as { marker: Record<string, unknown> })
        .marker,
    ).not.toHaveProperty("color");
    expect(chart.plotly_config.layout.xaxis).toMatchObject({
      rangemode: "tozero",
      title: { text: "unidades" },
    });
    expect(chart.plotly_config.layout.yaxis).toMatchObject({
      autorange: "reversed",
    });
  });

  it("maps line chart_type to a lines+markers scatter trace", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({ chart_type: "line" }),
    );

    expect(chart.plotly_config.data[0].type).toBe("scatter");
    expect(chart.plotly_config.data[0].mode).toBe("lines+markers");
  });

  it("sets barmode=group when there is more than one series", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        series: [
          { name: "A", points: [{ label: "x", value: 1, dimension: null }] },
          { name: "B", points: [{ label: "x", value: 2, dimension: null }] },
        ],
      }),
    );

    expect(chart.plotly_config.layout.barmode).toBe("group");
  });

  it("dashes the forecast series and keeps the real one solid (role)", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        metric_name: "forecast_demanda",
        chart_type: "line",
        series: [
          {
            name: "Venta real (unidades/día)",
            role: "real",
            points: [
              { label: "2026-07-20", value: 500, dimension: null },
              { label: "2026-07-21", value: 540, dimension: null },
            ],
          },
          {
            name: "Forecast · baseline_local",
            role: "forecast",
            points: [
              { label: "2026-07-22", value: 560, dimension: null },
              { label: "2026-07-23", value: 610, dimension: null },
            ],
          },
        ],
      }),
    );
    const [real, forecast] = chart.plotly_config.data;
    expect(real.line?.dash).toBeUndefined();
    expect(forecast.line?.dash).toBe("dot");
    expect(forecast.marker?.symbol).toBe("circle-open");
  });

  it("renders only a complete valid interval and marks the forecast cutoff", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        metric_name: "forecast_demanda",
        chart_type: "line",
        grounding: {
          source: "retail-advisor",
          unit: "count",
          capability: "demand_forecast",
          proveedor: "provider_test",
          forecast_cutoff: "2026-07-20",
        },
        series: [
          {
            name: "Venta real",
            role: "real",
            points: [{ label: "2026-07-20", value: 90 }],
          },
          {
            name: "Forecast",
            role: "forecast",
            points: [
              {
                label: "2026-07-21",
                value: 100,
                interval_low: 90,
                interval_high: 110,
              },
              {
                label: "2026-07-22",
                value: 105,
                interval_low: 95,
                interval_high: 115,
              },
            ],
          },
        ],
      }),
    );

    expect(chart.plotly_config.data).toHaveLength(4);
    expect((chart.plotly_config.data[1] as Record<string, unknown>).fill).toBe(
      "tonexty",
    );
    const layout = chart.plotly_config.layout as Record<string, unknown>;
    expect(layout.shapes).toHaveLength(1);
    expect(
      (layout.annotations as Array<Record<string, unknown>>).some(
        (annotation) => annotation.text === "Corte observado",
      ),
    ).toBe(true);
  });

  it("omits the entire band when one forecast limit is missing", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        chart_type: "line",
        series: [
          {
            name: "Forecast",
            role: "forecast",
            points: [
              {
                label: "2026-07-21",
                value: 100,
                interval_low: 90,
                interval_high: 110,
              },
              { label: "2026-07-22", value: 105 },
            ],
          },
        ],
      }),
    );
    expect(chart.plotly_config.data).toHaveLength(1);
  });

  it("produces no traces for chart_type=table (renders as table instead)", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        chart_type: "table",
        table_data: [{ tienda: "mundo_e" }],
      }),
    );

    expect(chart.plotly_config.data).toHaveLength(0);
    expect(chart.chart_status).toBe("success"); // hay table_data, no está vacío
  });

  it("marks chart_status=empty when there is neither series data nor table_data", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({ chart_type: "none", series: [], table_data: [] }),
    );

    expect(chart.chart_status).toBe("empty");
  });

  it("marks chart_status=error when the response carries an error", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({ error: "sin datos cargados" }),
    );

    expect(chart.chart_status).toBe("error");
  });

  it("carries grounding/freshness/data_as_of into the chart transport shape", () => {
    const chart = analyticsResponseToChartData(buildResponse());

    expect(chart.data_as_of).toBe("2026-06-30");
    expect(chart.source).toBe("retail-advisor");
    expect(chart.analytics?.freshness).toBe("day_closed");
  });

  it("uses editorial visualization headline/title before technical metric_name", () => {
    const headline = analyticsResponseToChartData(
      buildResponse({
        metric_name: "venta_hora",
        visualization: {
          task: "comparison",
          title: "Venta contra tienda control",
          headline: "Mundo E está 1.1% debajo del control",
        },
      }),
    );
    const title = analyticsResponseToChartData(
      buildResponse({
        metric_name: "venta_hora",
        visualization: {
          task: "comparison",
          title: "Venta contra tienda control",
        },
      }),
    );
    const fallback = analyticsResponseToChartData(
      buildResponse({ metric_name: "venta_hora" }),
    );

    expect(headline.title).toBe("Mundo E está 1.1% debajo del control");
    expect(title.title).toBe("Venta contra tienda control");
    expect(fallback.title).toBe("venta_hora por tienda"); // GRA-7: sin título del plugin, con la dimensión
    expect(headline.analytics?.metric_name).toBe("venta_hora");
  });

  describe("chart_type=sankey (predecir_faltante_hoy)", () => {
    function buildPredictionResponse(
      tableData: Array<Record<string, unknown>>,
    ): AnalyticsResponse {
      return buildResponse({
        chart_type: "sankey",
        metric_name: "prediccion_faltante",
        series: [],
        table_data: tableData,
      });
    }

    it("builds one sankey trace with SKU -> riesgo -> acción nodes", () => {
      const chart = analyticsResponseToChartData(
        buildPredictionResponse([
          {
            nombre: "Agua natural 1L",
            stock_cierre: 8,
            venta_diaria: 20,
            cobertura_dias: 0.24,
          },
          {
            nombre: "Refresco cola 2L",
            stock_cierre: 15,
            venta_diaria: 12.5,
            cobertura_dias: 1.2,
          },
        ]),
      );

      expect(chart.plotly_config.data).toHaveLength(1);
      const trace = chart.plotly_config.data[0];
      expect(trace.type).toBe("sankey");

      const labels = trace.node?.label as string[];
      expect(labels).toContain("Agua natural 1L");
      expect(labels).toContain("Refresco cola 2L");
      expect(labels).toContain("Riesgo alto"); // cobertura 0.24 < 0.5
      expect(labels).toContain("Riesgo bajo"); // cobertura 1.2 en [1.0, 1.5)
      expect(labels).toContain("Resurtir ahora");
      expect(labels).toContain("Monitorear");
    });

    it("uses replenishment units to reach 1.5 days as width and aggregates them", () => {
      const chart = analyticsResponseToChartData(
        buildPredictionResponse([
          {
            nombre: "SKU A",
            stock_cierre: 8,
            venta_diaria: 20,
            cobertura_dias: 0.4,
          },
          {
            nombre: "SKU B",
            stock_cierre: 4,
            venta_diaria: 10,
            cobertura_dias: 0.4,
          },
        ]),
      );

      const trace = chart.plotly_config.data[0];
      const link = trace.link as {
        source: number[];
        target: number[];
        value: number[];
      };
      const labels = trace.node?.label as string[];

      // El link riesgo->acción es el que apunta al nodo "Resurtir ahora".
      const accionIdx = labels.indexOf("Resurtir ahora");
      const riesgoToAccionIdx = link.target.indexOf(accionIdx);
      // A necesita 22 unidades y B necesita 11 para recuperar 1.5 días.
      expect(link.value[riesgoToAccionIdx]).toBe(33);
      expect(trace.name).toBe("Unidades para recuperar 1.5 días de cobertura");
    });

    it("skips SKUs with zero or missing stock (nothing flows for them)", () => {
      const chart = analyticsResponseToChartData(
        buildPredictionResponse([
          {
            nombre: "Sin stock",
            stock_cierre: 0,
            venta_diaria: 10,
            cobertura_dias: 0.1,
          },
          {
            nombre: "Con stock",
            stock_cierre: 3,
            venta_diaria: 10,
            cobertura_dias: 0.1,
          },
        ]),
      );

      const labels = chart.plotly_config.data[0].node?.label as string[];
      expect(labels).not.toContain("Sin stock");
      expect(labels).toContain("Con stock");
    });

    it("marks chart_status=empty when table_data has no candidates", () => {
      const chart = analyticsResponseToChartData(buildPredictionResponse([]));

      expect(chart.plotly_config.data).toHaveLength(0);
      expect(chart.chart_status).toBe("empty");
    });
  });
});

describe("bucketFor", () => {
  it("buckets by the same thresholds the sankey uses (alto < 0.5 < medio < 1.0 < bajo < 1.5)", () => {
    expect(bucketFor(0.1).label).toBe("Riesgo alto");
    expect(bucketFor(0.49).label).toBe("Riesgo alto");
    expect(bucketFor(0.5).label).toBe("Riesgo medio");
    expect(bucketFor(0.99).label).toBe("Riesgo medio");
    expect(bucketFor(1.0).label).toBe("Riesgo bajo");
    expect(bucketFor(1.49).label).toBe("Riesgo bajo");
  });

  it("falls back to the last bucket for values at/above the backend's own filter threshold", () => {
    // El backend nunca manda cobertura_dias >= 1.5 (su propio umbral), pero
    // el fallback debe ser seguro si algún día se relaja ese filtro.
    expect(bucketFor(5).label).toBe("Riesgo bajo");
  });
});

describe("chart_type=map (choropleth por región)", () => {
  const mapResponse = () =>
    buildResponse({
      chart_type: "map",
      series: [
        {
          name: "Inventario de sistema con existencia",
          points: [
            { label: "Jalisco", value: 91.2, dimension: null },
            { label: "Estado de México", value: 84.5, dimension: null },
          ],
        },
      ],
      grounding: {
        source: "retail-advisor",
        unit: "percent",
        dimension: "region",
        metric: "disponibilidad",
      },
      table_data: [
        {
          label: "Jalisco",
          value: 91.2,
          numerator: 912,
          denominator: 1000,
        },
        {
          label: "Estado de México",
          value: 84.5,
          numerator: 845,
          denominator: 1000,
        },
      ],
    });

  it("es ploteable y produce un trace choropleth con geojson local", () => {
    expect(isPlottableChartType("map")).toBe(true);
    const chart = analyticsResponseToChartData(mapResponse());
    const trace = chart.plotly_config.data[0] as Record<string, unknown>;
    expect(trace.type).toBe("choropleth");
    expect(trace.featureidkey).toBe("properties.name");
    expect(trace.locations).toHaveLength(32);
    const locations = trace.locations as string[];
    const values = trace.z as Array<number | null>;
    expect(values[locations.indexOf("Jalisco")]).toBe(91.2);
    expect(values[locations.indexOf("Chihuahua")]).toBeNull();
    // GeoJSON empaquetado (no URL externa) con los 32 estados.
    const geojson = trace.geojson as { features: unknown[] };
    expect(geojson.features).toHaveLength(32);
  });

  it("tooltip transporta numerador, denominador y tasa; cero difiere de sin dato", () => {
    const response = mapResponse();
    response.metric_name = "faltante";
    response.visualization = {
      task: "spatial",
      title: "Tasa regional de faltante",
      higher_is_better: false,
    };
    response.series[0].points = [
      { label: "Jalisco", value: 10, dimension: null },
      { label: "Yucatán", value: 0, dimension: null },
    ];
    response.table_data = [
      { label: "Jalisco", value: 10, numerator: 10, denominator: 100 },
      { label: "Yucatán", value: 0, numerator: 0, denominator: 20 },
    ];

    const trace = analyticsResponseToChartData(response).plotly_config
      .data[0] as Record<string, unknown>;
    const locations = trace.locations as string[];
    const values = trace.z as Array<number | null>;
    const customdata = trace.customdata as Array<
      [number | null, number | null]
    >;

    expect(values[locations.indexOf("Yucatán")]).toBe(0);
    expect(values[locations.indexOf("Chihuahua")]).toBeNull();
    expect(customdata[locations.indexOf("Jalisco")]).toEqual([10, 100]);
    expect(trace.hovertemplate).toContain("Numerador");
    expect(trace.hovertemplate).toContain("Denominador");
  });

  it("las regiones del dataset existen en el geojson (featureidkey match)", () => {
    const chart = analyticsResponseToChartData(mapResponse());
    const trace = chart.plotly_config.data[0] as Record<string, unknown>;
    const geojson = trace.geojson as {
      features: Array<{ properties: { name: string } }>;
    };
    const nombres = new Set(geojson.features.map((f) => f.properties.name));
    for (const loc of trace.locations as string[]) {
      expect(nombres.has(loc)).toBe(true);
    }
  });

  it("la polaridad del contrato decide la escala, no el id de métrica", () => {
    const faltante = analyticsResponseToChartData(
      buildResponse({
        chart_type: "map",
        grounding: { source: "retail-advisor", metric: "otra_metrica" },
        visualization: {
          task: "spatial",
          title: "Riesgo regional",
          higher_is_better: false,
        },
        series: [
          {
            name: "Faltante",
            points: [{ label: "Jalisco", value: 3, dimension: null }],
          },
        ],
      }),
    );
    const disponibilidad = analyticsResponseToChartData(mapResponse());
    expect(
      (faltante.plotly_config.data[0] as Record<string, unknown>).colorscale,
    ).toBe("Reds");
    expect(
      (disponibilidad.plotly_config.data[0] as Record<string, unknown>)
        .colorscale,
    ).toBe("Blues");
  });

  it("usa layout geo con fitbounds (sin ejes cartesianos)", () => {
    const chart = analyticsResponseToChartData(mapResponse());
    const layout = chart.plotly_config.layout as Record<string, unknown>;
    expect(layout.geo).toMatchObject({ fitbounds: "locations" });
    expect(layout.xaxis).toBeUndefined();
  });

  it("el merge con el tema NO reintroduce ejes cartesianos en el mapa", () => {
    // Regresión: el tema inyectaba xaxis/yaxis/hovermode a todo chart y el
    // choropleth tronaba en el resize responsivo de Plotly
    // (TypeError _axisMatchGroups de undefined, visto en el pase visual).
    const chart = analyticsResponseToChartData(mapResponse());
    const merged = mergePlotlyLayout(
      getPlotlyLayoutTheme("dark"),
      chart.plotly_config.layout as Partial<PlotlyLayout>,
    ) as Record<string, unknown>;
    expect(merged.geo).toMatchObject({ fitbounds: "locations" });
    expect(merged.xaxis).toBeUndefined();
    expect(merged.yaxis).toBeUndefined();
    expect(merged.hovermode).toBeUndefined();
    // Un chart cartesiano SÍ conserva los ejes del tema.
    const bar = analyticsResponseToChartData(buildResponse({}));
    const mergedBar = mergePlotlyLayout(
      getPlotlyLayoutTheme("dark"),
      bar.plotly_config.layout as Partial<PlotlyLayout>,
    ) as Record<string, unknown>;
    expect(mergedBar.xaxis).toBeDefined();
    expect(mergedBar.hovermode).toBe("x unified");
  });
});

describe("recibos por origen", () => {
  it("apila la composición temporal y conserva solo los puntos recibidos", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        metric_name: "recibo_mercancia",
        chart_type: "bar",
        grounding: {
          source: "retail-advisor",
          unit: "count",
          dimension: "origen",
        },
        visualization: {
          task: "composition",
          title: "Recibo de mercancía",
          subtitle: "Mundo E · Por origen · Últimos 7 días",
        },
        series: [
          {
            name: "cedis",
            points: [
              { label: "2026-06-29", value: 120, dimension: "cedis" },
              { label: "2026-06-30", value: 50, dimension: "cedis" },
            ],
          },
          {
            name: "directo",
            points: [{ label: "2026-06-29", value: 80, dimension: "directo" }],
          },
        ],
      }),
    );

    const layout = chart.plotly_config.layout as Record<string, unknown>;
    expect(layout.barmode).toBe("stack");
    expect(layout.showlegend).toBe(true);
    expect(chart.plotly_config.data).toHaveLength(2);
    expect((chart.plotly_config.data[1] as Record<string, unknown>).x).toEqual([
      "2026-06-29",
    ]);
  });
});


describe("revisión de gráficas 2026-11-08 (GRA-1, GRA-3, GRA-5, GRA-6)", () => {
  it("los ticks llevan la unidad: % en porcentajes, $ en pesos", () => {
    const pct = analyticsResponseToChartData(buildResponse({}));
    const yaxis = (pct.plotly_config.layout as Record<string, unknown>)
      .yaxis as Record<string, unknown>;
    expect(yaxis.ticksuffix).toBe("%");
    expect(ticksUnidad("currency")).toEqual({ tickprefix: "$" });
    expect(ticksUnidad("count")).toEqual({});
    expect(tituloEje(undefined)).toBeUndefined();
  });

  it("etiquetas largas se acortan por el final y el margen crece con ellas", () => {
    expect(acortarEtiqueta("Refresco Coca Cola Sin Azúcar 1.35 Lt Pet Nr")).toBe(
      "Refresco Coca Cola Sin Azúcar…",
    );
    expect(acortarEtiqueta("Pepsi 400")).toBe("Pepsi 400");
    expect(margenParaEtiquetas(["Pepsi 400"])).toBe(90);
    expect(margenParaEtiquetas(["Refresco Coca Cola Sin Azúcar 1.35 Lt"])).toBe(216);
  });

  it("los deciles se ordenan del 1 al 10 con Sin venta al final", () => {
    expect(ordenOrdinal(["Decil 7", "Decil 4", "Sin venta", "Decil 10", "Decil 1"])).toEqual([
      "Decil 1",
      "Decil 4",
      "Decil 7",
      "Decil 10",
      "Sin venta",
    ]);
    expect(ordenOrdinal(["Polanco", "Mundo E"])).toBeUndefined();
  });

  it("una serie de barras toda negativa (merma) se grafica en magnitud", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        chart_type: "bar",
        grounding: { unit: "count", dimension: "categoria" },
        series: [
          {
            name: "Merma",
            points: [
              { label: "Licores", value: -16 },
              { label: "Farmacia", value: -2 },
              { label: "Perfumería", value: 0 },
            ],
          },
        ],
      }),
    );
    const trace = chart.plotly_config.data[0] as Record<string, unknown>;
    expect(trace.y).toEqual([16, 2, 0]);
    expect(trace.text).toEqual(["16", "2", "0"]);
  });
});


describe("GRA-4, GRA-7, GRA-9 y GRA-10 (2026-11-08)", () => {
  it("nombres largos de categoría van en barras horizontales; fechas no", () => {
    const largas = buildResponse({
      chart_type: "bar",
      grounding: { unit: "percent", dimension: "categoria" },
      series: [
        {
          name: "Quiebre",
          points: [
            { label: "Brandy y coñac", value: 52.5 },
            { label: "Coolers y bebidas preparadas", value: 27.7 },
          ],
        },
      ],
    });
    expect(esRankingHorizontal(largas)).toBe(true);
    const chart = analyticsResponseToChartData(largas);
    expect((chart.plotly_config.data[0] as Record<string, unknown>).orientation).toBe("h");
    expect(chart.plotly_config.layout.height).toBe(alturaPorFilas(2));

    const fechas = buildResponse({
      chart_type: "bar",
      grounding: { unit: "count", dimension: "dia" },
      series: [
        {
          name: "Venta",
          points: [
            { label: "2026-09-01 (lunes)", value: 1 },
            { label: "2026-09-02 (martes)", value: 2 },
          ],
        },
      ],
    });
    expect(esRankingHorizontal(fechas)).toBe(false);
    expect(envolverEtiqueta("Coolers y bebidas preparadas")).toBe("Coolers y<br>bebidas<br>preparadas");
  });

  it("sin título del plugin, el título lleva la dimensión", () => {
    const sin = buildResponse({
      metric_name: "Merma",
      visualization: null,
      grounding: { unit: "count", dimension: "categoria" },
    });
    expect(tituloGrafica(sin)).toBe("Merma por categoría");
    expect(tituloGrafica(buildResponse({ metric_name: "Venta", visualization: null, grounding: {} }))).toBe("Venta");
  });

  it("dos series del mismo eje anotan el cambio porcentual por categoría", () => {
    const chart = analyticsResponseToChartData(
      buildResponse({
        chart_type: "bar",
        grounding: { unit: "currency", dimension: "articulo" },
        series: [
          { name: "agosto", points: [{ label: "Coca 600", value: 100 }, { label: "Squirt", value: 50 }] },
          { name: "septiembre", points: [{ label: "Coca 600", value: 92.4 }, { label: "Squirt", value: 68 }] },
        ],
      }),
    );
    const anotaciones = (chart.plotly_config.layout as Record<string, unknown>)
      .annotations as Array<Record<string, unknown>>;
    expect(anotaciones.map((a) => a.text)).toEqual(["−7.6%", "+36.0%"]);
    expect(chart.plotly_config.layout.bargap).toBe(0.6);
  });
});
