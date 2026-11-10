"use client";

import * as React from "react";
import toast from "react-hot-toast";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../../../lib/utils";
import type { ToolId } from "@/types/tools";
import { TOOL_REGISTRY } from "@/types/tools";
import { isLockedTool, toolsConChipEnComposer } from "@/lib/tool-mapping";
import { HELP_ONBOARDING_PROMPT_EVENT } from "@/lib/help-onboarding-events";
import ToolMenu from "../ToolMenu/ToolMenu";
import { ChatComposerAttachment } from "./types";
import { useChat } from "../../../lib/store";
import { logDebug, logError } from "../../../lib/logger";
import { apiClient } from "../../../lib/api-client";
import type { ChatMessage } from "../../../lib/types";
// Files V1 imports - MINIMALISMO FUNCIONAL: Solo lista, agregar desde tools
import { FileAttachmentList } from "../../files";
import type { FileAttachment } from "../../../types/files";
import type { FeatureFlagsResponse } from "@/lib/types";
import { useFiles, type LastReadyFile } from "../../../hooks/useFiles";
import { useAuditFlow } from "../../../hooks/useAuditFlow";
import { PreviewAttachment } from "../PreviewAttachment";

interface CompactChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void | Promise<void>;
  onSendMessageDirect?: (
    message: string,
    attachments?: ChatComposerAttachment[],
  ) => void;
  onCancel?: () => void;
  disabled?: boolean;
  loading?: boolean;
  layout?: "center" | "bottom";
  onActivate?: () => void;
  placeholder?: string;
  maxLength?: number;
  showCancel?: boolean;
  className?: string;
  selectedTools?: ToolId[];
  onRemoveTool?: (id: ToolId) => void;
  onAddTool?: (id: ToolId) => void;
  attachments?: ChatComposerAttachment[];
  onAttachmentsChange?: (attachments: ChatComposerAttachment[]) => void;
  // Files V1 props (simplified - no toggle needed)
  filesV1Attachments?: FileAttachment[];
  onAddFilesV1Attachment?: (attachment: FileAttachment) => void;
  onRemoveFilesV1Attachment?: (fileId: string) => void;
  conversationId?: string;
  featureFlags?: FeatureFlagsResponse | null;
  // Copiloto Audit: Audit props
  lastReadyFile?: LastReadyFile | null;
  onStartAudit?: (fileId: string, filename: string) => void;
  onAuditError?: (fileId: string, reason?: string) => void;
}

// Icons
function PlusIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 6v12" />
      <path d="M18 12H6" />
    </svg>
  );
}

function SendIconArrowUp({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 19V5" />
      <path d="m5 12 7-7 7 7" />
    </svg>
  );
}

function StopIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <rect x={7} y={7} width={10} height={10} rx={2} />
    </svg>
  );
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 18L18 6" />
      <path d="M6 6l12 12" />
    </svg>
  );
}

// Min height: ~44px (min-h-11), Max height: ~192px (max-h-48)
const MIN_HEIGHT = 44;
const MAX_HEIGHT = 192;

// Feature flag: Show tools button (set to true when tools are functional)
const SHOW_TOOLS_BUTTON = true; // V1: Enabled for document upload

export function CompactChatComposer({
  value,
  onChange,
  onSubmit,
  onSendMessageDirect,
  onCancel,
  disabled = false,
  loading = false,
  layout = "bottom",
  onActivate,
  placeholder = "Pregúntame algo…",
  maxLength = 10000,
  showCancel = false,
  className,
  selectedTools = [],
  onRemoveTool,
  onAddTool,
  attachments = [],
  onAttachmentsChange,
  // Files V1 props (simplified)
  filesV1Attachments = [],
  onAddFilesV1Attachment,
  onRemoveFilesV1Attachment,
  conversationId,
  featureFlags,
}: CompactChatComposerProps) {
  const [showToolsMenu, setShowToolsMenu] = React.useState(false);
  const [textareaHeight, setTextareaHeight] = React.useState(MIN_HEIGHT);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [uploadingFiles, setUploadingFiles] = React.useState<
    Map<string, number>
  >(new Map()); // filename -> progress%
  const [pendingAuditCommand, setPendingAuditCommand] = React.useState<
    string | null
  >(null);

  const taRef = React.useRef<HTMLTextAreaElement>(null);
  const composerRef = React.useRef<HTMLDivElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const liveRegionRef = React.useRef<HTMLDivElement>(null); // Parche B: ARIA live region

  // MVP-LOCK: Debounce to prevent double sends on slow networks
  const lastSubmitRef = React.useRef(0);
  const DEBOUNCE_MS = 600;

  // Get current chat ID and finalize function from store
  const { currentChatId, finalizeCreation } = useChat();

  // MVP-BUG-FIX: Use Files V1 hook for proper file storage
  const { uploadFile: uploadFileV1 } = useFiles(
    conversationId || currentChatId || undefined,
  );

  // Audit flow integration - Use direct send bypassing React state
  const directSubmitForAudit = React.useCallback(async () => {
    // Direct submit for audit - bypasses React state by reading from textarea DOM
    // This is safe because the audit command always includes text
    logDebug("[CompactChatComposer] Direct audit submit triggered", {
      currentValue: value,
      textareaValue: taRef.current?.value,
    });

    // Force submission by reading current textarea value
    // This works around React state update timing issues
    if (taRef.current && onSendMessageDirect) {
      const currentTextareaValue = taRef.current.value;
      logDebug("[CompactChatComposer] Textarea value:", {
        value: currentTextareaValue,
      });

      // If textarea has the audit command, send directly
      if (currentTextareaValue.trim().startsWith("Auditar archivo:")) {
        logDebug(
          "[CompactChatComposer] Audit command detected, calling onSendMessageDirect",
        );
        onSendMessageDirect(
          currentTextareaValue.trim(),
          attachments.length ? attachments : undefined,
        );

        // Clear input and attachments after successful send
        onChange("");
        if (onAttachmentsChange) {
          onAttachmentsChange([]);
        }
      } else {
        logError(
          "[CompactChatComposer] Textarea doesn't have audit command yet",
          {
            value: currentTextareaValue,
          },
        );
      }
    } else {
      logError(
        "[CompactChatComposer] Missing textarea ref or onSendMessageDirect callback",
        {},
      );
    }
  }, [onSendMessageDirect, value, attachments, onChange, onAttachmentsChange]);

  const { sendAuditForFile } = useAuditFlow({
    setValue: onChange,
    onSubmit: directSubmitForAudit,
    // clearFiles is optional - not available in CompactChatComposer context
    conversationId: conversationId || currentChatId || undefined,
  });

  // Debug: Log sendAuditForFile function availability
  React.useEffect(() => {
    logDebug("[CompactChatComposer] sendAuditForFile availability", {
      sendAuditForFile: typeof sendAuditForFile,
      isFunction: typeof sendAuditForFile === "function",
    });
  }, [sendAuditForFile]);

  // Finalize creation when user starts typing (guarantee transition creating → draft)
  const handleFirstInput = React.useCallback(() => {
    logDebug("[chat.composer] handleFirstInput", { currentChatId });
    if (currentChatId && currentChatId.startsWith("temp-")) {
      logDebug("[chat.composer] finalizeCreation trigger", { currentChatId });
      finalizeCreation(currentChatId);
    }
  }, [currentChatId, finalizeCreation]);

  // Auto-resize textarea (grows downward only)
  const handleAutoResize = React.useCallback(() => {
    const ta = taRef.current;
    if (!ta) return;

    // Reset height to recalculate
    ta.style.height = "auto";
    const scrollHeight = ta.scrollHeight;

    // Calculate new height (clamped between MIN and MAX)
    const newHeight = Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, scrollHeight));
    setTextareaHeight(newHeight);
    ta.style.height = `${newHeight}px`;
  }, []);

  // Auto-resize on value change
  React.useEffect(() => {
    handleAutoResize();
  }, [value, handleAutoResize]);

  // Pregunta elegida en la ayuda: ChatInterface pone el texto y aquí se toma
  // el foco, con el cursor al final, para que Enter la envíe (QA,
  // P2.7: el foco se quedaba en el botón "?" y Enter reabría la ayuda).
  React.useEffect(() => {
    const enfocar = () => {
      window.setTimeout(() => {
        const ta = taRef.current;
        if (!ta) return;
        ta.focus();
        ta.setSelectionRange(ta.value.length, ta.value.length);
      }, 0);
    };
    window.addEventListener(HELP_ONBOARDING_PROMPT_EVENT, enfocar);
    return () => window.removeEventListener(HELP_ONBOARDING_PROMPT_EVENT, enfocar);
  }, []);

  // Finalize creation on mount if current chat is optimistic
  React.useEffect(() => {
    if (currentChatId && currentChatId.startsWith("temp-")) {
      finalizeCreation(currentChatId);
    }
  }, [currentChatId, finalizeCreation]);

  // Reset isSubmitting when currentChatId changes (switching conversations)
  React.useEffect(() => {
    setIsSubmitting(false);
  }, [currentChatId]);

  // Reset isSubmitting when value is cleared from parent (after successful submit)
  React.useEffect(() => {
    if (value === "") {
      setIsSubmitting(false);
    }
  }, [value]);

  // Reset isSubmitting when loading completes (backend finished processing)
  const prevLoadingRef = React.useRef(loading);
  React.useEffect(() => {
    if (prevLoadingRef.current === true && loading === false) {
      setIsSubmitting(false);
    }
    prevLoadingRef.current = loading;
  }, [loading]);

  // Handle pending audit command submission
  React.useEffect(() => {
    if (pendingAuditCommand && !isSubmitting && !loading) {
      // Update the input value first
      onChange(pendingAuditCommand);

      // Submit after a brief delay to ensure state updates
      const timer = setTimeout(() => {
        onSubmit();
        setPendingAuditCommand(null);
      }, 150);

      return () => clearTimeout(timer);
    }
  }, [pendingAuditCommand, isSubmitting, loading, onChange, onSubmit]);

  // FE-UX-1: Uploading guard (single definition)
  const isUploading = uploadingFiles.size > 0;

  // Deduplicate attachments to prevent React key warnings
  const deduplicatedAttachments = React.useMemo(() => {
    if (!filesV1Attachments || filesV1Attachments.length === 0) return [];

    // Use Map to deduplicate by file_id
    const uniqueMap = new Map<string, FileAttachment>();
    filesV1Attachments.forEach((attachment) => {
      if (!uniqueMap.has(attachment.file_id)) {
        uniqueMap.set(attachment.file_id, attachment);
      }
    });

    const deduplicated = Array.from(uniqueMap.values());

    // Log if duplicates were found
    if (deduplicated.length !== filesV1Attachments.length) {
      logDebug("[CompactChatComposer] Removed duplicate attachments", {
        original: filesV1Attachments.length,
        deduplicated: deduplicated.length,
        removedCount: filesV1Attachments.length - deduplicated.length,
      });
    }

    return deduplicated;
  }, [filesV1Attachments]);

  // Fix Pack: READY attachments (single definition)
  const hasReadyFiles = React.useMemo(
    () => deduplicatedAttachments.some((a) => a.status === "READY"),
    [deduplicatedAttachments],
  );

  // Block submit if any files are still PROCESSING
  const hasProcessingFiles = React.useMemo(
    () => deduplicatedAttachments.some((a) => a.status === "PROCESSING"),
    [deduplicatedAttachments],
  );

  // Rollback feature flag: Allow disabling files-only send in production
  const allowFilesOnlySend =
    process.env.NEXT_PUBLIC_ALLOW_FILES_ONLY_SEND !== "false";

  // MINIMALISMO FUNCIONAL: Archivos siempre se usan si están listos (sin toggle)
  const canSubmit = React.useMemo(
    () =>
      !disabled &&
      !loading &&
      !isSubmitting &&
      !isUploading &&
      !hasProcessingFiles && // Block if any files are still processing
      (value.trim().length > 0 || (allowFilesOnlySend && hasReadyFiles)), // Removed useFilesInQuestion check
    [
      disabled,
      loading,
      isSubmitting,
      isUploading,
      hasProcessingFiles,
      value,
      hasReadyFiles,
      allowFilesOnlySend,
    ],
  );

  // MVP-LOCK: Dynamic placeholder based on file state (simplified)
  const dynamicPlaceholder = React.useMemo(() => {
    if (hasProcessingFiles) {
      return "Esperando que termine el procesamiento de archivos...";
    }
    return "Pregúntame algo…";
  }, [hasProcessingFiles]);

  // Submit with animation (must be defined before handleKeyDown)
  const handleSendClick = React.useCallback(async () => {
    // MVP-LOCK: Debounce to prevent double sends on slow networks
    const now = Date.now();
    if (now - lastSubmitRef.current < DEBOUNCE_MS) {
      logDebug("[CompactChatComposer] Debounced duplicate submit", {
        timeSinceLastSubmit: now - lastSubmitRef.current,
      });
      return;
    }
    lastSubmitRef.current = now;

    // Fix Pack: Show feedback if trying to submit without text and without READY files
    if (!canSubmit) {
      const hasText = value.trim().length > 0;
      const hasReady = deduplicatedAttachments.some(
        (a) => a.status === "READY",
      );

      if (!hasText && !hasReady) {
        toast.error(
          "Escribe un mensaje o adjunta un documento listo para analizar.",
        );
      } else if (!hasText && hasReady && !allowFilesOnlySend) {
        // Rollback feature flag message
        toast.error(
          "Escribe un mensaje para enviar con los archivos adjuntos.",
        );
      }
      return;
    }

    setIsSubmitting(true);

    try {
      // Brief animation before submit (120ms)
      await new Promise((resolve) => setTimeout(resolve, 120));

      await onSubmit();

      // Clear attachments immediately after sending (don't wait for LLM response)
      if (deduplicatedAttachments.length > 0 && onRemoveFilesV1Attachment) {
        deduplicatedAttachments.forEach((attachment) => {
          onRemoveFilesV1Attachment(attachment.file_id);
        });
      }

      // Reset state after submit
      setTextareaHeight(MIN_HEIGHT);

      // Parche B: Re-focus textarea and announce to screen readers
      setTimeout(() => {
        taRef.current?.focus();
        // Announce message sent for accessibility
        if (liveRegionRef.current) {
          const hasFiles =
            filesV1Attachments?.some((a) => a.status === "READY") ?? false;
          const announcement = hasFiles
            ? "Mensaje enviado. Analizando documentos adjuntos."
            : "Mensaje enviado. Esperando respuesta.";
          liveRegionRef.current.textContent = announcement;
          // Clear announcement after screen reader has time to announce
          setTimeout(() => {
            if (liveRegionRef.current) {
              liveRegionRef.current.textContent = "";
            }
          }, 1000);
        }
      }, 80);
    } catch (error) {
      // If submit fails, ensure we reset isSubmitting
      setIsSubmitting(false);
    }
    // Note: Don't reset isSubmitting here on success - let useEffects handle it
    // This prevents race conditions with parent state updates
  }, [
    value,
    onSubmit,
    canSubmit,
    deduplicatedAttachments,
    onRemoveFilesV1Attachment,
    allowFilesOnlySend,
  ]);

  // Handle Enter key (submit) and Shift+Enter (newline)
  const handleKeyDown = React.useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (canSubmit) handleSendClick();
      }

      if (e.key === "Escape") {
        if (showToolsMenu) {
          setShowToolsMenu(false);
          return;
        }
        if (showCancel && onCancel) {
          onCancel();
        }
      }
    },
    [canSubmit, showToolsMenu, showCancel, onCancel, handleSendClick],
  );

  // Close menu on click outside
  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!composerRef.current?.contains(event.target as Node)) {
        setShowToolsMenu(false);
      }
    };

    if (showToolsMenu) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showToolsMenu]);

  const handleToolSelect = React.useCallback(
    (id: ToolId) => {
      // Special handling for 'add-files': Open file picker
      if (id === "add-files" || id === "files") {
        fileInputRef.current?.click();
        setShowToolsMenu(false);
        return;
      }

      // DEPRECATED: 'audit-file' tool removed - functionality now in file attachment cards

      // For other tools, call onAddTool if provided
      if (onAddTool) {
        onAddTool(id);
      }
      setShowToolsMenu(false);
    },
    [onAddTool],
  );

  // Handle file selection
  const handleFileChange = React.useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = event.target.files;
      if (!files || files.length === 0) return;

      logDebug("[chat.composer] Files selected", { count: files.length });

      // Process files
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const filename = file.name;

        // Validate file type (PDF, PNG, JPG only)
        const allowedTypes = [
          "application/pdf",
          "image/png",
          "image/jpeg",
          "image/jpg",
        ];
        if (!allowedTypes.includes(file.type)) {
          alert(
            `Archivo no soportado: ${filename}. Solo se permiten PDF, PNG, JPG.`,
          );
          continue;
        }

        // Validate file size (max 30MB)
        const maxSize = 30 * 1024 * 1024; // 30MB
        if (file.size > maxSize) {
          alert(`Archivo muy grande: ${filename}. Máximo 30MB.`);
          continue;
        }

        // Start upload with progress
        setUploadingFiles((prev) => new Map(prev).set(filename, 0));

        try {
          // MVP-BUG-FIX: Use Files V1 system for ALL file types (PDFs and images)
          logDebug("[chat.composer] Uploading file via Files V1", {
            filename,
            type: file.type,
          });

          // Upload using Files V1 hook (saves to filesStore automatically)
          const attachment = await uploadFileV1(
            file,
            conversationId || currentChatId || undefined,
          );

          if (attachment) {
            logDebug(
              "[chat.composer] File uploaded successfully via Files V1",
              {
                filename,
                file_id: attachment.file_id,
                status: attachment.status,
              },
            );
          } else {
            // Upload failed - error was already shown by useFiles hook
            logDebug("[chat.composer] File upload failed", { filename });
          }

          // Legacy fallback for images if onAddFilesV1Attachment not available
          if (!onAddFilesV1Attachment && file.type !== "application/pdf") {
            // For images, use regular attachment flow
            const response = await apiClient.uploadDocument(file, {
              conversationId: currentChatId || undefined,
              onProgress: (progress) => {
                setUploadingFiles((prev) =>
                  new Map(prev).set(filename, progress),
                );
              },
            });

            // Add to attachments using document_id from response
            if (onAttachmentsChange) {
              const newAttachment: ChatComposerAttachment = {
                id: response.document_id ?? response.doc_id,
                file,
                name: response.filename,
                size: response.size_bytes,
                type: file.type,
                progress: 100,
                status: "completed",
              };
              onAttachmentsChange([...(attachments || []), newAttachment]);
            }

            logDebug("[chat.composer] Image uploaded successfully", {
              filename,
              doc_id: response.document_id,
            });
          }

          // Remove from uploading
          setUploadingFiles((prev) => {
            const next = new Map(prev);
            next.delete(filename);
            return next;
          });
        } catch (error: any) {
          logError("Upload failed in CompactChatComposer", error);
          const errorMsg =
            error?.response?.data?.detail ||
            error?.message ||
            "Error desconocido";
          alert(`Error al subir ${filename}: ${errorMsg}`);
          setUploadingFiles((prev) => {
            const next = new Map(prev);
            next.delete(filename);
            return next;
          });
        }
      }

      // Reset file input
      event.target.value = "";
    },
    [
      attachments,
      onAttachmentsChange,
      currentChatId,
      conversationId,
      uploadFileV1,
      onAddFilesV1Attachment,
    ],
  );

  const isCenter = layout === "center";

  return (
    <div
      className={cn(isCenter ? "w-full" : "sticky bottom-0 w-full", className)}
    >
      {/* Outer wrapper: horizontal centering + responsive padding */}
      <div
        className={cn(
          "mx-auto w-full",
          isCenter ? "max-w-[640px]" : "max-w-3xl px-4 pb-4",
        )}
      >
        <div ref={composerRef} className="relative">
          {/* Tool Menu */}
          <AnimatePresence>
            {showToolsMenu && (
              <motion.div
                initial={{ opacity: 0, y: 8, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 4, scale: 0.98 }}
                transition={{ duration: 0.14, ease: [0.16, 1, 0.3, 1] }}
                className="absolute bottom-full left-0 z-[9999] mb-2 pointer-events-auto"
              >
                <ToolMenu
                  onSelect={handleToolSelect}
                  onClose={() => setShowToolsMenu(false)}
                />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Preview Attachments Row - Estilo Vercel (antes del input) */}
          <AnimatePresence>
            {deduplicatedAttachments.length > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="overflow-hidden"
              >
                <div
                  className="flex flex-row items-end gap-2 overflow-x-auto pb-2"
                  data-testid="preview-attachments"
                >
                  {deduplicatedAttachments.map((attachment) => (
                    <PreviewAttachment
                      key={attachment.file_id}
                      attachment={attachment}
                      isUploading={attachment.status === "PROCESSING"}
                      onRemove={
                        onRemoveFilesV1Attachment
                          ? () => onRemoveFilesV1Attachment(attachment.file_id)
                          : undefined
                      }
                      onAudit={
                        sendAuditForFile
                          ? async () => {
                              logDebug(
                                "[CompactChatComposer] onAudit callback executing",
                                {
                                  sendAuditForFileType: typeof sendAuditForFile,
                                  attachmentFileId: attachment.file_id,
                                  attachmentFilename: attachment.filename,
                                  attachmentStatus: attachment.status,
                                },
                              );
                              await sendAuditForFile(attachment);
                              logDebug(
                                "[CompactChatComposer] sendAuditForFile completed",
                              );
                            }
                          : undefined
                      }
                      showAuditButton={false}
                    />
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Main Composer Container - Minimalist ChatGPT style */}
          <motion.div
            role="form"
            aria-label="Compositor de mensajes"
            className={cn(
              "grid items-center gap-2",
              "rounded-[2rem] p-2",
              "bg-[var(--surface)]",
              "shadow-sm",
              // Dynamic grid: smaller space when tools hidden, full 44px when shown
              SHOW_TOOLS_BUTTON
                ? "grid-cols-[44px,1fr,44px]"
                : "grid-cols-[8px,1fr,44px]",
            )}
            style={{
              boxShadow: "inset 0 0 0 0.5px var(--hairline)",
            }}
            animate={{
              height: isSubmitting ? MIN_HEIGHT + 16 : "auto", // +16 for padding
            }}
            transition={{ duration: 0.12, ease: "easeOut" }}
          >
            {/* Plus Button (Tools) - Minimal space when hidden (8px), full when shown (44px) */}
            <div
              className={cn(
                "shrink-0",
                SHOW_TOOLS_BUTTON ? "w-11" : "w-2", // 44px when shown, 8px when hidden
                !SHOW_TOOLS_BUTTON && "pointer-events-none",
              )}
            >
              {SHOW_TOOLS_BUTTON && (
                <button
                  type="button"
                  onClick={() => setShowToolsMenu(!showToolsMenu)}
                  disabled={disabled || loading}
                  className={cn(
                    "h-11 w-11 rounded-full",
                    "grid place-items-center",
                    "text-muted bg-transparent",
                    "hover:bg-surface-2 active:bg-surface-2",
                    "transition-colors duration-150",
                    "outline-none ring-0 focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0",
                    (disabled || loading) && "cursor-not-allowed opacity-40",
                  )}
                  aria-label="Abrir herramientas"
                  aria-expanded={showToolsMenu}
                  aria-haspopup="menu"
                >
                  <PlusIcon className="h-5 w-5 opacity-80" />
                </button>
              )}
            </div>

            {/* Auto-grow Textarea - No borders, no focus color change */}
            <div className="min-w-0 flex-1">
              <motion.textarea
                ref={taRef}
                value={value}
                onChange={(e) => {
                  onChange(e.target.value);
                  handleFirstInput(); // Finalize creation on first input
                }}
                onKeyDown={handleKeyDown}
                placeholder={dynamicPlaceholder}
                disabled={disabled || loading}
                maxLength={maxLength}
                rows={1}
                className={cn(
                  "w-full resize-none bg-transparent",
                  "text-[15px] leading-6 text-foreground placeholder:text-muted",
                  "outline-none ring-0 border-0",
                  "focus:outline-none focus:ring-0 focus:border-0 focus:border-transparent",
                  "focus-visible:outline-none focus-visible:ring-0",
                  "overflow-y-auto thin-scroll",
                  "transition-[height] duration-150 ease-out",
                  "py-1.5",
                )}
                style={{
                  minHeight: `${MIN_HEIGHT}px`,
                  maxHeight: `${MAX_HEIGHT}px`,
                  height: `${textareaHeight}px`,
                }}
                aria-label="Escribe tu mensaje"
                aria-multiline="true"
                animate={{
                  opacity: isSubmitting ? 0.6 : 1,
                }}
                transition={{ duration: 0.12 }}
              />
            </div>

            {/* Send Button (Arrow Up) or Stop Button - No visible rings */}
            {showCancel && onCancel ? (
              <button
                type="button"
                onClick={onCancel}
                className={cn(
                  "h-11 w-11 shrink-0 rounded-xl",
                  "grid place-items-center",
                  "bg-red-500/20 text-red-300",
                  "hover:bg-red-500/30 active:bg-red-500/40",
                  "transition-colors duration-150",
                  "outline-none ring-0 focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0",
                )}
                aria-label="Detener generación"
              >
                <StopIcon className="h-5 w-5" />
              </button>
            ) : (
              <motion.button
                type="submit"
                onClick={handleSendClick}
                disabled={!canSubmit}
                className={cn(
                  "h-11 w-11 shrink-0 rounded-full",
                  "grid place-items-center",
                  "transition-all duration-150",
                  "outline-none ring-0 focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0",
                  canSubmit
                    ? "bg-primary text-primary-foreground hover:bg-primary/90 active:scale-95"
                    : "bg-muted/20 text-muted cursor-not-allowed",
                )}
                aria-label={
                  isUploading
                    ? "Subiendo archivos..."
                    : loading
                      ? "Analizando..."
                      : hasReadyFiles && !value.trim()
                        ? "Enviar archivos para análisis"
                        : "Enviar mensaje"
                }
                aria-disabled={!canSubmit}
                whileTap={canSubmit ? { scale: 0.92 } : {}}
                transition={{ duration: 0.1 }}
              >
                <SendIconArrowUp className="h-5 w-5" />
              </motion.button>
            )}
          </motion.div>

          {/* Tool Chips (below main bar); las bloqueadas por el despliegue no se pintan */}
          <AnimatePresence>
            {toolsConChipEnComposer(selectedTools).length > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="mt-2 overflow-hidden"
              >
                <div className="flex items-center gap-2 overflow-x-auto thin-scroll px-1">
                  {toolsConChipEnComposer(selectedTools)
                    .slice(0, 4)
                    .map((id) => {
                      const tool = TOOL_REGISTRY[id];
                      if (!tool) return null;
                      const Icon = tool.Icon;
                      // Una tool bloqueada nunca llega aquí; se conserva la rama
                      // informativa por si el despliegue bloquea una con chip.
                      const bloqueada = isLockedTool(id);
                      return (
                        <motion.div
                          key={id}
                          initial={{ opacity: 0, scale: 0.9 }}
                          animate={{ opacity: 1, scale: 1 }}
                          exit={{ opacity: 0, scale: 0.9 }}
                          transition={{ duration: 0.12 }}
                          className={cn(
                            "group flex h-9 items-center gap-2 shrink-0",
                            "rounded-xl border border-primary/60 bg-primary/15 pl-2",
                            bloqueada ? "pr-3" : "pr-1",
                            "text-primary",
                            !bloqueada &&
                              "transition-colors hover:bg-primary/25",
                          )}
                          title={
                            bloqueada
                              ? `${tool.label}: siempre activa en este asistente`
                              : tool.label
                          }
                          data-testid={`tool-chip-${id}`}
                        >
                          <Icon className="h-4 w-4" />
                          <span className="text-sm font-medium">
                            {tool.label}
                          </span>
                          {!bloqueada && (
                            <button
                              type="button"
                              aria-label={`Quitar ${tool.label}`}
                              onClick={() => onRemoveTool?.(id)}
                              className={cn(
                                "grid place-items-center rounded-lg p-1",
                                "text-primary hover:bg-primary/20",
                                "transition-colors",
                              )}
                            >
                              <CloseIcon className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </motion.div>
                      );
                    })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* File Upload Cards with Progress - DESHABILITADO: Usando PreviewAttachment en su lugar */}
          {/* NOTA: Esta sección mostraba tarjetas grandes con gradientes y barras de progreso */}
          {/* Reemplazado por PreviewAttachment más arriba (líneas 584-613) para UX más limpia */}
          {/*
          <AnimatePresence>
            {(uploadingFiles.size > 0 ||
              (attachments && attachments.length > 0)) && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="mt-2 overflow-hidden"
              >
                <div className="space-y-2">
                  {Array.from(uploadingFiles.entries()).map(
                    ([filename, progress]) => {
                      const fileExt = filename.split(".").pop()?.toLowerCase();
                      const isPdf = fileExt === "pdf";
                      const isImage = ["png", "jpg", "jpeg"].includes(
                        fileExt || "",
                      );

                      return (
                        <motion.div
                          key={`uploading-${filename}`}
                          initial={{ opacity: 0, y: 8, scale: 0.95 }}
                          animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={{ opacity: 0, y: -8, scale: 0.95 }}
                          transition={{ duration: 0.3, ease: "easeOut" }}
                          className="group rounded-2xl border border-blue-500/30 bg-gradient-to-br from-blue-500/10 to-indigo-500/10 p-4 shadow-md hover:shadow-lg hover:scale-[1.01] transition-all duration-200"
                        >
                          <div className="flex items-center gap-4">
                            <div
                              className={cn(
                                "flex h-14 w-14 items-center justify-center rounded-xl shadow-md transition-all duration-200 group-hover:scale-110 group-hover:shadow-lg",
                                isPdf
                                  ? "bg-gradient-to-br from-red-500 to-pink-600"
                                  : isImage
                                    ? "bg-gradient-to-br from-blue-500 to-indigo-600"
                                    : "bg-gradient-to-br from-purple-500 to-violet-600",
                              )}
                            >
                              {isPdf ? (
                                <svg
                                  className="h-7 w-7 text-white"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                  />
                                  <text
                                    x="7"
                                    y="17"
                                    fill="white"
                                    fontSize="5"
                                    fontWeight="bold"
                                  >
                                    PDF
                                  </text>
                                </svg>
                              ) : isImage ? (
                                <svg
                                  className="h-7 w-7 text-white"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <rect
                                    x="3"
                                    y="3"
                                    width="18"
                                    height="18"
                                    rx="2"
                                    ry="2"
                                    strokeWidth={2}
                                  />
                                  <circle cx="8.5" cy="8.5" r="1.5" />
                                  <polyline
                                    points="21 15 16 10 5 21"
                                    strokeWidth={2}
                                  />
                                </svg>
                              ) : (
                                <svg
                                  className="h-7 w-7 text-white"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                  />
                                </svg>
                              )}
                            </div>

                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-semibold text-foreground truncate">
                                {filename}
                              </p>
                              <div className="mt-2 flex items-center gap-3">
                                <div className="flex-1 h-2 bg-zinc-800/80 rounded-full overflow-hidden shadow-inner">
                                  <motion.div
                                    className="h-full bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 shadow-lg"
                                    initial={{ width: 0 }}
                                    animate={{ width: `${progress}%` }}
                                    transition={{
                                      duration: 0.3,
                                      ease: "easeOut",
                                    }}
                                  />
                                </div>
                                <span className="text-xs font-bold text-blue-300 min-w-[3ch]">
                                  {progress}%
                                </span>
                              </div>
                            </div>
                          </div>
                        </motion.div>
                      );
                    },
                  )}

                  {attachments?.map((attachment) => {
                    const fileExt = attachment.name
                      .split(".")
                      .pop()
                      ?.toLowerCase();
                    const isPdf = fileExt === "pdf";
                    const isImage = ["png", "jpg", "jpeg"].includes(
                      fileExt || "",
                    );

                    return (
                      <motion.div
                        key={attachment.id}
                        initial={{ opacity: 0, y: 8, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: -8, scale: 0.95 }}
                        transition={{ duration: 0.3, ease: "easeOut" }}
                        className="group rounded-2xl border border-emerald-500/40 bg-gradient-to-br from-emerald-500/15 to-green-500/15 p-4 shadow-md hover:shadow-lg hover:scale-[1.01] transition-all duration-200"
                      >
                        <div className="flex items-center gap-4">
                          <div className="relative">
                            <div
                              className={cn(
                                "flex h-14 w-14 items-center justify-center rounded-xl shadow-md transition-all duration-200 group-hover:scale-110 group-hover:shadow-lg",
                                isPdf
                                  ? "bg-gradient-to-br from-red-500 to-pink-600"
                                  : isImage
                                    ? "bg-gradient-to-br from-blue-500 to-indigo-600"
                                    : "bg-gradient-to-br from-purple-500 to-violet-600",
                              )}
                            >
                              {isPdf ? (
                                <svg
                                  className="h-7 w-7 text-white"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                  />
                                  <text
                                    x="7"
                                    y="17"
                                    fill="white"
                                    fontSize="5"
                                    fontWeight="bold"
                                  >
                                    PDF
                                  </text>
                                </svg>
                              ) : isImage ? (
                                <svg
                                  className="h-7 w-7 text-white"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <rect
                                    x="3"
                                    y="3"
                                    width="18"
                                    height="18"
                                    rx="2"
                                    ry="2"
                                    strokeWidth={2}
                                  />
                                  <circle cx="8.5" cy="8.5" r="1.5" />
                                  <polyline
                                    points="21 15 16 10 5 21"
                                    strokeWidth={2}
                                  />
                                </svg>
                              ) : (
                                <svg
                                  className="h-7 w-7 text-white"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                  />
                                </svg>
                              )}
                            </div>
                            <div className="absolute -bottom-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-emerald-500 to-green-600 shadow-lg ring-2 ring-zinc-900">
                              <svg
                                className="h-3.5 w-3.5 text-white"
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
                            </div>
                          </div>

                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-zinc-100 truncate">
                              {attachment.name}
                            </p>
                            <p className="text-xs font-medium text-emerald-300 mt-1">
                              {(attachment.size / 1024).toFixed(0)} KB · ✓ Listo
                            </p>
                          </div>

                          <button
                            type="button"
                            onClick={() => {
                              const filtered = attachments.filter(
                                (a) => a.id !== attachment.id,
                              );
                              onAttachmentsChange?.(filtered);
                            }}
                            className="flex-shrink-0 p-2 rounded-xl hover:bg-red-500/20 text-muted hover:text-red-400 transition-all duration-200 hover:scale-110 opacity-0 group-hover:opacity-100"
                            aria-label="Eliminar archivo"
                          >
                            <CloseIcon className="h-4 w-4" />
                          </button>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          */}

          {/* Files V1 Section - DESHABILITADO: Usando PreviewAttachment en su lugar */}
          {/* NOTA: FileAttachmentList mostraba lista detallada con botones de auditoría */}
          {/* Ahora usamos solo PreviewAttachment arriba del input (estilo Vercel) */}
          {/* Si necesitas botones de auditoría, descomentar esta sección */}
          {/* {onAddFilesV1Attachment && (
            <AnimatePresence>
              {(filesV1Attachments?.length ?? 0) > 0 && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.16, ease: "easeOut" }}
                  className="mt-3 space-y-2"
                >
                  {onRemoveFilesV1Attachment && (
                    <FileAttachmentList
                      attachments={filesV1Attachments}
                      onRemove={onRemoveFilesV1Attachment}
                      onAudit={sendAuditForFile}
                    />
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          )} */}

          {/* La espera se muestra una sola vez, en la burbuja del asistente
              (TypingIndicator); aquí había una segunda barra con "Analizando
              con Saptiva Turbo…" (Equipo, 2026-10-21). */}
          {/* Parche B: ARIA live region for accessibility announcements */}
          <div
            ref={liveRegionRef}
            role="status"
            aria-live="polite"
            aria-atomic="true"
            className="sr-only"
          />

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            multiple
            onChange={handleFileChange}
            className="hidden"
            aria-label="Seleccionar archivos"
          />
        </div>
      </div>
    </div>
  );
}
