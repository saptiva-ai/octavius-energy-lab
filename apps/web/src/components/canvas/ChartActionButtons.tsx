"use client";

import {
  ArrowDownTrayIcon,
  TableCellsIcon,
  ArrowPathIcon,
} from "@heroicons/react/24/outline";

interface ChartActionButtonsProps {
  onDownloadPNG: () => void;
  onExportCSV: () => void;
  onResetZoom?: () => void;
}

/**
 * ChartActionButtons - Reusable action buttons for chart operations
 *
 * Features:
 * - Reset zoom to original view
 * - Download chart as PNG
 * - Export data as CSV
 * - Compact horizontal layout aligned to the right
 *
 * Usage:
 *   <ChartActionButtons
 *     onDownloadPNG={handleDownloadPNG}
 *     onExportCSV={handleExportCSV}
 *     onResetZoom={handleResetZoom}
 *   />
 */
export function ChartActionButtons({
  onDownloadPNG,
  onExportCSV,
  onResetZoom,
}: ChartActionButtonsProps) {
  return (
    <div className="flex items-center justify-end gap-1">
      {onResetZoom && (
        <button
          onClick={onResetZoom}
          className="p-1.5 text-muted hover:text-foreground hover:bg-surface-2 rounded transition-colors"
          title="Restablecer zoom"
        >
          <ArrowPathIcon className="h-4 w-4" />
        </button>
      )}
      <button
        onClick={onDownloadPNG}
        className="p-1.5 text-muted hover:text-foreground hover:bg-surface-2 rounded transition-colors"
        title="Descargar PNG"
      >
        <ArrowDownTrayIcon className="h-4 w-4" />
      </button>
      <button
        onClick={onExportCSV}
        className="p-1.5 text-muted hover:text-foreground hover:bg-surface-2 rounded transition-colors"
        title="Exportar CSV"
      >
        <TableCellsIcon className="h-4 w-4" />
      </button>
    </div>
  );
}
