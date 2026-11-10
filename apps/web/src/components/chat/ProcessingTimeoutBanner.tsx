/**
 * ProcessingTimeoutBanner Component
 *
 * Shows a banner when file processing takes longer than expected (90s).
 * Informs the user that we are still trying to connect.
 */

"use client";

import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

// Simple X icon component (inline SVG)
const XIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

interface ProcessingTimeoutBannerProps {
  filename: string;
  onDismiss: () => void;
  className?: string;
}

export function ProcessingTimeoutBanner({
  filename,
  onDismiss,
  className,
}: ProcessingTimeoutBannerProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={cn(
        "mx-4 my-2 rounded-lg border border-yellow-500/20 bg-yellow-500/10 p-4",
        className,
      )}
    >
      <div className="flex items-center gap-3">
        {/* Animated Spinner */}
        <div className="relative h-5 w-5">
          <motion.div
            className="absolute inset-0 rounded-full border-2 border-yellow-500/30 border-t-yellow-500"
            animate={{ rotate: 360 }}
            transition={{
              duration: 1,
              repeat: Infinity,
              ease: "linear",
            }}
          />
        </div>

        {/* Progress Text */}
        <div className="flex-1">
          <p className="text-sm font-medium text-yellow-100">
            El procesamiento está tardando más de lo esperado.
          </p>
          <p className="text-xs text-yellow-200/70 mt-0.5">{filename}</p>
        </div>

        <button
          onClick={onDismiss}
          className="p-1 rounded-full hover:bg-yellow-500/20"
        >
          <XIcon className="h-4 w-4 text-yellow-200/70" />
        </button>
      </div>

      <p className="mt-2 text-xs text-yellow-200/50">
        Continuamos reintentando la conexión con el servidor.
      </p>
    </motion.div>
  );
}
