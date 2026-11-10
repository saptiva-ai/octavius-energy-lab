import * as React from "react";
import { cn } from "@/lib/utils";
import type { ChartData } from "@/lib/types";
import { PredictionList } from "./PredictionList";

interface PredictionViewProps {
  chart: ChartData;
  className?: string;
}

/** La decisión operativa es secuencial: qué SKU atender primero y por qué.
 * El Sankey anterior ponderaba stock restante, no riesgo. La lista conserva
 * el conjunto grounded y hace explícitos prioridad, evidencia y recomendación. */
export function PredictionView({ chart, className }: PredictionViewProps) {
  return (
    <div className={cn("h-full min-h-0", className)}>
      <PredictionList chart={chart} />
    </div>
  );
}

export default PredictionView;
