/**
 * audit-store.ts - State management for document audit system
 *
 * Manages audit workflow with a finite state machine:
 * - idle: No files selected
 * - filesSelected: Files ready to audit
 * - auditing: Audit in progress
 * - success: Audit completed
 * - error: Audit failed
 * - historySelect: Picking files from history
 *
 * Features:
 * - Auto-trigger audit when toggle ON + files selected
 * - Cancellation support via AbortController
 * - Persistent selectedFileIds (survives send)
 * - Error recovery with retry
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ValidationReportResponse } from "@/types/validation";
import { apiClient } from "@/lib/api-client";
import { logDebug, logError } from "@/lib/logger";

// Audit state machine
export type AuditStatus =
  | "idle"
  | "filesSelected"
  | "auditing"
  | "success"
  | "error"
  | "historySelect";

export interface AuditError {
  message: string;
  code?: string;
  retryable: boolean;
}

interface AuditStoreState {
  // State machine
  status: AuditStatus;

  // Toggle state
  auditEnabled: boolean;

  // Selected files for audit
  selectedFileIds: string[];

  // Audit results
  report: ValidationReportResponse | null;
  error: AuditError | null;

  // Abort controller for cancellation
  abortController: AbortController | null;

  // Actions
  setAuditEnabled: (enabled: boolean) => void;
  setSelectedFileIds: (fileIds: string[]) => void;
  addSelectedFileId: (fileId: string) => void;
  removeSelectedFileId: (fileId: string) => void;
  clearSelectedFiles: () => void;

  // Audit lifecycle
  runAudit: (conversationId?: string, clientName?: string) => Promise<void>;
  cancelAudit: () => void;
  retryAudit: (conversationId?: string, clientName?: string) => Promise<void>;
  reset: () => void;

  // History picker
  openHistoryPicker: () => void;
  closeHistoryPicker: () => void;
}

const initialState = {
  status: "idle" as AuditStatus,
  auditEnabled: false,
  selectedFileIds: [],
  report: null,
  error: null,
  abortController: null,
};

export const useAuditStore = create<AuditStoreState>()(
  persist(
    (set, get) => ({
      ...initialState,

      setAuditEnabled: (enabled) => {
        const state = get();
        set({ auditEnabled: enabled });

        // Auto-trigger audit if enabled and files selected
        if (
          enabled &&
          state.selectedFileIds.length > 0 &&
          state.status !== "auditing"
        ) {
          logDebug("[audit-store] Auto-triggering audit", {
            fileCount: state.selectedFileIds.length,
          });
          // Use setTimeout to avoid sync state update during render
          setTimeout(() => get().runAudit(), 0);
        }
      },

      setSelectedFileIds: (fileIds) => {
        const uniqueIds = Array.from(new Set(fileIds));
        const prevState = get().status;

        set({
          selectedFileIds: uniqueIds,
          status: uniqueIds.length > 0 ? "filesSelected" : "idle",
          error: null, // Clear error when files change
        });

        // Auto-trigger audit if toggle is ON and we just got files
        if (
          get().auditEnabled &&
          uniqueIds.length > 0 &&
          prevState === "idle"
        ) {
          logDebug("[audit-store] Auto-triggering audit on file selection", {
            fileCount: uniqueIds.length,
          });
          setTimeout(() => get().runAudit(), 0);
        }
      },

      addSelectedFileId: (fileId) => {
        const state = get();
        if (state.selectedFileIds.includes(fileId)) return;

        const newFileIds = [...state.selectedFileIds, fileId];
        get().setSelectedFileIds(newFileIds);
      },

      removeSelectedFileId: (fileId) => {
        const state = get();
        const newFileIds = state.selectedFileIds.filter((id) => id !== fileId);
        get().setSelectedFileIds(newFileIds);
      },

      clearSelectedFiles: () => {
        set({
          selectedFileIds: [],
          status: "idle",
          error: null,
        });
      },

      runAudit: async (conversationId?: string, clientName?: string) => {
        const state = get();

        if (state.selectedFileIds.length === 0) {
          logError("[audit-store] Cannot run audit: no files selected");
          set({
            status: "error",
            error: {
              message: "No hay archivos seleccionados para auditar",
              retryable: false,
            },
          });
          return;
        }

        if (state.status === "auditing") {
          logDebug("[audit-store] Audit already in progress, ignoring");
          return;
        }

        // Create abort controller for cancellation
        const controller = new AbortController();

        set({
          status: "auditing",
          error: null,
          report: null,
          abortController: controller,
        });

        logDebug("[audit-store] Starting audit", {
          fileIds: state.selectedFileIds,
          conversationId,
          clientName,
        });

        try {
          // For now, audit first file (future: batch audit)
          const firstFileId = state.selectedFileIds[0];

          // Call audit API via apiClient
          const report = await apiClient.auditDocument(firstFileId, {
            clientName: clientName || "Demo",
            // Add signal for cancellation
            // @ts-ignore - signal not in types yet
            signal: controller.signal,
          });

          logDebug("[audit-store] Audit completed successfully", {
            jobId: report.job_id,
            status: report.status,
            findings: report.summary.total_findings,
          });

          set({
            status: "success",
            report,
            abortController: null,
          });
        } catch (error: any) {
          // Check if cancelled
          if (
            error.name === "AbortError" ||
            error.message === "Audit cancelled"
          ) {
            logDebug("[audit-store] Audit cancelled by user");
            set({
              status: "filesSelected",
              error: null,
              abortController: null,
            });
            return;
          }

          const errorMessage =
            error?.response?.data?.detail ||
            error?.message ||
            "Error desconocido en la auditoría";

          logError("[audit-store] Audit failed", { error });

          set({
            status: "error",
            error: {
              message: errorMessage,
              code: error?.response?.status?.toString(),
              retryable: true,
            },
            abortController: null,
          });
        }
      },

      cancelAudit: () => {
        const state = get();

        if (state.status !== "auditing") return;

        logDebug("[audit-store] Cancelling audit");

        // Trigger abort
        state.abortController?.abort();

        set({
          status: "filesSelected",
          error: null,
          abortController: null,
        });
      },

      retryAudit: async (conversationId?: string, clientName?: string) => {
        logDebug("[audit-store] Retrying audit");
        await get().runAudit(conversationId, clientName);
      },

      reset: () => {
        // Cancel ongoing audit if any
        get().abortController?.abort();

        set({
          ...initialState,
          // Keep selectedFileIds and auditEnabled for persistence
          selectedFileIds: get().selectedFileIds,
          auditEnabled: get().auditEnabled,
        });
      },

      openHistoryPicker: () => {
        set({ status: "historySelect" });
      },

      closeHistoryPicker: () => {
        const state = get();
        set({
          status: state.selectedFileIds.length > 0 ? "filesSelected" : "idle",
        });
      },
    }),
    {
      name: "audit-store",
      // Persist only toggle state and selected files
      partialize: (state) => ({
        auditEnabled: state.auditEnabled,
        selectedFileIds: state.selectedFileIds,
      }),
    },
  ),
);
