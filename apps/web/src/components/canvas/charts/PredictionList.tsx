"use client";

import * as React from "react";
import {
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
} from "@heroicons/react/24/solid";
import { bucketFor } from "@/lib/charts/analytics-to-chart-data";
import type { ChartData } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ChartNarration } from "./ChartNarration";
import { FreshnessBadge } from "./FreshnessBadge";

type Urgencia = "alta" | "media" | "baja";

interface PrediccionRow {
  articulo_id: string;
  nombre: string;
  es_top_seller?: boolean;
  stock_cierre: number;
  venta_diaria: number;
  cobertura_dias: number;
  capacidad_unidades?: number | null;
  prioridad?: number;
  urgencia?: Urgencia;
  accion_recomendada?: string;
  [key: string]: unknown;
}

const URGENCIA_CONFIG: Record<
  Urgencia,
  {
    label: string;
    color: string;
    action: string;
    icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  }
> = {
  alta: {
    label: "Alta",
    color: "#EF4444",
    action: "Resurtir ahora",
    icon: ExclamationCircleIcon,
  },
  media: {
    label: "Media",
    color: "#F59E0B",
    action: "Resurtir hoy",
    icon: ExclamationTriangleIcon,
  },
  baja: {
    label: "Baja",
    color: "#10B981",
    action: "Monitorear y preparar resurtido",
    icon: InformationCircleIcon,
  },
};

function isPrediccionRow(row: Record<string, unknown>): row is PrediccionRow {
  return (
    typeof row.nombre === "string" &&
    typeof row.stock_cierre === "number" &&
    Number.isFinite(row.stock_cierre) &&
    typeof row.venta_diaria === "number" &&
    Number.isFinite(row.venta_diaria) &&
    typeof row.cobertura_dias === "number" &&
    Number.isFinite(row.cobertura_dias)
  );
}

function urgenciaFor(row: PrediccionRow): Urgencia {
  if (
    row.urgencia === "alta" ||
    row.urgencia === "media" ||
    row.urgencia === "baja"
  ) {
    return row.urgencia;
  }
  const bucket = bucketFor(row.cobertura_dias);
  if (bucket.label === "Riesgo alto") return "alta";
  if (bucket.label === "Riesgo medio") return "media";
  return "baja";
}

function prioridadFor(row: PrediccionRow): number {
  return typeof row.prioridad === "number" &&
    Number.isFinite(row.prioridad) &&
    row.prioridad > 0
    ? row.prioridad
    : Number.MAX_SAFE_INTEGER;
}

function formatNumber(value: number, maximumFractionDigits = 2): string {
  return new Intl.NumberFormat("es-MX", {
    maximumFractionDigits,
  }).format(value);
}

interface PredictionListProps {
  chart: ChartData;
  className?: string;
}

/** Ranking operativo para predecir_faltante_hoy. La urgencia usa color e
 * icono; el llenado conserva una barra neutral, y los textos distinguen datos
 * observados, estimación y recomendación. */
export function PredictionList({ chart, className }: PredictionListProps) {
  const analytics = chart.analytics;
  const rows = [...(analytics?.table_data ?? []).filter(isPrediccionRow)].sort(
    (a, b) =>
      prioridadFor(a) - prioridadFor(b) ||
      a.cobertura_dias - b.cobertura_dias ||
      b.venta_diaria - a.venta_diaria ||
      String(a.articulo_id ?? "").localeCompare(String(b.articulo_id ?? "")),
  );
  const ventanaRaw = analytics?.grounding?.ventana_dias;
  const ventanaDias =
    typeof ventanaRaw === "number" && ventanaRaw > 0 ? ventanaRaw : 7;
  const resumen = rows.reduce<Record<Urgencia, number>>(
    (totals, row) => {
      totals[urgenciaFor(row)] += 1;
      return totals;
    },
    { alta: 0, media: 0, baja: 0 },
  );

  return (
    <div className={cn("flex h-full min-h-0 flex-col gap-3", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {analytics?.freshness && (
            <FreshnessBadge
              freshness={analytics.freshness}
              dataAsOf={analytics.data_as_of}
            />
          )}
          {analytics?.grounding?.source && (
            <span className="text-[10px] text-muted">
              Fuente: {analytics.grounding.source}
            </span>
          )}
          {analytics?.visualization?.subtitle && (
            <span className="text-[10px] text-muted">
              {analytics.visualization.subtitle}
            </span>
          )}
        </div>
        <span className="text-xs font-medium text-muted">
          {rows.length} {rows.length === 1 ? "artículo" : "artículos"}{" "}
          priorizados
        </span>
      </div>

      {rows.length > 0 ? (
        <>
          <div
            className="flex flex-wrap gap-2"
            aria-label="Resumen por urgencia"
          >
            {(Object.keys(URGENCIA_CONFIG) as Urgencia[]).map((urgencia) => (
              <span
                key={urgencia}
                className="rounded-full border border-border bg-surface px-2 py-1 text-xs font-medium"
                style={{ color: URGENCIA_CONFIG[urgencia].color }}
              >
                {URGENCIA_CONFIG[urgencia].label} {resumen[urgencia]}
              </span>
            ))}
          </div>

          <p className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs text-muted">
            <span className="font-medium text-foreground">
              Cobertura estimada:
            </span>{" "}
            stock al cierre ÷ promedio diario de venta de los últimos{" "}
            {ventanaDias} días. Orden: menor cobertura, luego mayor venta
            diaria. Es una estimación de días de venta, no una hora exacta de
            quiebre.
          </p>

          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
            {rows.map((row, index) => {
              const urgencia = urgenciaFor(row);
              const config = URGENCIA_CONFIG[urgencia];
              const Icon = config.icon;
              const prioridad =
                prioridadFor(row) === Number.MAX_SAFE_INTEGER
                  ? index + 1
                  : prioridadFor(row);
              const capacidad =
                typeof row.capacidad_unidades === "number" &&
                Number.isFinite(row.capacidad_unidades) &&
                row.capacidad_unidades > 0
                  ? row.capacidad_unidades
                  : null;
              const fillPct =
                capacidad === null
                  ? null
                  : Math.max(
                      0,
                      Math.min(
                        100,
                        Math.round((row.stock_cierre / capacidad) * 100),
                      ),
                    );

              return (
                <article
                  key={`${row.articulo_id}-${index}`}
                  data-testid="prediction-card"
                  className="rounded-lg border border-border bg-surface p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold text-primary">
                      Prioridad {prioridad}
                    </span>
                    <Icon
                      className="h-4 w-4 shrink-0"
                      style={{ color: config.color }}
                      aria-hidden="true"
                    />
                    <span
                      className="text-xs font-semibold"
                      style={{ color: config.color }}
                    >
                      Urgencia {urgencia}
                    </span>
                    {row.es_top_seller && (
                      <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary">
                        Top seller
                      </span>
                    )}
                  </div>

                  <div className="mt-2">
                    <span className="text-sm font-semibold text-foreground">
                      {row.nombre}
                    </span>
                    {row.articulo_id && (
                      <span className="ml-1.5 text-xs text-muted">
                        ({row.articulo_id})
                      </span>
                    )}
                  </div>

                  <div className="mt-3 grid gap-2 text-xs sm:grid-cols-3">
                    <div className="rounded-md bg-surface-2 p-2">
                      <p className="font-semibold text-foreground">
                        Dato observado
                      </p>
                      <p className="mt-1 text-muted">
                        {formatNumber(row.stock_cierre)} unidades al cierre
                      </p>
                    </div>
                    <div className="rounded-md bg-surface-2 p-2">
                      <p className="font-semibold text-foreground">
                        Cobertura estimada
                      </p>
                      <p className="mt-1 text-muted">
                        {formatNumber(row.cobertura_dias)} días de venta
                      </p>
                      <p className="text-[10px] text-muted">
                        Promedio: {formatNumber(row.venta_diaria, 1)}{" "}
                        unidades/día
                      </p>
                    </div>
                    <div className="rounded-md bg-surface-2 p-2">
                      <p className="font-semibold text-foreground">
                        Siguiente acción recomendada
                      </p>
                      <p className="mt-1 text-muted">
                        {row.accion_recomendada || config.action}
                      </p>
                    </div>
                  </div>

                  <div className="mt-3">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-medium text-foreground">
                        Nivel de llenado
                      </span>
                      {capacidad === null || fillPct === null ? (
                        <span className="text-muted">
                          Capacidad no disponible
                        </span>
                      ) : (
                        <span className="text-muted">
                          {formatNumber(row.stock_cierre)} de{" "}
                          {formatNumber(capacidad)} unidades ({fillPct}%)
                        </span>
                      )}
                    </div>
                    {capacidad !== null && fillPct !== null && (
                      <div
                        role="progressbar"
                        aria-label={`Nivel de llenado de ${row.nombre}`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={fillPct}
                        className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted/20"
                      >
                        <div
                          className="h-full rounded-full bg-primary transition-[width]"
                          style={{ width: `${fillPct}%` }}
                        />
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </>
      ) : (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-border bg-surface p-6 text-center text-sm text-muted">
          Sin artículos en riesgo de faltante.
        </div>
      )}

      {chart.response_text && (
        <ChartNarration
          text={chart.response_text}
          className="border-t border-border pt-3"
        />
      )}
    </div>
  );
}

export default PredictionList;
