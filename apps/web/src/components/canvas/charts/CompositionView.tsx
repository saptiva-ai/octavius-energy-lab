"use client";

import * as React from "react";
import { TableCellsIcon } from "@heroicons/react/24/outline";
import type { ChartData } from "@/lib/types";
import { cn } from "@/lib/utils";

interface RelatedRow {
  label: string;
  value: number;
  dimension: string | null;
}

interface RelatedPanel {
  id: string;
  sequence: number;
  title: string;
  status: string;
  visual: string;
  metric_id: string;
  metric_label: string;
  unit: string | null;
  period: string;
  filters: Record<string, string>;
  data_as_of: string | null;
  dimension: string | null;
  finding: string | null;
  contradictions: string[];
  state_message: string | null;
  rows: RelatedRow[];
  provenance?: Record<string, string>;
}

interface RelatedViews {
  version: string;
  status: string;
  reading: string;
  focus_panel_id: string | null;
  stop_reason: string;
  shared_context: {
    metric_id: string;
    metric_label: string;
    unit: string | null;
    period: string | null;
    filters: Record<string, string>;
    data_as_of: string | null;
  };
  panels: RelatedPanel[];
  unlinked_contradictions: string[];
}

interface CompositionViewProps {
  chart: ChartData;
  className?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseRelatedViews(value: unknown): RelatedViews | null {
  if (!isRecord(value) || !Array.isArray(value.panels)) return null;
  const context = isRecord(value.shared_context) ? value.shared_context : {};
  const panels = value.panels
    .filter(isRecord)
    .map((panel, index): RelatedPanel | null => {
      if (typeof panel.id !== "string" || !Array.isArray(panel.rows)) {
        return null;
      }
      const rows = panel.rows.filter(isRecord).flatMap((row) =>
        typeof row.label === "string" &&
        typeof row.value === "number" &&
        Number.isFinite(row.value)
          ? [
              {
                label: row.label,
                value: row.value,
                dimension:
                  typeof row.dimension === "string" ? row.dimension : null,
              },
            ]
          : [],
      );
      return {
        id: panel.id,
        sequence:
          typeof panel.sequence === "number" ? panel.sequence : index + 1,
        title:
          typeof panel.title === "string" ? panel.title : `Panel ${index + 1}`,
        status: typeof panel.status === "string" ? panel.status : "empty",
        visual: typeof panel.visual === "string" ? panel.visual : "table",
        metric_id:
          typeof panel.metric_id === "string" ? panel.metric_id : "metric",
        metric_label:
          typeof panel.metric_label === "string"
            ? panel.metric_label
            : "Métrica",
        unit: typeof panel.unit === "string" ? panel.unit : null,
        period: typeof panel.period === "string" ? panel.period : "",
        filters: isRecord(panel.filters)
          ? Object.fromEntries(
              Object.entries(panel.filters).filter(
                (entry): entry is [string, string] =>
                  typeof entry[1] === "string",
              ),
            )
          : {},
        data_as_of:
          typeof panel.data_as_of === "string" ? panel.data_as_of : null,
        dimension: typeof panel.dimension === "string" ? panel.dimension : null,
        finding: typeof panel.finding === "string" ? panel.finding : null,
        contradictions: Array.isArray(panel.contradictions)
          ? panel.contradictions.filter(
              (item): item is string => typeof item === "string",
            )
          : [],
        state_message:
          typeof panel.state_message === "string" ? panel.state_message : null,
        rows,
        provenance: isRecord(panel.provenance)
          ? Object.fromEntries(
              Object.entries(panel.provenance).filter(
                (entry): entry is [string, string] =>
                  typeof entry[1] === "string",
              ),
            )
          : {},
      };
    })
    .filter((panel): panel is RelatedPanel => panel !== null)
    .sort((left, right) => left.sequence - right.sequence);

  return {
    version: typeof value.version === "string" ? value.version : "1",
    status: typeof value.status === "string" ? value.status : "partial",
    reading:
      typeof value.reading === "string"
        ? value.reading
        : "observational_not_causal",
    focus_panel_id:
      typeof value.focus_panel_id === "string" ? value.focus_panel_id : null,
    stop_reason:
      typeof value.stop_reason === "string" ? value.stop_reason : "completado",
    shared_context: {
      metric_id:
        typeof context.metric_id === "string" ? context.metric_id : "metric",
      metric_label:
        typeof context.metric_label === "string"
          ? context.metric_label
          : "Métrica",
      unit: typeof context.unit === "string" ? context.unit : null,
      period: typeof context.period === "string" ? context.period : null,
      filters: isRecord(context.filters)
        ? Object.fromEntries(
            Object.entries(context.filters).filter(
              (entry): entry is [string, string] =>
                typeof entry[1] === "string",
            ),
          )
        : {},
      data_as_of:
        typeof context.data_as_of === "string" ? context.data_as_of : null,
    },
    panels,
    unlinked_contradictions: Array.isArray(value.unlinked_contradictions)
      ? value.unlinked_contradictions.filter(
          (item): item is string => typeof item === "string",
        )
      : [],
  };
}

function csvCell(value: unknown): string {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function filtersText(filters: Record<string, string>): string {
  return Object.entries(filters)
    .map(([key, value]) => `${key}=${value}`)
    .join("; ");
}

export function relatedViewsCsv(value: unknown): string {
  const contract = parseRelatedViews(value);
  if (!contract) return "";
  const rows = [
    [
      "panel_id",
      "panel",
      "metric_id",
      "period",
      "filters",
      "unit",
      "label",
      "value",
      "dimension",
    ],
  ];
  for (const panel of contract.panels) {
    if (panel.status !== "ready") continue;
    for (const row of panel.rows) {
      rows.push([
        panel.id,
        panel.title,
        panel.metric_id,
        panel.period,
        filtersText(panel.filters),
        panel.unit ?? "",
        row.label,
        String(row.value),
        row.dimension ?? "",
      ]);
    }
  }
  return rows.map((row) => row.map(csvCell).join(",")).join("\n");
}

function downloadCsv(contract: RelatedViews, title?: string) {
  const csv = relatedViewsCsv(contract);
  if (!csv) return;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${title || "recorrido-analitico"}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function unitLabel(unit: string | null): string {
  const labels: Record<string, string> = {
    count: "unidades",
    currency: "MXN",
    percentage: "%",
    days: "días",
    hours: "horas",
  };
  return unit ? (labels[unit] ?? unit) : "sin unidad declarada";
}

function formatValue(value: number, unit: string | null): string {
  if (unit === "currency") {
    return value.toLocaleString("es-MX", {
      style: "currency",
      currency: "MXN",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  const formatted = value.toLocaleString("es-MX", {
    maximumFractionDigits: 2,
  });
  if (unit === "percentage") return `${formatted}%`;
  return formatted;
}

function panelStepLabel(panel: RelatedPanel): string {
  const labels: Record<string, string> = {
    region: "Región",
    tienda: "Tienda",
    categoria: "Categoría",
  };
  return panel.dimension ? (labels[panel.dimension] ?? panel.title) : "Total";
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    ready: "Con datos",
    empty: "Sin datos",
    omitted: "No disponible",
    not_run: "No ejecutado",
  };
  return labels[status] ?? status;
}

function RelatedChart({ panel }: { panel: RelatedPanel }) {
  if (panel.status !== "ready" || panel.rows.length === 0) {
    return (
      <div className="flex min-h-40 items-center justify-center rounded-lg border border-dashed border-border bg-surface-2 p-5 text-center text-sm text-muted">
        {panel.state_message ?? "Sin datos para este nivel."}
      </div>
    );
  }

  const max = Math.max(...panel.rows.map((row) => Math.abs(row.value)), 1);
  if (panel.visual === "line" && panel.rows.length > 1) {
    const width = 520;
    const height = 180;
    const values = panel.rows.map((row) => row.value);
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const range = maxValue - minValue || 1;
    const points = panel.rows
      .map((row, index) => {
        const x = 20 + (index / (panel.rows.length - 1)) * (width - 40);
        const y = 20 + ((maxValue - row.value) / range) * (height - 40);
        return `${x},${y}`;
      })
      .join(" ");
    return (
      <div className="rounded-lg border border-border bg-surface p-3">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`Tendencia de ${panel.metric_label}`}
          className="h-44 w-full"
        >
          <polyline
            points={points}
            fill="none"
            stroke="currentColor"
            strokeWidth="4"
            strokeLinejoin="round"
            className="text-primary"
          />
        </svg>
        <div className="flex justify-between text-[10px] text-muted">
          <span>{panel.rows[0].label}</span>
          <span>{panel.rows[panel.rows.length - 1].label}</span>
        </div>
      </div>
    );
  }

  return (
    <div
      role="img"
      aria-label={`Ranking por ${panel.dimension ?? "nivel"}`}
      className="space-y-2 rounded-lg border border-border bg-surface p-3"
    >
      {panel.rows.slice(0, 8).map((row) => (
        <div key={`${row.label}-${row.dimension ?? ""}`}>
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="truncate text-foreground">{row.label}</span>
            <span className="shrink-0 tabular-nums text-muted">
              {formatValue(row.value, panel.unit)}
            </span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full rounded-full bg-primary"
              style={{
                width: `${
                  row.value === 0
                    ? 0
                    : Math.max(2, (Math.abs(row.value) / max) * 100)
                }%`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function RelatedTable({ panel }: { panel: RelatedPanel }) {
  if (panel.status !== "ready" || panel.rows.length === 0) return null;
  return (
    <div className="overflow-auto rounded-lg border border-border">
      <table aria-label="Datos del panel" className="w-full min-w-72 text-xs">
        <thead className="bg-surface-2 text-muted">
          <tr>
            <th scope="col" className="px-3 py-2 text-left font-medium">
              {panel.dimension ? panelStepLabel(panel) : "Periodo"}
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              {panel.metric_label} ({unitLabel(panel.unit)})
            </th>
          </tr>
        </thead>
        <tbody>
          {panel.rows.map((row) => (
            <tr
              key={`${row.label}-${row.dimension ?? ""}`}
              className="border-t border-border"
            >
              <td className="px-3 py-2 text-foreground">{row.label}</td>
              <td className="px-3 py-2 text-right tabular-nums text-muted">
                {formatValue(row.value, panel.unit)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CompositionView({ chart, className }: CompositionViewProps) {
  const raw = chart.analytics?.grounding.related_views;
  const contract = React.useMemo(() => parseRelatedViews(raw), [raw]);
  const [activeId, setActiveId] = React.useState(
    contract?.focus_panel_id ?? contract?.panels[0]?.id ?? "",
  );

  React.useEffect(() => {
    setActiveId(contract?.focus_panel_id ?? contract?.panels[0]?.id ?? "");
  }, [contract?.focus_panel_id, contract?.panels]);

  if (!contract || contract.panels.length === 0) return null;
  const active =
    contract.panels.find((panel) => panel.id === activeId) ??
    contract.panels[0];
  const context = contract.shared_context;
  const filterEntries = Object.entries(context.filters);
  const provenance = Object.values(active.provenance ?? {});

  return (
    <section
      role="region"
      aria-label="Recorrido analítico"
      className={cn("min-h-0 space-y-3", className)}
    >
      <header className="rounded-lg border border-border bg-surface-2 p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-foreground">
              Recorrido analítico · {context.metric_label}
            </p>
            <p className="mt-1 text-xs text-muted">
              Lectura observacional: localiza concentraciones y diferencias. No
              demuestra causalidad.
            </p>
          </div>
          <button
            type="button"
            title="Exportar CSV"
            aria-label="Exportar CSV"
            onClick={() => downloadCsv(contract, chart.title)}
            className="rounded p-1.5 text-muted transition-colors hover:bg-surface hover:text-foreground"
          >
            <TableCellsIcon className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted">
          <span>Periodo: {context.period ?? "no declarado"}</span>
          <span>Unidad: {unitLabel(context.unit)}</span>
          <span>
            Fuente: {chart.analytics?.grounding.source ?? "no declarada"}
          </span>
          <span>Corte: {context.data_as_of ?? "no disponible"}</span>
          {filterEntries.map(([key, value]) => (
            <span key={key}>
              {key === "tienda"
                ? "Tienda"
                : key === "categoria"
                  ? "Categoría"
                  : key}
              : {value}
            </span>
          ))}
        </div>
        {contract.status !== "complete" && (
          <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
            Recorrido parcial: {contract.stop_reason.replace(/_/g, " ")}.
          </p>
        )}
        {contract.unlinked_contradictions.map((contradiction) => (
          <p
            key={contradiction}
            className="mt-2 text-xs text-amber-700 dark:text-amber-300"
          >
            Contradicción global: {contradiction}
          </p>
        ))}
      </header>

      <nav aria-label="Niveles del recorrido" className="overflow-x-auto pb-1">
        <div className="flex min-w-max gap-2">
          {contract.panels.map((panel) => {
            const activePanel = panel.id === active.id;
            return (
              <button
                key={panel.id}
                type="button"
                aria-label={`${panel.sequence}. ${panelStepLabel(panel)}`}
                aria-pressed={activePanel}
                onClick={() => setActiveId(panel.id)}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-xs transition-colors",
                  activePanel
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-surface text-muted hover:text-foreground",
                )}
              >
                {panel.sequence} {panelStepLabel(panel)}
                {panel.status !== "ready" && (
                  <span className="ml-1 opacity-75">
                    · {statusLabel(panel.status)}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </nav>

      <article
        aria-labelledby={`related-panel-${active.id}`}
        className="rounded-lg border border-border bg-surface p-3"
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted">
              Nivel {active.sequence} de {contract.panels.length}
            </p>
            <h3
              id={`related-panel-${active.id}`}
              className="text-sm font-semibold text-foreground"
            >
              {active.title}
            </h3>
          </div>
          <span className="rounded-full bg-surface-2 px-2 py-1 text-[10px] text-muted">
            {statusLabel(active.status)}
          </span>
        </div>

        {active.finding && (
          <p className="mt-2 text-sm font-medium text-foreground">
            {active.finding}
          </p>
        )}
        {active.contradictions.map((contradiction) => (
          <p
            key={contradiction}
            className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-xs text-amber-800 dark:text-amber-200"
          >
            Contradicción: {contradiction}
          </p>
        ))}

        <div className="mt-3 grid min-h-0 gap-3 lg:grid-cols-[minmax(0,3fr)_minmax(16rem,2fr)]">
          <RelatedChart panel={active} />
          <RelatedTable panel={active} />
        </div>

        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 border-t border-border pt-2 text-[10px] text-muted">
          <span>Métrica: {active.metric_label}</span>
          <span>Periodo: {active.period || "no declarado"}</span>
          <span>Unidad: {unitLabel(active.unit)}</span>
          {Object.entries(active.filters).map(([key, value]) => (
            <span key={key}>
              {key}={value}
            </span>
          ))}
          {provenance.length > 0 && (
            <span>Proveniencia curada: {provenance.join(" · ")}</span>
          )}
        </div>
      </article>
    </section>
  );
}

export default CompositionView;
