import * as React from "react";
import type { ChartData } from "@/lib/types";

interface EditorialTableProps {
  chart: ChartData;
}

interface ColumnMeta {
  key: string;
  label: string;
  data_type: string;
  unit: string | null;
  format: string;
  align: "left" | "right";
  role: string;
  nullable: boolean;
}

interface TableContract {
  columns: ColumnMeta[];
  observation?: string;
  primary_row_indices: number[];
  primary_columns: string[];
  order?: { label?: string };
  pagination?: {
    page_size?: number;
    returned_rows?: number;
    total_rows?: number;
    truncated?: boolean;
  };
  visualization_recommendation?: {
    status?: string;
    shape?: string | null;
  };
}

function humanize(value: string): string {
  const label = value.replace(/_/g, " ").trim();
  return label ? label[0].toUpperCase() + label.slice(1) : "Columna";
}

function fallbackColumns(rows: Array<Record<string, unknown>>): ColumnMeta[] {
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return keys.map((key) => {
    const values = rows.map((row) => row[key]).filter((value) => value != null);
    const numeric =
      values.length > 0 &&
      values.every(
        (value) => typeof value === "number" && Number.isFinite(value),
      );
    const boolean =
      values.length > 0 && values.every((value) => typeof value === "boolean");
    return {
      key,
      label: humanize(key),
      data_type: numeric ? "number" : boolean ? "boolean" : "text",
      unit: null,
      format: numeric ? "decimal" : boolean ? "boolean" : "text",
      align: numeric ? "right" : "left",
      role: "unknown",
      nullable: rows.some((row) => row[key] == null),
    };
  });
}

function tableContract(chart: ChartData): TableContract {
  const raw = chart.analytics?.grounding?.table_contract;
  if (raw && typeof raw === "object") {
    const contract = raw as Partial<TableContract>;
    if (Array.isArray(contract.columns)) {
      return {
        columns: contract.columns,
        observation: contract.observation,
        primary_row_indices: Array.isArray(contract.primary_row_indices)
          ? contract.primary_row_indices
          : [],
        primary_columns: Array.isArray(contract.primary_columns)
          ? contract.primary_columns
          : [],
        order: contract.order,
        pagination: contract.pagination,
        visualization_recommendation: contract.visualization_recommendation,
      };
    }
  }
  return {
    columns: fallbackColumns(chart.analytics?.table_data ?? []),
    primary_row_indices: [],
    primary_columns: [],
    order: { label: "Orden devuelto por la consulta" },
    pagination: { page_size: 25 },
    visualization_recommendation: {
      status: "table_only",
      shape: null,
    },
  };
}

function formatCell(value: unknown, format: string): string {
  if (value == null || value === "") return "Sin dato";
  if (format === "boolean") return value === true ? "Sí" : "No";
  if (format === "date" && typeof value === "string") {
    const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
    if (!Number.isNaN(date.valueOf())) {
      return date.toLocaleDateString("es-MX", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      });
    }
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    if (format === "currency_mxn") {
      return `$${value.toLocaleString("es-MX", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;
    }
    if (format === "percent") {
      return `${value.toLocaleString("es-MX", {
        maximumFractionDigits: 1,
      })}%`;
    }
    return value.toLocaleString("es-MX", {
      maximumFractionDigits: format === "integer" ? 0 : 2,
    });
  }
  return String(value);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

const SHAPE_LABELS: Record<string, string> = {
  line: "línea",
  horizontal_bar: "barras horizontales",
  scatter: "dispersión",
};

export function EditorialTable({ chart }: EditorialTableProps) {
  const analytics = chart.analytics;
  const rows = analytics?.table_data ?? [];
  const contract = tableContract(chart);
  const pageSize = Math.max(
    1,
    Math.min(contract.pagination?.page_size ?? 25, 100),
  );
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const [page, setPage] = React.useState(0);
  const safePage = Math.min(page, totalPages - 1);
  const visibleRows = rows.slice(
    safePage * pageSize,
    (safePage + 1) * pageSize,
  );
  const primaryRows = new Set(contract.primary_row_indices);
  const primaryColumns = new Set(contract.primary_columns);
  const exploratory = analytics?.grounding?.exploratory;
  const assumptions =
    exploratory && typeof exploratory === "object"
      ? stringList((exploratory as Record<string, unknown>).supuestos)
      : [];
  const caveats =
    exploratory && typeof exploratory === "object"
      ? stringList((exploratory as Record<string, unknown>).caveats)
      : [];
  const recommendation = contract.visualization_recommendation;
  const recommendedShape =
    recommendation?.status === "validated" && recommendation.shape
      ? (SHAPE_LABELS[recommendation.shape] ?? recommendation.shape)
      : null;

  return (
    <section className="min-h-0 space-y-3" aria-label="Tabla editorial">
      <div className="rounded-lg border border-border bg-surface-2 p-3 text-xs">
        {contract.observation && (
          <p className="font-semibold text-foreground">
            {contract.observation}
          </p>
        )}
        {contract.primary_row_indices.length > 0 && (
          <p className="mt-1 text-muted">
            Respuesta principal:{" "}
            {contract.primary_row_indices
              .map((rowIndex) => `fila ${rowIndex + 1}`)
              .join(", ")}
          </p>
        )}
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-muted">
          <span>Fuente: {analytics?.grounding?.source ?? "no declarada"}</span>
          <span>Corte: {analytics?.data_as_of ?? "no disponible"}</span>
          <span>
            {contract.order?.label ?? "Orden devuelto por la consulta"}
          </span>
          <span>
            {rows.length} filas recibidas
            {contract.pagination?.total_rows != null &&
            contract.pagination.total_rows !== rows.length
              ? ` de ${contract.pagination.total_rows}`
              : ""}
          </span>
        </div>
        {assumptions.map((assumption) => (
          <p key={assumption} className="mt-1 text-muted">
            Supuesto: {assumption}
          </p>
        ))}
        {caveats.map((caveat) => (
          <p key={caveat} className="mt-1 text-amber-700 dark:text-amber-300">
            Caveat: {caveat}
          </p>
        ))}
        {contract.pagination?.truncated && (
          <p className="mt-1 text-amber-700 dark:text-amber-300">
            Resultado limitado por el sandbox.
          </p>
        )}
        <p className="mt-1 text-muted">
          {recommendedShape
            ? `Gráfica sugerida: ${recommendedShape}, con roles de columna validados.`
            : "Vista segura: tabla. No hay roles suficientes para recomendar una gráfica."}
        </p>
      </div>

      <div className="overflow-auto rounded-lg border border-border">
        <table className="w-full min-w-max text-xs">
          <thead className="sticky top-0 bg-surface-2 text-muted">
            <tr>
              {contract.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={`px-3 py-2 font-medium ${
                    column.align === "right" ? "text-right" : "text-left"
                  }`}
                >
                  <span className="block text-foreground">{column.label}</span>
                  {column.unit && (
                    <span className="block text-[10px] font-normal">
                      {column.unit}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, visibleIndex) => {
              const rowIndex = safePage * pageSize + visibleIndex;
              const primary = primaryRows.has(rowIndex);
              return (
                <tr
                  key={rowIndex}
                  data-testid={`editorial-row-${rowIndex}`}
                  data-primary={primary ? "true" : "false"}
                  aria-label={primary ? "Respuesta principal" : undefined}
                  className={`border-t border-border ${
                    primary ? "bg-primary/10" : "bg-surface"
                  }`}
                >
                  {contract.columns.map((column) => (
                    <td
                      key={column.key}
                      className={`px-3 py-2 ${
                        column.align === "right"
                          ? "text-right tabular-nums"
                          : "text-left"
                      } ${
                        primary && primaryColumns.has(column.key)
                          ? "font-semibold text-foreground"
                          : "text-muted"
                      }`}
                    >
                      {formatCell(row[column.key], column.format)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <nav
          aria-label="Paginación de tabla"
          className="flex items-center justify-between text-xs"
        >
          <button
            type="button"
            disabled={safePage === 0}
            onClick={() => setPage((current) => Math.max(0, current - 1))}
            className="rounded border border-border px-3 py-1.5 disabled:opacity-40"
          >
            Anterior
          </button>
          <span className="text-muted">
            Página {safePage + 1} de {totalPages}
          </span>
          <button
            type="button"
            disabled={safePage >= totalPages - 1}
            onClick={() =>
              setPage((current) => Math.min(totalPages - 1, current + 1))
            }
            className="rounded border border-border px-3 py-1.5 disabled:opacity-40"
          >
            Siguiente
          </button>
        </nav>
      )}
    </section>
  );
}

export default EditorialTable;
