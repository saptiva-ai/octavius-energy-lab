"use client";

/**
 * FileCard - Displays uploaded file with progress and review button
 *
 * States:
 * - uploading: Shows skeleton + progress bar
 * - processing: Shows processing message
 * - ready: Shows "Iniciar revisión" button
 * - reviewing: Shows review progress
 * - completed: Shows "Ver resultados" button
 * - error: Shows error message
 */

import { useState } from "react";
import { cn } from "../../lib/utils";

export type FileCardState =
  | "uploading"
  | "processing"
  | "ready"
  | "reviewing"
  | "completed"
  | "error";

export interface FileCardProps {
  filename: string;
  fileSize: number;
  docId?: string;
  state: FileCardState;
  progress?: number;
  errorMessage?: string;
  onStartReview?: (docId: string) => void;
  onViewResults?: (docId: string) => void;
  onCancel?: () => void;
  className?: string;
}

export function FileCard({
  filename,
  fileSize,
  docId,
  state,
  progress = 0,
  errorMessage,
  onStartReview,
  onViewResults,
  onCancel,
  className,
}: FileCardProps) {
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getFileExtension = (name: string): string => {
    const ext = name.split(".").pop()?.toUpperCase() || "FILE";
    return ext;
  };

  const getStateMessage = (): string => {
    switch (state) {
      case "uploading":
        return `Subiendo... ${Math.round(progress)}%`;
      case "processing":
        return "Procesando documento...";
      case "ready":
        return "Adjunto listo"; // MVP-LOCK: Changed from "Listo para revisar"
      case "reviewing":
        return `Revisando... ${Math.round(progress)}%`;
      case "completed":
        return "Revisión completada";
      case "error":
        return errorMessage || "Error al procesar";
      default:
        return "";
    }
  };

  const getStateColor = (): string => {
    switch (state) {
      case "uploading":
      case "processing":
      case "reviewing":
        return "text-blue-400";
      case "ready":
        return "text-green-400";
      case "completed":
        return "text-primary";
      case "error":
        return "text-red-400";
      default:
        return "text-text-muted";
    }
  };

  return (
    <div
      className={cn(
        "rounded-xl border bg-surface p-4 shadow-sm transition-all",
        state === "error" && "border-red-500/40 bg-red-500/5",
        state !== "error" && "border-border/40",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        {/* File Icon */}
        <div
          className={cn(
            "flex-shrink-0 rounded-lg p-3",
            state === "uploading" && "animate-pulse bg-surface-2",
            state !== "uploading" && "bg-surface-2",
          )}
        >
          <svg
            className="h-8 w-8 text-primary"
            viewBox="0 0 24 24"
            fill="currentColor"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
            <path d="M14 2v6h6M12 18v-6M9 15l3 3 3-3" />
          </svg>
          <div className="mt-1 text-center text-[10px] font-bold text-text-muted">
            {getFileExtension(filename)}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Filename */}
          <h4 className="text-sm font-medium text-text truncate">{filename}</h4>

          {/* Size & State */}
          <div className="mt-1 flex items-center gap-2 text-xs">
            <span className="text-text-muted">{formatFileSize(fileSize)}</span>
            <span className="text-text-muted">•</span>
            <span className={getStateColor()}>{getStateMessage()}</span>
          </div>

          {/* Progress Bar */}
          {(state === "uploading" ||
            state === "reviewing" ||
            state === "processing") && (
            <div className="mt-3 w-full bg-surface-2 rounded-full h-1.5 overflow-hidden">
              <div
                className={cn(
                  "h-full transition-all duration-300",
                  state === "reviewing" ? "bg-primary" : "bg-blue-500",
                )}
                style={{ width: `${progress}%` }}
              />
            </div>
          )}

          {/* Skeleton (uploading) */}
          {state === "uploading" && (
            <div className="mt-3 space-y-2">
              <div className="h-2 bg-surface-2 rounded animate-pulse w-3/4" />
              <div className="h-2 bg-surface-2 rounded animate-pulse w-1/2" />
            </div>
          )}

          {/* Actions */}
          <div className="mt-3 flex items-center gap-2">
            {/* MVP-LOCK: Hide "Iniciar revisión" button unless explicitly enabled */}
            {process.env.NEXT_PUBLIC_ENABLE_REVIEW === "true" &&
              state === "ready" &&
              docId &&
              onStartReview && (
                <button
                  onClick={() => onStartReview(docId)}
                  className={cn(
                    "px-3 py-1.5 rounded-lg text-xs font-medium",
                    "bg-primary/15 text-primary border border-primary/40",
                    "hover:bg-primary/20 transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                  )}
                >
                  Iniciar revisión
                </button>
              )}

            {state === "completed" && docId && onViewResults && (
              <button
                onClick={() => onViewResults(docId)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-medium",
                  "bg-primary text-white",
                  "hover:bg-primary/90 transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                )}
              >
                Ver resultados
              </button>
            )}

            {state === "processing" && (
              <div className="flex items-center gap-2 text-xs text-text-muted">
                <svg
                  className="h-4 w-4 animate-spin"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                <span>Extrayendo texto...</span>
              </div>
            )}

            {(state === "uploading" || state === "processing") && onCancel && (
              <button
                onClick={onCancel}
                className={cn(
                  "ml-auto px-2 py-1 rounded text-xs font-medium",
                  "text-text-muted hover:text-text hover:bg-surface-2",
                  "transition-colors",
                )}
              >
                Cancelar
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
