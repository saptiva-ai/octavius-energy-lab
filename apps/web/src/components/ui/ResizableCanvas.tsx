"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useCanvas } from "@/context/CanvasContext";
import { AuditDetailView } from "@/components/canvas/views/AuditDetailView";
import { ArrowDownTrayIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { cn } from "@/lib/utils";

const MIN_WIDTH = 350;
const MAX_WIDTH = 800;
const DEFAULT_WIDTH = 400;

interface ResizableCanvasProps {
  className?: string;
}

export function ResizableCanvas({ className }: ResizableCanvasProps = {}) {
  const { isOpen, content, closeCanvas, reportPdfUrl } = useCanvas();
  const [width, setWidth] = React.useState<number>(DEFAULT_WIDTH);
  const [isDragging, setIsDragging] = React.useState(false);

  // Restore width from localStorage on mount
  React.useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const savedWidth = localStorage.getItem("canvas-width");
    if (savedWidth) {
      const parsedWidth = parseInt(savedWidth, 10);
      if (parsedWidth >= MIN_WIDTH && parsedWidth <= MAX_WIDTH) {
        setWidth(parsedWidth);
        return;
      }
    }

    const defaultViewportWidth = Math.round(window.innerWidth * 0.4);
    const targetWidth = Math.max(
      MIN_WIDTH,
      Math.min(MAX_WIDTH, defaultViewportWidth),
    );
    setWidth(targetWidth);
  }, []);

  // Persist width to localStorage when changed
  React.useEffect(() => {
    if (width !== DEFAULT_WIDTH) {
      localStorage.setItem("canvas-width", width.toString());
    }
  }, [width]);

  // Mouse event handlers for resize
  const handleMouseDown = React.useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleMouseMove = React.useCallback(
    (e: MouseEvent) => {
      if (!isDragging) return;

      const newWidth = window.innerWidth - e.clientX;
      const clampedWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, newWidth));
      setWidth(clampedWidth);
    },
    [isDragging],
  );

  const handleMouseUp = React.useCallback(() => {
    setIsDragging(false);
  }, []);

  // Double-click to expand to 50% width
  const handleDoubleClick = React.useCallback(() => {
    const halfWidth = window.innerWidth * 0.5;
    const targetWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, halfWidth));
    setWidth(targetWidth);
  }, []);

  const handleCopy = React.useCallback(async () => {
    if (!content) return;
    const json = JSON.stringify(content, null, 2);
    await navigator.clipboard.writeText(json);
  }, [content]);

  const handleDownload = React.useCallback(() => {
    if (!content) return;

    // Extract a usable validation_report_id for on-demand download fallback
    const reportId =
      (content.metadata as any)?.decision_metadata?.validation_report_id ||
      (content.metadata as any)?.validation_report_id ||
      (content as any)?.payload?.validation_report_id;

    const url =
      reportPdfUrl ||
      // Prefer generated PDF attachment if present (metadata)
      (content.metadata as any)?.attachments?.full_report_pdf?.url ||
      (content.metadata as any)?.attachments?.full_report_pdf?.presigned_url ||
      (content.metadata as any)?.attachments?.report_pdf_url ||
      content.metadata?.report_pdf_url ||
      content.metadata?.report_url ||
      content.metadata?.pdf_url ||
      // Fallback to payload attachments if metadata is missing
      (content as any)?.payload?.attachments?.full_report_pdf?.url ||
      (content as any)?.payload?.attachments?.full_report_pdf?.presigned_url ||
      (content as any)?.payload?.attachments?.report_pdf_url ||
      (content as any)?.payload?.report_pdf_url ||
      // Legacy on-demand endpoint if we only have the report id
      (reportId
        ? `${(
            process.env.NEXT_PUBLIC_API_URL ||
            (typeof window !== "undefined" ? window.location.origin : "")
          ).replace(/\/$/, "")}/api/reports/audit/${reportId}/download`
        : null);

    if (url) {
      window.open(url, "_blank", "noopener,noreferrer");
      return;
    }

    const filename =
      content.metadata?.display_name ||
      content.metadata?.filename ||
      content.doc_name ||
      "reporte-auditoria";

    const blob = new Blob([JSON.stringify(content, null, 2)], {
      type: "application/json",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${filename}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 3000);
  }, [content, reportPdfUrl]);

  // Attach global mouse listeners when dragging
  React.useEffect(() => {
    if (isDragging) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    } else {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  return (
    <AnimatePresence>
      {isOpen && content && (
        <motion.div
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "spring", damping: 30, stiffness: 300 }}
          className={cn(
            "relative h-full border-l border-white/10 shadow-2xl",
            className,
          )}
          style={{ width: `${width}px`, backgroundColor: "#232B3A" }}
        >
          {/* Resize Handle */}
          <div
            onMouseDown={handleMouseDown}
            onDoubleClick={handleDoubleClick}
            className={`absolute left-0 top-0 h-full w-1.5 cursor-col-resize transition-colors ${
              isDragging ? "bg-white/50" : "hover:bg-white/30"
            }`}
            title="Arrastra para redimensionar. Doble clic para expandir al 50%."
          />

          {/* Header */}
          <div
            className="flex items-center justify-between gap-2 px-3 py-1.5 border-b border-white/10"
            style={{ backgroundColor: "#232B3A" }}
          >
            <h2 className="text-sm font-semibold text-white">
              Panel de hallazgos
            </h2>
            <div className="flex items-center gap-1">
              <button
                onClick={handleDownload}
                className="flex items-center justify-center rounded-md border border-white/10 bg-white/5 p-1.5 text-xs font-semibold text-white hover:border-white/30 hover:bg-white/10 transition-colors"
                aria-label="Descargar"
              >
                <ArrowDownTrayIcon className="h-4 w-4" />
              </button>
              <button
                onClick={closeCanvas}
                className="flex items-center justify-center rounded-md border border-white/10 bg-white/5 p-1.5 text-xs font-semibold text-white hover:border-white/30 hover:bg-white/10 transition-colors"
                aria-label="Cerrar"
                title="Cerrar"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="h-[calc(100%-4rem)] overflow-auto p-6">
            <AuditDetailView report={content} />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
