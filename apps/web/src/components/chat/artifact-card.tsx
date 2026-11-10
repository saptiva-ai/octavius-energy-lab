"use client";

import type { JSX } from "react";

import { useCanvasStore } from "@/lib/stores/canvas-store";
import type { ArtifactType } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ArtifactCardProps {
  id: string;
  title: string;
  type?: ArtifactType | string | null;
}

const iconMap: Record<string, JSX.Element> = {
  markdown: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
    >
      <path d="M4 4h16v16H4z" />
      <path d="M7 9v6" />
      <path d="M11 9v6" />
      <path d="M7 12h4" />
      <path d="M14 15l3-3-3-3" />
    </svg>
  ),
  code: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
    >
      <path d="m7 8-4 4 4 4" />
      <path d="m17 8 4 4-4 4" />
      <path d="m14 4-4 16" />
    </svg>
  ),
  graph: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
    >
      <circle cx="6" cy="6" r="2.5" />
      <circle cx="18" cy="8" r="2.5" />
      <circle cx="12" cy="18" r="2.5" />
      <path d="M7.5 7.5 10.5 15" />
      <path d="M17 9.8 13.5 15" />
    </svg>
  ),
  chart: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
    >
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M7 16v-4" />
      <path d="M12 16V8" />
      <path d="M17 16v-6" />
    </svg>
  ),
};

export function ArtifactCard({ id, title, type }: ArtifactCardProps) {
  const setArtifact = useCanvasStore((state) => state.setArtifact);

  const icon = iconMap[(type as string) || ""] || iconMap.markdown;

  // Render as a clickable card that opens the artifact in the canvas
  return (
    <button
      type="button"
      onClick={() => setArtifact(id)}
      className={cn(
        "flex w-full items-center justify-between rounded-md border border-white/10 bg-white/5 px-3 py-2 text-left transition-colors",
        "hover:border-white/25 hover:bg-white/10",
      )}
    >
      <div className="flex items-center gap-3 overflow-hidden">
        <span className="grid h-8 w-8 place-items-center rounded-md bg-white/10 text-white/80">
          {icon}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-white">{title}</p>
          <p className="text-xs uppercase tracking-wide text-saptiva-light/70">
            {type || "artifact"}
          </p>
        </div>
      </div>
      <span className="text-xs text-saptiva-light/70">Ver</span>
    </button>
  );
}
