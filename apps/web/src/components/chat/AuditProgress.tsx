/**
 * AuditProgress Component
 *
 * Shows a progress indicator when document audit is in progress.
 * Displays in-chat banner with animated spinner and status updates.
 */

"use client";

import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface AuditProgressProps {
  filename: string;
  className?: string;
}

export function AuditProgress({ filename, className }: AuditProgressProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={cn(
        "mx-4 my-2 rounded-lg border border-blue-500/20 bg-blue-500/10 p-4",
        className,
      )}
    >
      <div className="flex items-center gap-3">
        {/* Animated Spinner */}
        <div className="relative h-5 w-5">
          <motion.div
            className="absolute inset-0 rounded-full border-2 border-blue-500/30 border-t-blue-500"
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
          <p className="text-sm font-medium text-blue-100">
            Auditando documento...
          </p>
          <p className="text-xs text-blue-200/70 mt-0.5">{filename}</p>
        </div>

        {/* Progress Stages (optional - can show which stage is running) */}
        <div className="flex gap-1">
          <StageIndicator label="Formato" />
          <StageIndicator label="Logo" />
          <StageIndicator label="Cumplimiento" />
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-blue-900/30">
        <motion.div
          className="h-full bg-gradient-to-r from-blue-500 to-blue-400"
          initial={{ width: "0%" }}
          animate={{ width: ["0%", "30%", "60%", "90%"] }}
          transition={{
            duration: 30,
            times: [0, 0.3, 0.6, 1],
            ease: "easeInOut",
          }}
        />
      </div>

      <p className="mt-2 text-xs text-blue-200/50">
        Esto puede tardar hasta 60 segundos para documentos grandes
      </p>
    </motion.div>
  );
}

function StageIndicator({ label }: { label: string }) {
  return (
    <div
      className="flex items-center gap-1 rounded-full bg-blue-500/20 px-2 py-1 text-xs text-blue-200"
      title={label}
    >
      <motion.div
        className="h-1.5 w-1.5 rounded-full bg-blue-400"
        animate={{ scale: [1, 1.3, 1] }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />
      <span className="hidden sm:inline">{label}</span>
    </div>
  );
}
