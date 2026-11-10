"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import toast from "react-hot-toast";
import { logDebug, logError } from "@/lib/logger";

interface FileReference {
  file_id: string;
  filename: string;
  upload_date: string;
  size_bytes: number;
  status: string;
}

interface HistoryFilePickerProps {
  conversationId?: string;
  isOpen: boolean;
  onClose: () => void;
  onSelect: (fileIds: string[]) => void;
  multiSelect?: boolean;
}

/**
 * HistoryFilePicker - Modal to select files from chat history
 *
 * Features:
 * - Fetches files from conversation history via API
 * - Multi-select support with checkboxes
 * - Shows file metadata (name, size, date)
 * - Empty state when no files found
 * - Loading and error states
 *
 * Usage:
 * ```tsx
 * <HistoryFilePicker
 *   conversationId={chatId}
 *   isOpen={showPicker}
 *   onClose={() => setShowPicker(false)}
 *   onSelect={(fileIds) => {
 *     setSelectedFileIds(fileIds);
 *     runAudit();
 *   }}
 *   multiSelect={true}
 * />
 * ```
 */
export function HistoryFilePicker({
  conversationId,
  isOpen,
  onClose,
  onSelect,
  multiSelect = true,
}: HistoryFilePickerProps) {
  const [files, setFiles] = React.useState<FileReference[]>([]);
  const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Fetch files when modal opens
  React.useEffect(() => {
    if (!isOpen || !conversationId) return;

    const fetchFiles = async () => {
      setLoading(true);
      setError(null);

      try {
        logDebug("[HistoryFilePicker] Fetching files", { conversationId });

        // TODO: Implement API endpoint GET /api/chats/:chatId/files
        // For now, use empty array (feature not yet implemented)
        const fetchedFiles: FileReference[] = [];
        setFiles(fetchedFiles);

        logDebug("[HistoryFilePicker] Files fetched", {
          count: fetchedFiles.length,
        });
      } catch (err: any) {
        const errorMsg =
          err?.response?.data?.detail ||
          err?.message ||
          "Error al cargar archivos";
        logError("[HistoryFilePicker] Failed to fetch files", err);
        setError(errorMsg);
        toast.error(errorMsg);
      } finally {
        setLoading(false);
      }
    };

    fetchFiles();
  }, [isOpen, conversationId]);

  // Reset selection when modal closes
  React.useEffect(() => {
    if (!isOpen) {
      setSelectedIds([]);
      setFiles([]);
      setError(null);
    }
  }, [isOpen]);

  const toggleSelection = (fileId: string) => {
    if (!multiSelect) {
      // Single select: replace selection
      setSelectedIds([fileId]);
      return;
    }

    // Multi select: toggle
    setSelectedIds((prev) =>
      prev.includes(fileId)
        ? prev.filter((id) => id !== fileId)
        : [...prev, fileId],
    );
  };

  const handleConfirm = () => {
    if (selectedIds.length === 0) {
      toast.error("Selecciona al menos un archivo");
      return;
    }

    logDebug("[HistoryFilePicker] Files selected", {
      count: selectedIds.length,
      fileIds: selectedIds,
    });

    onSelect(selectedIds);
    onClose();
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (isoDate: string) => {
    const date = new Date(isoDate);
    return date.toLocaleDateString("es-ES", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
          />

          {/* Modal */}
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="w-full max-w-2xl max-h-[80vh] flex flex-col bg-neutral-900 rounded-2xl shadow-2xl border border-neutral-800"
            >
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-800">
                <div>
                  <h2 className="text-lg font-semibold text-neutral-100">
                    Seleccionar archivos del historial
                  </h2>
                  <p className="text-sm text-neutral-400 mt-0.5">
                    {multiSelect
                      ? "Selecciona uno o más archivos para auditar"
                      : "Selecciona un archivo para auditar"}
                  </p>
                </div>
                <button
                  onClick={onClose}
                  className="p-2 rounded-lg hover:bg-neutral-800 text-neutral-400 hover:text-neutral-100 transition-colors"
                  aria-label="Cerrar"
                >
                  <svg
                    className="h-5 w-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-y-auto p-6">
                {loading && (
                  <div className="flex flex-col items-center justify-center py-12 space-y-3">
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{
                        duration: 1,
                        repeat: Infinity,
                        ease: "linear",
                      }}
                      className="h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full"
                    />
                    <p className="text-sm text-neutral-400">
                      Cargando archivos...
                    </p>
                  </div>
                )}

                {error && !loading && (
                  <div className="flex flex-col items-center justify-center py-12 space-y-3">
                    <div className="h-12 w-12 rounded-full bg-red-500/20 flex items-center justify-center">
                      <svg
                        className="h-6 w-6 text-red-400"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                        />
                      </svg>
                    </div>
                    <p className="text-sm text-neutral-400">{error}</p>
                  </div>
                )}

                {!loading && !error && files.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-12 space-y-3">
                    <div className="h-16 w-16 rounded-full bg-neutral-800 flex items-center justify-center">
                      <svg
                        className="h-8 w-8 text-neutral-500"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={1.5}
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        />
                      </svg>
                    </div>
                    <p className="text-sm text-neutral-400">
                      No hay archivos en este chat
                    </p>
                    <p className="text-xs text-neutral-500">
                      Adjunta archivos para poder auditarlos
                    </p>
                  </div>
                )}

                {!loading && !error && files.length > 0 && (
                  <div className="space-y-2">
                    {files.map((file) => {
                      const isSelected = selectedIds.includes(file.file_id);

                      return (
                        <motion.button
                          key={file.file_id}
                          type="button"
                          onClick={() => toggleSelection(file.file_id)}
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          className={cn(
                            "w-full flex items-center gap-4 p-4 rounded-xl border transition-all duration-200 text-left",
                            isSelected
                              ? "border-blue-500 bg-blue-500/10"
                              : "border-neutral-800 hover:border-neutral-700 hover:bg-neutral-800/50",
                          )}
                        >
                          {/* Checkbox */}
                          <div
                            className={cn(
                              "h-5 w-5 rounded border-2 flex items-center justify-center transition-colors shrink-0",
                              isSelected
                                ? "border-blue-500 bg-blue-500"
                                : "border-neutral-600",
                            )}
                          >
                            {isSelected && (
                              <svg
                                className="h-3 w-3 text-white"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                                strokeWidth={3}
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M5 13l4 4L19 7"
                                />
                              </svg>
                            )}
                          </div>

                          {/* File Icon */}
                          <div className="h-10 w-10 rounded-lg bg-blue-500/20 flex items-center justify-center shrink-0">
                            <svg
                              className="h-5 w-5 text-blue-400"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={1.5}
                                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                              />
                            </svg>
                          </div>

                          {/* File Info */}
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-neutral-100 truncate">
                              {file.filename}
                            </p>
                            <p className="text-xs text-neutral-400 mt-0.5">
                              {formatFileSize(file.size_bytes)} ·{" "}
                              {formatDate(file.upload_date)}
                            </p>
                          </div>

                          {/* Status Badge */}
                          {file.status === "READY" && (
                            <div className="px-2 py-1 rounded-md bg-green-500/20 text-green-400 text-xs font-medium shrink-0">
                              Listo
                            </div>
                          )}
                        </motion.button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between px-6 py-4 border-t border-neutral-800">
                <p className="text-sm text-neutral-400">
                  {selectedIds.length > 0
                    ? `${selectedIds.length} archivo(s) seleccionado(s)`
                    : "Ningún archivo seleccionado"}
                </p>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 rounded-lg text-sm font-medium text-neutral-300 hover:bg-neutral-800 transition-colors"
                  >
                    Cancelar
                  </button>
                  <button
                    type="button"
                    onClick={handleConfirm}
                    disabled={selectedIds.length === 0}
                    className={cn(
                      "px-4 py-2 rounded-lg text-sm font-medium transition-all",
                      selectedIds.length > 0
                        ? "bg-blue-500 text-white hover:bg-blue-600 active:scale-95"
                        : "bg-neutral-800 text-neutral-500 cursor-not-allowed",
                    )}
                  >
                    Confirmar
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );
}
