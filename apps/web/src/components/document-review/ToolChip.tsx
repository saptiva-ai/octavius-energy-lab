"use client";

/**
 * ToolChip - Accessible chip component for tools bar
 *
 * States: inactive | active | loading | disabled
 * Features: Focus, ARIA, keyboard navigation
 */

import { useState } from "react";
import { cn } from "../../lib/utils";

export type ChipState = "inactive" | "active" | "loading" | "disabled";

export interface ToolChipProps {
  label: string;
  icon?: React.ReactNode;
  state?: ChipState;
  onClick?: () => void;
  onToggle?: (active: boolean) => void;
  className?: string;
}

export function ToolChip({
  label,
  icon,
  state = "inactive",
  onClick,
  onToggle,
  className,
}: ToolChipProps) {
  const [isActive, setIsActive] = useState(state === "active");

  const handleClick = () => {
    if (state === "disabled" || state === "loading") return;

    const newActive = !isActive;
    setIsActive(newActive);

    if (onToggle) {
      onToggle(newActive);
    }

    if (onClick) {
      onClick();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleClick();
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      disabled={state === "disabled"}
      aria-pressed={isActive}
      aria-label={label}
      aria-busy={state === "loading"}
      className={cn(
        "inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium",
        "transition-all duration-200 ease-out",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        // Inactive state
        state === "inactive" &&
          !isActive && [
            "bg-surface-2 text-text-muted border border-border/40",
            "hover:bg-surface hover:text-text hover:border-border",
          ],
        // Active state
        (state === "active" || isActive) && [
          "bg-primary/15 text-primary border border-primary/40",
          "hover:bg-primary/20",
        ],
        // Loading state
        state === "loading" && [
          "bg-surface-2 text-text-muted border border-border/40",
          "cursor-wait opacity-75",
        ],
        // Disabled state
        state === "disabled" && [
          "bg-surface-2/50 text-text-muted/50 border border-border/20",
          "cursor-not-allowed opacity-50",
        ],
        className,
      )}
    >
      {state === "loading" ? (
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
      ) : icon ? (
        <span className="flex-shrink-0">{icon}</span>
      ) : null}
      <span>{label}</span>
    </button>
  );
}
