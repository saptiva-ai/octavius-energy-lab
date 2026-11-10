"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { useTheme } from "next-themes";
import type { Data, Layout } from "plotly.js";
import { cn } from "@/lib/utils";
import type { ChartData } from "@/lib/types";
import { ChartActionButtons } from "../ChartActionButtons";
import { ChartNarration } from "./ChartNarration";
import { FreshnessBadge } from "./FreshnessBadge";
import {
  colorearBarras,
  getPlotlyLayoutTheme,
  mergePlotlyLayout,
} from "@/lib/charts/plotly-theme";
import { getPlotlyRuntime } from "./plotly-runtime";
import { logError } from "@/lib/logger";
import { MetricContextNote } from "./MetricContextNote";
import { RegionalRanking } from "./RegionalRanking";
import { StoreComparisonSummary } from "./StoreComparisonSummary";
import { IntradayContextPanel } from "./IntradayContextPanel";
import { EditorialTable } from "./EditorialTable";

// Plotly necesita `window`; se carga solo en cliente y solo cuando el canvas
// realmente muestra un chart (no infla el bundle inicial del chat).
const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center text-sm text-muted">
      Cargando gráfica…
    </div>
  ),
});

function downloadCsv(chart: ChartData) {
  const rows: string[][] = [];
  const series = chart.analytics?.series ?? [];

  if (series.length > 0) {
    rows.push(["serie", "etiqueta", "valor"]);
    for (const serie of series) {
      for (const point of serie.points) {
        rows.push([serie.name, point.label, String(point.value)]);
      }
    }
  } else if (chart.analytics?.table_data?.length) {
    const columns = Object.keys(chart.analytics.table_data[0]);
    rows.push(columns);
    for (const row of chart.analytics.table_data) {
      rows.push(columns.map((c) => String(row[c] ?? "")));
    }
  } else {
    return;
  }

  const csv = rows
    .map((r) => r.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(","))
    .join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${chart.title || "retail-chart"}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

interface PlotlyChartViewProps {
  chart: ChartData;
  className?: string;
}

/** Renderer genérico de charts del canvas (contrato ChartData.plotly_config).
 * Retail-advisor es hoy el único productor real; cualquier otro origen que
 * arme el mismo contrato (plotly_config + analytics opcional) se ve igual. */
export function PlotlyChartView({ chart, className }: PlotlyChartViewProps) {
  // next-themes (no useUIStore.theme) es la fuente real del modo claro/oscuro
  // aplicado a la UI (ver ModeToggle.tsx) — resolvedTheme sigue "system".
  const { resolvedTheme } = useTheme();
  const theme = resolvedTheme === "dark" ? "dark" : "light";
  const graphDivRef = React.useRef<HTMLElement | null>(null);

  const layout = React.useMemo(
    () =>
      mergePlotlyLayout(
        getPlotlyLayoutTheme(theme),
        // Boundary cast: ChartData.plotly_config.layout es un transporte laxo
        // (contrato compartido con canvas-store/backend); Plotly.Layout es el
        // shape estricto que espera react-plotly.js para renderizar.
        (chart.plotly_config.layout ?? {}) as Partial<Layout>,
      ),
    [theme, chart.plotly_config.layout],
  );

  // Una sola serie de barras: un color por barra según el tema.
  const data = React.useMemo(
    () => colorearBarras(chart.plotly_config.data as Data[], theme),
    [theme, chart.plotly_config.data],
  );

  const handleDownloadPNG = React.useCallback(async () => {
    if (!graphDivRef.current) return;
    try {
      const Plotly = (await getPlotlyRuntime()).default;
      await Plotly.downloadImage(graphDivRef.current, {
        format: "png",
        filename: chart.title || "retail-chart",
        width: graphDivRef.current.clientWidth || 800,
        height: graphDivRef.current.clientHeight || 500,
      });
    } catch (err) {
      logError("[PlotlyChartView] Failed to download PNG", err);
    }
  }, [chart.title]);

  const handleResetZoom = React.useCallback(async () => {
    if (!graphDivRef.current) return;
    try {
      const Plotly = (await getPlotlyRuntime()).default;
      await Plotly.relayout(graphDivRef.current, {
        "xaxis.autorange": true,
        "yaxis.autorange": true,
      });
    } catch (err) {
      logError("[PlotlyChartView] Failed to reset zoom", err);
    }
  }, []);

  const handleExportCSV = React.useCallback(() => downloadCsv(chart), [chart]);

  const analytics = chart.analytics;
  const isPlottable = chart.plotly_config.data.length > 0;
  const hasRegionalRanking =
    analytics?.chart_type === "map" &&
    analytics.table_data.some(
      (row) =>
        typeof row.numerator === "number" &&
        typeof row.denominator === "number",
    );

  // Plotly solo se reajusta con el resize de la ventana. Si se monta con el
  // panel todavía cerrado (ancho 0) toma su ancho por omisión y queda cortada
  // al abrirse, p. ej. al reabrirla con "Ver gráfica". Cuando el contenedor ya
  // no mide lo que Plotly dibujó, se avisa como resize de la ventana: así
  // `useResizeHandler` reajusta con la instancia de Plotly que ya está cargada.
  const contenedorRef = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    const contenedor = contenedorRef.current;
    if (!contenedor || typeof ResizeObserver === "undefined") return;
    let cuadro = 0;
    const observador = new ResizeObserver(([entrada]) => {
      const svg = graphDivRef.current?.querySelector(".main-svg");
      const anchoDibujado = Number(svg?.getAttribute("width"));
      const anchoContenedor = Math.round(entrada?.contentRect.width ?? 0);
      if (!anchoDibujado || !anchoContenedor) return;
      if (anchoDibujado === anchoContenedor) return;
      cancelAnimationFrame(cuadro);
      cuadro = requestAnimationFrame(() =>
        window.dispatchEvent(new Event("resize")),
      );
    });
    observador.observe(contenedor);
    return () => {
      cancelAnimationFrame(cuadro);
      observador.disconnect();
    };
  }, [isPlottable]);

  return (
    <div className={cn("flex h-full flex-col gap-3", className)}>
      {/* Encabezado en dos renglones: el badge y la fuente nunca se parten
          (GRA-8: "Día cerrado · 2026-09-30" quedaba en dos líneas cuando el
          ámbito era largo); el ámbito va abajo, completo. */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            {analytics?.freshness && (
              <FreshnessBadge
                className="shrink-0 whitespace-nowrap"
                freshness={analytics.freshness}
                dataAsOf={analytics.data_as_of}
              />
            )}
            {analytics?.grounding?.source && (
              <span className="shrink-0 whitespace-nowrap text-[10px] text-muted">
                Fuente: {analytics.grounding.source}
              </span>
            )}
          </div>
          {analytics?.visualization?.subtitle && (
            <span className="text-[10px] leading-snug text-muted">
              {analytics.visualization.subtitle}
            </span>
          )}
        </div>
        {isPlottable && (
          <ChartActionButtons
            onDownloadPNG={handleDownloadPNG}
            onExportCSV={handleExportCSV}
            onResetZoom={handleResetZoom}
          />
        )}
      </div>

      <MetricContextNote chart={chart} />

      {analytics?.grounding?.capability === "intraday_sales" && (
        <IntradayContextPanel chart={chart} />
      )}

      {analytics?.visualization?.task === "comparison" && (
        <StoreComparisonSummary
          rows={analytics.table_data}
          unit={analytics.grounding?.unit}
          period={analytics.grounding?.period}
        />
      )}

      {isPlottable ? (
        <div
          className={cn(
            "min-h-0 flex-1",
            hasRegionalRanking &&
              "grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(15rem,1fr)]",
          )}
        >
          <div ref={contenedorRef} className="min-h-64">
            <Plot
              // Boundary cast: mismo motivo que el layout — el adaptador arma
              // `type` como string genérico (bar/scatter), Plotly.Data exige
              // los literales exactos que sí produce analytics-to-chart-data.ts.
              data={data}
              layout={layout}
              config={{
                responsive: true,
                displayModeBar: false,
                ...chart.plotly_config.config,
              }}
              useResizeHandler
              // Con alto propio (rankings: según sus barras, GRA-9) la
              // gráfica se pega arriba en vez de flotar a media altura.
              style={{
                width: "100%",
                height:
                  typeof layout.height === "number"
                    ? `${layout.height}px`
                    : "100%",
              }}
              onInitialized={(_figure, graphDiv) => {
                graphDivRef.current = graphDiv;
              }}
              onUpdate={(_figure, graphDiv) => {
                graphDivRef.current = graphDiv;
              }}
            />
          </div>
          {hasRegionalRanking && (
            <RegionalRanking rows={analytics?.table_data ?? []} />
          )}
        </div>
      ) : analytics?.table_data?.length ? (
        <EditorialTable chart={chart} />
      ) : chart.response_text ? (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-border bg-surface p-6">
          <ChartNarration text={chart.response_text} />
        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-border bg-surface p-6 text-center text-sm text-muted">
          Sin datos para graficar.
        </div>
      )}
      {/* Sin el texto del plugin debajo de la gráfica: el chat ya lo narra y
          ocupaba medio panel (Equipo, 2026-10-21). Solo se muestra cuando no
          hay gráfica ni tabla, arriba. */}
    </div>
  );
}

export default PlotlyChartView;
