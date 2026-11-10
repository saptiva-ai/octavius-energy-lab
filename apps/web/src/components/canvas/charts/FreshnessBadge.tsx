import * as React from "react";
import { cn } from "@/lib/utils";
import type { AnalyticsFreshness } from "@/lib/contracts";

const LABELS: Record<AnalyticsFreshness, string> = {
  intraday: "Intradía",
  daily: "Forecast diario",
  day_closed: "Día cerrado",
  monthly: "Mensual",
  unknown: "Frescura desconocida",
};

const STYLES: Record<AnalyticsFreshness, string> = {
  intraday: "bg-emerald-500/15 text-emerald-500",
  daily: "bg-amber-500/15 text-amber-500",
  day_closed: "bg-sky-500/15 text-sky-500",
  monthly: "bg-violet-500/15 text-violet-500",
  unknown: "bg-muted/20 text-muted",
};

interface FreshnessBadgeProps {
  freshness: AnalyticsFreshness;
  dataAsOf?: string | null;
  className?: string;
}

/** Chip compacto: de qué corte es el dato, para no implicar tiempo real sobre
 * datos día-cerrado (regla del cliente en el catálogo del plugin). */
export function FreshnessBadge({
  freshness,
  dataAsOf,
  className,
}: FreshnessBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
        STYLES[freshness] ?? STYLES.unknown,
        className,
      )}
      title={dataAsOf ? `Datos al corte: ${dataAsOf}` : undefined}
    >
      {LABELS[freshness] ?? LABELS.unknown}
      {dataAsOf ? <span className="opacity-70">· {dataAsOf}</span> : null}
    </span>
  );
}

export default FreshnessBadge;
