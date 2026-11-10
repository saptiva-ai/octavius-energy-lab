"use client";

import * as React from "react";
import { cn } from "../../lib/utils";

export interface FilesToggleProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
  fileCount?: number;
  className?: string;
}

/**
 * FilesToggle - Toggle switch for "Use files in this question"
 *
 * Usage:
 * ```tsx
 * <FilesToggle
 *   enabled={useFilesInQuestion}
 *   onChange={setUseFilesInQuestion}
 *   disabled={attachments.length === 0}
 *   fileCount={attachments.length}
 * />
 * ```
 */
export function FilesToggle({
  enabled,
  onChange,
  disabled = false,
  fileCount = 0,
  className,
}: FilesToggleProps) {
  const handleChange = () => {
    if (!disabled) {
      onChange(!enabled);
    }
  };

  return (
    <div className={cn("flex items-center gap-3", className)}>
      {/* Toggle Switch */}
      <button
        role="switch"
        aria-checked={enabled}
        disabled={disabled}
        onClick={handleChange}
        className={cn(
          "relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary/60 focus:ring-offset-2",
          enabled ? "bg-primary" : "bg-gray-200",
          disabled && "opacity-50 cursor-not-allowed",
        )}
      >
        <span
          className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white transition-transform",
            enabled ? "translate-x-6" : "translate-x-1",
          )}
        />
      </button>

      {/* Label */}
      <label
        onClick={!disabled ? handleChange : undefined}
        className={cn(
          "text-sm font-medium text-gray-700 select-none",
          !disabled && "cursor-pointer",
          disabled && "opacity-50 cursor-not-allowed",
        )}
      >
        Usar archivos en esta pregunta
        {fileCount > 0 && (
          <span className="ml-2 text-xs text-gray-500">
            ({fileCount} archivo{fileCount !== 1 ? "s" : ""})
          </span>
        )}
      </label>
    </div>
  );
}
