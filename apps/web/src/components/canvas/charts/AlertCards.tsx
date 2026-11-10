"use client";

import * as React from "react";
import {
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  ArrowRightIcon,
} from "@heroicons/react/24/solid";
import { cn } from "@/lib/utils";
import type { ChartData } from "@/lib/types";
import { ChartNarration } from "./ChartNarration";
import { FreshnessBadge } from "./FreshnessBadge";

type Severidad = "alta" | "media" | "baja";

interface AlertaEvidence {
  label: string;
  value: string | number;
  unit?: string;
}

interface AlertaRow {
  tipo: string;
  severidad: Severidad;
  articulo_id: string;
  nombre: string;
  causa: string;
  accion: string;
  prioridad?: number;
  urgencia?: string;
  por_que_ahora?: string;
  tipo_label?: string;
  impacto_unidades?: number | null;
  evidencia?: AlertaEvidence[];
  recomendacion_no_confirmada?: boolean;
  datos?: Record<string, unknown>;
  [key: string]: unknown;
}

const SEVERIDAD_STYLE: Record<
  Severidad,
  {
    Icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
    iconColor: string;
    border: string;
    badge: string;
  }
> = {
  alta: {
    Icon: ExclamationCircleIcon,
    iconColor: "text-red-500",
    border: "border-l-red-500",
    badge: "bg-red-500/15 text-red-500",
  },
  media: {
    Icon: ExclamationTriangleIcon,
    iconColor: "text-amber-500",
    border: "border-l-amber-500",
    badge: "bg-amber-500/15 text-amber-500",
  },
  baja: {
    Icon: InformationCircleIcon,
    iconColor: "text-muted",
    border: "border-l-muted",
    badge: "bg-muted/20 text-muted",
  },
};

const SEVERIDAD_ORDEN: Record<Severidad, number> = {
  alta: 0,
  media: 1,
  baja: 2,
};

const TIPO_LABEL: Record<string, string> = {
  confiabilidad_sospechosa: "Confiabilidad sospechosa",
  venta_cayendo: "Venta cayendo",
  riesgo_faltante: "Riesgo de faltante",
  faltante_anticipado: "Faltante anticipado",
  sobre_stock: "Sobre-stock",
};

function isEvidence(value: unknown): value is AlertaEvidence {
  if (typeof value !== "object" || value === null) return false;
  const evidence = value as Record<string, unknown>;
  return (
    typeof evidence.label === "string" &&
    (typeof evidence.value === "string" ||
      typeof evidence.value === "number") &&
    (evidence.unit === undefined || typeof evidence.unit === "string")
  );
}

function isAlertaRow(row: Record<string, unknown>): row is AlertaRow {
  return (
    typeof row.tipo === "string" &&
    typeof row.articulo_id === "string" &&
    typeof row.nombre === "string" &&
    typeof row.causa === "string" &&
    typeof row.accion === "string" &&
    (row.severidad === "alta" ||
      row.severidad === "media" ||
      row.severidad === "baja")
  );
}

function formatEvidence(evidence: AlertaEvidence): string {
  const value =
    typeof evidence.value === "number" && !Number.isInteger(evidence.value)
      ? evidence.value.toFixed(1)
      : evidence.value;
  return `${evidence.label}: ${value}${evidence.unit ? ` ${evidence.unit}` : ""}`;
}

interface AlertCardsProps {
  chart: ChartData;
  className?: string;
}

/** Foquitos semáforo (detectar_alertas): una card por alerta, coloreada por
 * severidad, con causa raíz + acción recomendada — la UI del "foquito" del
 * brief. Vive fuera de Plotly (no es un chart, es una lista priorizada). */
export function AlertCards({ chart, className }: AlertCardsProps) {
  const analytics = chart.analytics;
  const tableData = analytics?.table_data;
  const rows = React.useMemo(
    () => (tableData ?? []).filter(isAlertaRow),
    [tableData],
  );
  const [typeFilter, setTypeFilter] = React.useState<string | null>(null);

  const sortedRows = React.useMemo(
    () =>
      [...rows].sort((left, right) => {
        const leftPriority =
          typeof left.prioridad === "number"
            ? left.prioridad
            : Number.MAX_SAFE_INTEGER;
        const rightPriority =
          typeof right.prioridad === "number"
            ? right.prioridad
            : Number.MAX_SAFE_INTEGER;
        return (
          leftPriority - rightPriority ||
          SEVERIDAD_ORDEN[left.severidad] - SEVERIDAD_ORDEN[right.severidad] ||
          left.tipo.localeCompare(right.tipo) ||
          left.articulo_id.localeCompare(right.articulo_id)
        );
      }),
    [rows],
  );

  const severityCounts = React.useMemo(
    () =>
      sortedRows.reduce(
        (counts, row) => {
          counts[row.severidad] += 1;
          return counts;
        },
        { alta: 0, media: 0, baja: 0 },
      ),
    [sortedRows],
  );

  const typeOptions = React.useMemo(() => {
    const counts = new Map<string, { label: string; count: number }>();
    for (const row of sortedRows) {
      const current = counts.get(row.tipo);
      counts.set(row.tipo, {
        label:
          row.tipo_label ??
          TIPO_LABEL[row.tipo] ??
          row.tipo.split("_").join(" "),
        count: (current?.count ?? 0) + 1,
      });
    }
    return Array.from(counts.entries()).sort((left, right) =>
      left[1].label.localeCompare(right[1].label, "es"),
    );
  }, [sortedRows]);

  const activeTypeFilter = typeOptions.some(([type]) => type === typeFilter)
    ? typeFilter
    : null;
  const visibleRows = activeTypeFilter
    ? sortedRows.filter((row) => row.tipo === activeTypeFilter)
    : sortedRows;

  return (
    <div className={cn("flex h-full flex-col gap-3", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
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
          {rows.length} {rows.length === 1 ? "foquito" : "foquitos"}
        </span>
      </div>

      {sortedRows.length > 0 ? (
        <>
          <section
            aria-label="Resumen de alertas"
            className="rounded-lg border border-border bg-surface p-2.5"
          >
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-medium text-foreground">Resumen</span>
              {(["alta", "media", "baja"] as const).map((severity) => (
                <span
                  key={severity}
                  className={cn(
                    "rounded-full px-2 py-0.5 font-medium capitalize",
                    SEVERIDAD_STYLE[severity].badge,
                  )}
                >
                  {severity.charAt(0).toUpperCase() + severity.slice(1)}{" "}
                  {severityCounts[severity]}
                </span>
              ))}
            </div>

            <div
              role="group"
              aria-label="Filtrar alertas por tipo"
              className="mt-2 flex gap-1.5 overflow-x-auto pb-0.5"
            >
              <button
                type="button"
                aria-pressed={activeTypeFilter === null}
                aria-label="Mostrar todos los tipos"
                onClick={() => setTypeFilter(null)}
                className={cn(
                  "shrink-0 rounded-full border px-2 py-1 text-[10px] font-medium",
                  activeTypeFilter === null
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted hover:text-foreground",
                )}
              >
                Todos {sortedRows.length}
              </button>
              {typeOptions.map(([type, option]) => (
                <button
                  key={type}
                  type="button"
                  aria-pressed={activeTypeFilter === type}
                  aria-label={`Filtrar ${option.label}`}
                  onClick={() =>
                    setTypeFilter((current) => (current === type ? null : type))
                  }
                  className={cn(
                    "shrink-0 rounded-full border px-2 py-1 text-[10px] font-medium",
                    activeTypeFilter === type
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted hover:text-foreground",
                  )}
                >
                  {option.label} {option.count}
                </button>
              ))}
            </div>
          </section>

          <div className="flex-1 space-y-2 overflow-y-auto">
            {visibleRows.map((row, i) => {
              const style =
                SEVERIDAD_STYLE[row.severidad] ?? SEVERIDAD_STYLE.baja;
              const evidence = Array.isArray(row.evidencia)
                ? row.evidencia.filter(isEvidence)
                : [];
              return (
                <div
                  key={`${row.articulo_id}-${row.tipo}-${i}`}
                  data-testid="alert-card"
                  className={cn(
                    "rounded-lg border border-border border-l-4 bg-surface p-3",
                    style.border,
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {typeof row.prioridad === "number" && (
                      <span className="rounded bg-foreground px-1.5 py-0.5 text-[10px] font-semibold text-background">
                        Prioridad {row.prioridad}
                      </span>
                    )}
                    <style.Icon
                      className={cn("h-4 w-4 shrink-0", style.iconColor)}
                      aria-hidden="true"
                    />
                    <span className="text-sm font-medium text-foreground">
                      {row.nombre}
                    </span>
                    <span className="text-xs text-muted">
                      ({row.articulo_id})
                    </span>
                    {row.urgencia && (
                      <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-medium text-foreground">
                        {row.urgencia}
                      </span>
                    )}
                    <span
                      className={cn(
                        "ml-auto rounded-full px-2 py-0.5 text-[10px] font-medium uppercase",
                        style.badge,
                      )}
                    >
                      {row.severidad}
                    </span>
                  </div>

                  <div className="mt-2 grid gap-2 text-xs sm:grid-cols-2">
                    <div>
                      <p className="font-medium text-foreground">
                        Causa probable
                      </p>
                      <p className="mt-0.5 text-muted">{row.causa}</p>
                    </div>
                    {row.por_que_ahora && (
                      <div>
                        <p className="font-medium text-foreground">
                          Por qué ahora
                        </p>
                        <p className="mt-0.5 text-muted">{row.por_que_ahora}</p>
                      </div>
                    )}
                  </div>

                  {evidence.length > 0 && (
                    <div className="mt-2">
                      <p className="text-[10px] font-medium uppercase tracking-wide text-muted">
                        Evidencia
                      </p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {evidence.map((item) => (
                          <span
                            key={`${item.label}-${item.value}`}
                            className="rounded bg-muted/15 px-1.5 py-1 text-[10px] text-foreground"
                          >
                            {formatEvidence(item)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {typeof row.impacto_unidades === "number" &&
                    row.impacto_unidades > 0 && (
                      <p
                        className="mt-2 text-[10px] text-muted"
                        title="Magnitud usada solo para desempatar alertas del mismo tipo"
                      >
                        Magnitud dentro del tipo:{" "}
                        {Number.isInteger(row.impacto_unidades)
                          ? row.impacto_unidades
                          : row.impacto_unidades.toFixed(1)}{" "}
                        unidades
                      </p>
                    )}

                  <div className="mt-2 rounded-md bg-primary/10 px-2 py-1.5 text-xs text-primary">
                    <p className="inline-flex items-center gap-1 font-medium">
                      <ArrowRightIcon
                        className="h-3.5 w-3.5 shrink-0"
                        aria-hidden="true"
                      />
                      Siguiente acción recomendada
                    </p>
                    <p className="mt-0.5">{row.accion}</p>
                  </div>

                  {row.recomendacion_no_confirmada && (
                    <p className="mt-1.5 text-[10px] text-muted">
                      Recomendación basada en señales: el conteo físico aún no
                      está confirmado.
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-border bg-surface p-6 text-center text-sm text-muted">
          Sin foquitos detectados.
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

export default AlertCards;
