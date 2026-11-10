"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useAuditStore } from "@/lib/stores/audit-store";
import toast from "react-hot-toast";

interface AuditToggleProps {
  hasFiles: boolean;
  className?: string;
  disabled?: boolean;
}

/**
 * AuditToggle - Switch component for audit system
 *
 * Features:
 * - ON/OFF toggle for automatic audit
 * - Disabled when no files selected
 * - Shows loading state during audit
 * - Displays audit status hints
 *
 * UX Behavior:
 * - Switch disabled if hasFiles=false
 * - Auto-triggers audit when switched ON with files
 * - Shows "Auditando..." during audit
 * - Returns to ON after success/error
 */
export function AuditToggle({
  hasFiles,
  className,
  disabled = false,
}: AuditToggleProps) {
  const { auditEnabled, status, error, setAuditEnabled, cancelAudit } =
    useAuditStore();

  const isAuditing = status === "auditing";
  const isDisabled = disabled || (!hasFiles && status === "idle");

  const handleToggle = React.useCallback(() => {
    if (isDisabled) {
      // Show hint if trying to enable without files
      if (!hasFiles) {
        toast.error("Adjunta al menos un archivo para auditar", {
          icon: "📎",
          duration: 2000,
        });
      }
      return;
    }

    if (isAuditing) {
      // If auditing, clicking cancels
      cancelAudit();
      toast.success("Auditoría cancelada", {
        icon: "⏹️",
        duration: 2000,
      });
      return;
    }

    // Toggle the switch
    const newState = !auditEnabled;
    setAuditEnabled(newState);

    if (newState && hasFiles) {
      toast.success("Iniciando auditoría...", {
        icon: "🔍",
        duration: 2000,
      });
    }
  }, [
    isDisabled,
    hasFiles,
    isAuditing,
    auditEnabled,
    setAuditEnabled,
    cancelAudit,
  ]);

  // Show error toast when audit fails
  React.useEffect(() => {
    if (status === "error" && error) {
      toast.error(error.message, {
        icon: "❌",
        duration: 4000,
      });
    }
  }, [status, error]);

  // Show success toast
  React.useEffect(() => {
    if (status === "success") {
      toast.success("Auditoría completada", {
        icon: "✅",
        duration: 3000,
      });
    }
  }, [status]);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      {/* Status hint (optional, shows during auditing) */}
      {isAuditing && (
        <motion.div
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -8 }}
          className="flex items-center gap-1.5 text-xs text-blue-400 font-medium"
        >
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
            className="h-3 w-3"
          >
            🔍
          </motion.div>
          <span>Auditando...</span>
        </motion.div>
      )}

      {/* Toggle Switch */}
      <button
        type="button"
        role="switch"
        aria-checked={auditEnabled}
        aria-label={
          isAuditing
            ? "Cancelar auditoría"
            : auditEnabled
              ? "Desactivar auditoría automática"
              : "Activar auditoría automática"
        }
        aria-disabled={isDisabled}
        disabled={isDisabled}
        onClick={handleToggle}
        className={cn(
          "relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-neutral-900",
          auditEnabled
            ? isAuditing
              ? "bg-blue-500"
              : "bg-green-500"
            : "bg-neutral-700",
          isDisabled && "opacity-40 cursor-not-allowed",
          !isDisabled && "cursor-pointer",
        )}
      >
        {/* Switch Knob */}
        <motion.span
          layout
          className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white shadow-lg transition-transform",
          )}
          animate={{
            x: auditEnabled ? 22 : 4,
          }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
        >
          {/* Loading spinner inside knob when auditing */}
          {isAuditing && (
            <motion.svg
              className="h-3 w-3 text-blue-500 absolute inset-0.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={3}
              animate={{ rotate: 360 }}
              transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }}
            >
              <circle
                cx={12}
                cy={12}
                r={10}
                strokeDasharray="60 20"
                strokeLinecap="round"
              />
            </motion.svg>
          )}
        </motion.span>
      </button>

      {/* Label */}
      <label
        htmlFor="audit-toggle"
        className={cn(
          "text-xs font-medium select-none transition-colors",
          auditEnabled ? "text-green-400" : "text-neutral-400",
          isDisabled && "opacity-40",
        )}
      >
        {isAuditing ? "Auditando" : auditEnabled ? "Auditar ON" : "Auditar"}
      </label>
    </div>
  );
}
