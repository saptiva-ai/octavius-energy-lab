"use client";

import * as React from "react";
import {
  ArchiveBoxIcon,
  ArrowTrendingDownIcon,
  ArrowTrendingUpIcon,
  BuildingStorefrontIcon,
  ChartBarIcon,
  ChatBubbleLeftRightIcon,
  ClockIcon,
  CubeIcon,
  CurrencyDollarIcon,
  ExclamationTriangleIcon,
  QuestionMarkCircleIcon,
  ScaleIcon,
  Squares2X2Icon,
  ViewfinderCircleIcon,
} from "@heroicons/react/24/outline";

type Icono = React.ComponentType<React.SVGProps<SVGSVGElement>>;

/**
 * El catálogo del plugin declara un `icono` por vista o sugerencia. La web lo
 * pinta como SVG del sistema de iconos, nunca como emoji (equipo,
 * 2026-10-19). Acepta nombres semánticos y, mientras el catálogo no se
 * actualice, los emojis que hoy trae; lo desconocido cae a un icono neutro.
 */
const ICONOS: Record<string, Icono> = {
  tendencia: ArrowTrendingUpIcon,
  baja: ArrowTrendingDownIcon,
  ranking: ChartBarIcon,
  comparacion: ChartBarIcon,
  categoria: Squares2X2Icon,
  inventario: CubeIcon,
  sin_desplazamiento: ArchiveBoxIcon,
  alerta: ExclamationTriangleIcon,
  venta: CurrencyDollarIcon,
  medida: ScaleIcon,
  objetivo: ViewfinderCircleIcon,
  tienda: BuildingStorefrontIcon,
  hora: ClockIcon,
  pregunta: QuestionMarkCircleIcon,
  "📈": ArrowTrendingUpIcon,
  "📉": ArrowTrendingDownIcon,
  "🥤": ChartBarIcon,
  "📊": ChartBarIcon,
  "🏢": Squares2X2Icon,
  "📦": ArchiveBoxIcon,
  "✅": CubeIcon,
  "❓": QuestionMarkCircleIcon,
  "🚨": ExclamationTriangleIcon,
  "🧾": CurrencyDollarIcon,
  "📏": ScaleIcon,
  "🎯": ViewfinderCircleIcon,
  "🏬": BuildingStorefrontIcon,
};

export function iconoAyuda(icono?: string): Icono {
  return (icono && ICONOS[icono.trim()]) || ChatBubbleLeftRightIcon;
}

export function IconoAyuda({
  icono,
  className,
}: {
  icono?: string;
  className?: string;
}) {
  const Componente = iconoAyuda(icono);
  return <Componente aria-hidden="true" className={className} />;
}
