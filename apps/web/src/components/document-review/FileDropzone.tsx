"use client";

/**
 * FileDropzone - Drag & drop file upload component
 *
 * Features:
 * - Drag & drop support
 * - File validation (PDF, PNG, JPG)
 * - Size limits (50MB)
 * - Visual feedback
 * - Accessibility
 */

import { useCallback, useState } from "react";
import { cn } from "../../lib/utils";

export interface FileDropzoneProps {
  onFileSelect: (file: File) => void;
  maxSizeMB?: number;
  acceptedTypes?: string[];
  disabled?: boolean;
  className?: string;
}

const DEFAULT_ACCEPTED_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/jpg",
];

export function FileDropzone({
  onFileSelect,
  maxSizeMB = 50,
  acceptedTypes = DEFAULT_ACCEPTED_TYPES,
  disabled = false,
  className,
}: FileDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validateFile = useCallback(
    (file: File): string | null => {
      // Check file type
      if (!acceptedTypes.includes(file.type)) {
        return `Tipo de archivo no soportado. Usa: ${acceptedTypes
          .map((t) => t.split("/")[1].toUpperCase())
          .join(", ")}`;
      }

      // Check file size
      const maxSizeBytes = maxSizeMB * 1024 * 1024;
      if (file.size > maxSizeBytes) {
        return `Archivo muy grande. Máximo: ${maxSizeMB}MB`;
      }

      return null;
    },
    [acceptedTypes, maxSizeMB],
  );

  const handleFileSelect = useCallback(
    (file: File) => {
      setError(null);

      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }

      onFileSelect(file);
    },
    [validateFile, onFileSelect],
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();

      if (!disabled && !isDragging) {
        setIsDragging(true);
      }
    },
    [disabled, isDragging],
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    // Only set dragging to false if we're leaving the dropzone
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX;
    const y = e.clientY;

    if (x < rect.left || x >= rect.right || y < rect.top || y >= rect.bottom) {
      setIsDragging(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      if (disabled) return;

      const files = Array.from(e.dataTransfer.files);
      if (files.length > 0) {
        handleFileSelect(files[0]);
      }
    },
    [disabled, handleFileSelect],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      if (files.length > 0) {
        handleFileSelect(files[0]);
      }
      // Reset input
      e.target.value = "";
    },
    [handleFileSelect],
  );

  return (
    <div className={cn("w-full", className)}>
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "relative rounded-xl border-2 border-dashed transition-all duration-200",
          "flex flex-col items-center justify-center gap-3 p-8",
          !disabled && [
            "cursor-pointer hover:border-primary/60 hover:bg-primary/5",
          ],
          isDragging &&
            !disabled && ["border-primary bg-primary/10 scale-[1.02]"],
          disabled && ["cursor-not-allowed opacity-50 border-border/30"],
          !isDragging && !disabled && ["border-border/40"],
          error && ["border-red-500/60 bg-red-500/5"],
        )}
      >
        <input
          type="file"
          onChange={handleInputChange}
          accept={acceptedTypes.join(",")}
          disabled={disabled}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
          aria-label="Seleccionar archivo"
        />

        {/* Icon */}
        <div
          className={cn(
            "rounded-full p-4 transition-colors",
            isDragging
              ? "bg-primary/20 text-primary"
              : "bg-surface-2 text-text-muted",
          )}
        >
          <svg
            className="h-8 w-8"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>

        {/* Text */}
        <div className="text-center">
          <p className="text-sm font-medium text-text">
            {isDragging ? (
              "Suelta el archivo aquí"
            ) : (
              <>
                Arrastra un archivo o{" "}
                <span className="text-primary">haz clic para seleccionar</span>
              </>
            )}
          </p>
          <p className="mt-1 text-xs text-text-muted">
            PDF, PNG, JPG (máx. {maxSizeMB}MB)
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 text-sm text-red-400">
            <svg
              className="h-4 w-4 flex-shrink-0"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
            </svg>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
