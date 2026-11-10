import * as React from "react";

interface RegionalRankingProps {
  rows: Array<Record<string, unknown>>;
}

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function RegionalRanking({ rows }: RegionalRankingProps) {
  const ranked = rows
    .map((row) => ({
      label: String(row.label ?? ""),
      value: numeric(row.value),
      numerator: numeric(row.numerator),
      denominator: numeric(row.denominator),
    }))
    .filter(
      (row) =>
        row.label &&
        row.value != null &&
        row.numerator != null &&
        row.denominator != null,
    )
    .sort(
      (left, right) =>
        Number(right.value) - Number(left.value) ||
        left.label.localeCompare(right.label, "es"),
    );

  if (ranked.length === 0) return null;

  return (
    <aside className="min-h-0 overflow-auto rounded-lg border border-border bg-surface p-3">
      <h3 className="text-xs font-semibold text-foreground">
        Ranking regional, peor primero
      </h3>
      <p className="mt-1 text-[10px] text-muted">
        0%: sin faltantes observados · Gris: sin datos
      </p>
      <ol className="mt-2 space-y-2">
        {ranked.map((row, index) => (
          <li
            key={row.label}
            className="grid grid-cols-[1.5rem_1fr_auto] items-center gap-2 text-xs"
          >
            <span className="text-muted">{index + 1}</span>
            <span className="truncate text-foreground">{row.label}</span>
            <span className="text-right">
              <strong className="font-semibold text-foreground">
                {Number(row.value).toFixed(1)}%
              </strong>
              <span className="ml-1 text-[10px] text-muted">
                {Number(row.numerator).toLocaleString("es-MX")} /{" "}
                {Number(row.denominator).toLocaleString("es-MX")}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </aside>
  );
}

export default RegionalRanking;
