/**
 * useFiles - Hook for Files V1 unified file ingestion
 *
 * MVP-LOCK: Now persists attachments by chatId to survive page refreshes
 *
 * Simplified hook for uploading files to /api/files/upload
 * Handles validation, upload, error mapping, idempotency, and SSE progress tracking
 *
 * See: VALIDATION_REPORT_V1.md for complete specification
 */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import toast from "react-hot-toast";
import { useApiClient } from "../lib/api-client";
import { sha256Hex } from "../lib/hash";
import { logDebug, logError } from "../lib/logger";
import type {
  FileIngestResponse,
  FileIngestBulkResponse,
  FileError,
  UploadProgress,
  FileAttachment,
} from "../types/files";
import {
  validateFile,
  getErrorMessage,
  MAX_UPLOAD_SIZE,
  RATE_LIMIT_UPLOADS_PER_MINUTE,
} from "../types/files";
import { useFilesStore } from "../lib/stores/files-store";

export type LastReadyFile = FileAttachment | null;

export interface UseFilesReturn {
  // Upload functions
  uploadFile: (
    file: File,
    conversationId?: string,
    turnstileToken?: string,
  ) => Promise<FileAttachment | null>;
  uploadFiles: (
    files: File[],
    conversationId?: string,
    turnstileToken?: string,
  ) => Promise<FileAttachment[]>;

  // State
  isUploading: boolean;
  uploadProgress: UploadProgress | null;
  error: string | null;
  clearError: () => void;

  // Attachments management
  attachments: FileAttachment[];
  addAttachment: (attachment: FileAttachment) => void;
  removeAttachment: (fileId: string) => void;
  clearAttachments: (overrideChatId?: string) => void;
  lastReadyFile: LastReadyFile;
}

/**
 * MVP-LOCK: Hook now accepts optional chatId for persistent storage
 * @param chatId - Optional conversation ID to persist attachments (defaults to "draft")
 * @param hasMessages - Whether the chat has messages (used for firewall logic)
 */
export function useFiles(
  chatId?: string,
  hasMessages?: boolean,
): UseFilesReturn {
  const apiClient = useApiClient();

  // MVP-LOCK: Use selectors to prevent unnecessary re-renders
  const byChat = useFilesStore((state) => state.byChat);
  const addToChat = useFilesStore((state) => state.addToChat);
  const removeFromChat = useFilesStore((state) => state.removeFromChat);
  const clearForChat = useFilesStore((state) => state.clearForChat);

  // Use "draft" as fallback when no chatId is provided
  const effectiveChatId = chatId || "draft";

  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  // SSE tracking
  const eventSourceRef = useRef<EventSource | null>(null);
  const processingFileRef = useRef<{
    file_id: string;
    filename: string;
  } | null>(null);

  // MVP-LOCK: Select attachments directly from store
  const storedAttachments = byChat[effectiveChatId] ?? [];

  // MVP-LOCK: Firewall logic to prevent historical files from appearing in composer
  const attachments = useMemo(() => {
    // 🛡️ FIREWALL DE HISTORIAL: Detectar si es un chat existente (histórico) CON mensajes
    const isExistingChat =
      effectiveChatId &&
      effectiveChatId !== "draft" &&
      !effectiveChatId.startsWith("temp-") &&
      !effectiveChatId.startsWith("creating") &&
      hasMessages === true;

    if (isExistingChat) {
      return []; // 🚫 Empty input for existing chats
    }

    return storedAttachments;
  }, [effectiveChatId, hasMessages, storedAttachments]);

  const lastReadyFile = useMemo(() => {
    const ready = attachments.filter(
      (attachment) => attachment.status === "READY",
    );
    return ready.length > 0 ? ready[ready.length - 1] : null;
  }, [attachments]);

  // Cleanup SSE connection on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  // Rate limit tracking (client-side, informational only)
  const uploadTimestamps = useRef<number[]>([]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // MVP-LOCK: Sync with persistent store
  const addAttachment = useCallback(
    (attachment: FileAttachment) => {
      addToChat(effectiveChatId, attachment);
      logDebug("[useFiles] Added attachment to store", {
        chatId: effectiveChatId,
        file_id: attachment.file_id,
      });
    },
    [effectiveChatId, addToChat],
  );

  // MVP-LOCK: Sync with persistent store
  const removeAttachment = useCallback(
    (fileId: string) => {
      removeFromChat(effectiveChatId, fileId);
      logDebug("[useFiles] Removed attachment from store", {
        chatId: effectiveChatId,
        file_id: fileId,
      });
    },
    [effectiveChatId, removeFromChat],
  );

  // MVP-LOCK: Sync with persistent store
  // 🔧 FIX: Accept optional chatId to avoid stale closure issues
  const clearAttachments = useCallback(
    (overrideChatId?: string) => {
      const targetChatId = overrideChatId || effectiveChatId;

      logDebug("[useFiles] 🔧 clearAttachments called", {
        targetChatId,
        effectiveChatId,
        overrideProvided: !!overrideChatId,
        currentAttachments: attachments.length,
        chatIdType: targetChatId === "draft" ? "draft" : "uuid",
      });

      // Clear from Zustand store (will auto-persist to localStorage)
      clearForChat(targetChatId);

      // Also clear "draft" if we're clearing a real chat ID
      // This prevents orphaned attachments when transitioning draft → UUID
      if (targetChatId !== "draft") {
        clearForChat("draft");
        logDebug("[useFiles] Also cleared draft attachments", {
          primaryChatId: targetChatId,
        });
      }

      logDebug("[useFiles] ✅ Cleared attachments from store", {
        clearedChatId: targetChatId,
      });
    },
    [effectiveChatId, clearForChat, attachments],
  );

  /**
   * Check client-side rate limit (informational, server enforces)
   */
  const checkClientRateLimit = useCallback((): boolean => {
    const now = Date.now();
    const oneMinuteAgo = now - 60 * 1000;

    // Clean old timestamps
    uploadTimestamps.current = uploadTimestamps.current.filter(
      (ts) => ts > oneMinuteAgo,
    );

    // Check if we've hit the limit
    if (uploadTimestamps.current.length >= RATE_LIMIT_UPLOADS_PER_MINUTE) {
      return false; // Rate limited
    }

    return true; // OK to upload
  }, []);

  /**
   * Track upload for client-side rate limiting
   */
  const trackUpload = useCallback(() => {
    uploadTimestamps.current.push(Date.now());
  }, []);

  /**
   * Connect to SSE for real-time progress updates
   */
  const connectToSSE = useCallback(
    (
      fileId: string,
      filename: string,
      fileSize: number,
      conversationId?: string,
    ) => {
      // Close any existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const traceId = crypto.randomUUID();
      const token = apiClient.getToken();
      const tokenParam = token ? encodeURIComponent(token) : "";
      const eventSourceUrl = `/api/files/events/${fileId}?t=${encodeURIComponent(traceId)}&token=${tokenParam}`;

      logDebug("[useFiles] Connecting to SSE", {
        file_id: fileId,
        url: eventSourceUrl,
      });

      try {
        const eventSource = new EventSource(eventSourceUrl, {
          withCredentials: true,
        });

        eventSourceRef.current = eventSource;
        processingFileRef.current = { file_id: fileId, filename };

        // Set initial progress
        setUploadProgress({
          loaded: 0,
          total: fileSize,
          percentage: 5, // Show 5% to indicate upload started
        });

        eventSource.onopen = () => {
          logDebug("[useFiles] SSE connected", { file_id: fileId });
        };

        // Handle meta event (initial status)
        eventSource.addEventListener("meta", (event) => {
          try {
            const data = JSON.parse(event.data);
            logDebug("[useFiles] SSE meta event", data);

            const progress = data.pct || 10;
            setUploadProgress({
              loaded: Math.floor((fileSize * progress) / 100),
              total: fileSize,
              percentage: progress,
            });
          } catch (err) {
            logError("[useFiles] Failed to parse meta event", err);
          }
        });

        // Handle progress events
        eventSource.addEventListener("progress", (event) => {
          try {
            const data = JSON.parse(event.data);
            logDebug("[useFiles] SSE progress event", data);

            const progress = Math.min(data.pct || 0, 95); // Cap at 95% until ready
            setUploadProgress({
              loaded: Math.floor((fileSize * progress) / 100),
              total: fileSize,
              percentage: progress,
            });
          } catch (err) {
            logError("[useFiles] Failed to parse progress event", err);
          }
        });

        // Handle ready event (processing complete)
        eventSource.addEventListener("ready", (event) => {
          try {
            const data = JSON.parse(event.data);
            logDebug("[useFiles] SSE ready event", data);

            // Show 100% progress
            setUploadProgress({
              loaded: fileSize,
              total: fileSize,
              percentage: 100,
            });

            // Update attachment to READY status (replaces PROCESSING state)
            const attachment: FileAttachment = {
              file_id: fileId,
              filename: filename,
              status: "READY",
              bytes: fileSize,
              pages: data.pages,
              mimetype: data.mimetype,
            };

            const targetChatId = conversationId || effectiveChatId;

            // Remove old PROCESSING attachment and add READY one
            removeFromChat(targetChatId, fileId);
            addToChat(targetChatId, attachment);

            logDebug("[useFiles] File ready, updated in store", {
              chatId: targetChatId,
              file_id: fileId,
              status: "READY",
            });

            // Toast notification
            toast.success(
              `✓ ${filename} listo para analizar en esta conversación`,
              { duration: 2500 },
            );

            // Cleanup
            eventSource.close();
            eventSourceRef.current = null;
            processingFileRef.current = null;
            setIsUploading(false);
            setUploadProgress(null);
          } catch (err) {
            logError("[useFiles] Failed to parse ready event", err);
          }
        });

        // Handle failed event
        eventSource.addEventListener("failed", (event) => {
          try {
            const data = JSON.parse(event.data);
            logError("[useFiles] SSE failed event", data);

            const errorMessage = data.error?.detail || "Processing failed";
            setError(`🔧 ${errorMessage}`);

            // Cleanup
            eventSource.close();
            eventSourceRef.current = null;
            processingFileRef.current = null;
            setIsUploading(false);
            setUploadProgress(null);
          } catch (err) {
            logError("[useFiles] Failed to parse failed event", err);
          }
        });

        // Handle heartbeat (keep-alive)
        eventSource.addEventListener("heartbeat", (event) => {
          logDebug("[useFiles] SSE heartbeat", { file_id: fileId });
        });

        // Handle errors
        eventSource.onerror = (err) => {
          logError("[useFiles] SSE error", err);

          // If we already got the file processed, don't show error
          if (processingFileRef.current?.file_id !== fileId) {
            return;
          }

          setError(
            "⚠️ Conexión perdida con el servidor. El archivo puede estar procesándose.",
          );

          // Cleanup after timeout
          setTimeout(() => {
            if (eventSourceRef.current === eventSource) {
              eventSource.close();
              eventSourceRef.current = null;
              processingFileRef.current = null;
              setIsUploading(false);
              setUploadProgress(null);
            }
          }, 5000);
        };
      } catch (err: any) {
        logError("[useFiles] Failed to create EventSource", {
          error: err.message,
          file_id: fileId,
        });
        setError("⚠️ Error al conectar para actualizaciones de progreso");
      }
    },
    [effectiveChatId, addToChat, removeFromChat, apiClient],
  );

  /**
   * Upload a single file with SSE progress tracking
   */
  const uploadFile = useCallback(
    async (
      file: File,
      conversationId?: string,
      turnstileToken?: string,
    ): Promise<FileAttachment | null> => {
      setError(null);

      // Client-side validation
      const validation = validateFile(file);
      if (!validation.valid) {
        setError(validation.error!);
        logError("[useFiles] Validation failed", {
          filename: file.name,
          error: validation.error,
        });
        return null;
      }

      // Client-side rate limit check (informational)
      if (!checkClientRateLimit()) {
        setError(
          `Demasiados archivos subidos. Espera un minuto. (${RATE_LIMIT_UPLOADS_PER_MINUTE} máximo por minuto)`,
        );
        logError("[useFiles] Client rate limit exceeded", {
          filename: file.name,
        });
        return null;
      }

      setIsUploading(true);
      setUploadProgress({ loaded: 0, total: file.size, percentage: 0 });

      // Create temporary attachment IMMEDIATELY to show in UI with spinner
      const tempFileId = crypto.randomUUID();
      const targetChatId = conversationId || effectiveChatId;

      const tempAttachment: FileAttachment = {
        file_id: tempFileId,
        filename: file.name,
        status: "PROCESSING",
        bytes: file.size,
        mimetype: file.type,
      };

      // Add to store IMMEDIATELY - user sees thumbnail instantly
      addToChat(targetChatId, tempAttachment);

      logDebug("[useFiles] Added temporary attachment to store BEFORE fetch", {
        chatId: targetChatId,
        file_id: tempFileId,
        filename: file.name,
        status: "PROCESSING",
      });

      try {
        // Generate idempotency key from file hash
        const buffer = await file.arrayBuffer();
        const digest = await sha256Hex(buffer);
        const idempotencyKey = `${digest}:${conversationId || "no-chat"}`;

        // Generate trace ID for observability
        const traceId = crypto.randomUUID();

        logDebug("[useFiles] Starting upload", {
          filename: file.name,
          size: file.size,
          type: file.type,
          traceId,
          idempotencyKey,
        });

        // Prepare form data
        const formData = new FormData();
        formData.append("files", file);
        if (conversationId) {
          formData.append("conversation_id", conversationId);
        }
        // Add Turnstile token if available (for Cloudflare challenge bypass)
        if (turnstileToken) {
          formData.append("cf-turnstile-response", turnstileToken);
        }

        // Upload to backend (non-blocking - returns immediately with file_id)
        const response = await fetch("/api/files/upload", {
          method: "POST",
          body: formData,
          headers: {
            Authorization: `Bearer ${apiClient.getToken()}`,
            "X-Trace-Id": traceId,
            "Idempotency-Key": idempotencyKey,
          },
          credentials: "include",
        });

        if (!response.ok) {
          // FE-UX-2: Enhanced error handling with actionable messages
          const errorData: { detail?: string; error?: FileError } =
            await response.json().catch(() => ({}));

          // Map backend error to user-friendly message
          if (errorData.error) {
            const userMessage = getErrorMessage(errorData.error);
            throw new Error(userMessage);
          }

          // FE-UX-2: Actionable error messages by status code
          if (response.status === 413) {
            throw new Error(
              `❌ El archivo es demasiado grande. Comprime o divide el PDF antes de subir. Máximo: ${MAX_UPLOAD_SIZE / (1024 * 1024)} MB.`,
            );
          } else if (response.status === 415) {
            throw new Error(
              "❌ Formato no soportado. Usa PDF, PNG, JPG, GIF o HEIC. Si tienes un archivo diferente, conviértelo primero.",
            );
          } else if (response.status === 429) {
            throw new Error(
              `⏸️ Demasiados archivos subidos. Espera 60 segundos e intenta de nuevo. Límite: ${RATE_LIMIT_UPLOADS_PER_MINUTE}/minuto.`,
            );
          } else if (response.status === 410) {
            throw new Error(
              "⚠️ El documento expiró (1 hora de TTL). Sube el archivo nuevamente para incluirlo en el chat.",
            );
          } else if (response.status === 500) {
            throw new Error(
              "🔧 Error del servidor al procesar el archivo. Verifica que el archivo no esté corrupto e intenta de nuevo.",
            );
          } else if (response.status === 503) {
            throw new Error(
              "⏳ Servicio temporalmente no disponible. Intenta de nuevo en unos segundos.",
            );
          }

          throw new Error(
            errorData.detail ||
              `⚠️ Error al subir archivo (código ${response.status}). Intenta de nuevo.`,
          );
        }

        const payload: FileIngestBulkResponse = await response.json();

        if (!payload.files || payload.files.length === 0) {
          throw new Error("Invalid response from server");
        }

        const ingestResponse: FileIngestResponse = payload.files[0];

        // Check if processing failed immediately
        if (ingestResponse.status === "FAILED") {
          const userMessage = ingestResponse.error
            ? getErrorMessage(ingestResponse.error)
            : "Processing failed";
          throw new Error(userMessage);
        }

        // Track successful upload
        trackUpload();

        logDebug("[useFiles] Upload accepted by server", {
          file_id: ingestResponse.file_id,
          status: ingestResponse.status,
        });

        // Remove temporary attachment and add real one with server-assigned file_id
        removeFromChat(targetChatId, tempFileId);

        logDebug(
          "[useFiles] Removed temporary attachment after server response",
          {
            chatId: targetChatId,
            tempFileId,
            realFileId: ingestResponse.file_id,
          },
        );

        // If already READY (cached or instant processing), return immediately
        if (ingestResponse.status === "READY") {
          setUploadProgress({
            loaded: file.size,
            total: file.size,
            percentage: 100,
          });

          const attachment: FileAttachment = {
            file_id: ingestResponse.file_id,
            filename: ingestResponse.filename || file.name,
            status: ingestResponse.status,
            bytes: ingestResponse.bytes,
            pages: ingestResponse.pages,
            mimetype: ingestResponse.mimetype,
          };

          addToChat(targetChatId, attachment);

          logDebug("[useFiles] File immediately ready (cached)", {
            chatId: targetChatId,
            file_id: attachment.file_id,
          });

          toast.success(
            `✓ ${attachment.filename} listo para analizar en esta conversación`,
            { duration: 2500 },
          );

          setIsUploading(false);
          setUploadProgress(null);

          return attachment;
        }

        // File is still PROCESSING - connect to SSE for real-time updates
        logDebug("[useFiles] File processing, connecting to SSE", {
          file_id: ingestResponse.file_id,
          status: ingestResponse.status,
        });

        // Create real attachment in PROCESSING state with server file_id
        const processingAttachment: FileAttachment = {
          file_id: ingestResponse.file_id,
          filename: ingestResponse.filename || file.name,
          status: "PROCESSING",
          bytes: ingestResponse.bytes,
          pages: ingestResponse.pages,
          mimetype: ingestResponse.mimetype,
        };

        // Add real attachment (temp already removed above)
        addToChat(targetChatId, processingAttachment);

        logDebug("[useFiles] Added real processing attachment to store", {
          chatId: targetChatId,
          file_id: processingAttachment.file_id,
          status: processingAttachment.status,
        });

        connectToSSE(
          ingestResponse.file_id,
          ingestResponse.filename || file.name,
          file.size,
          conversationId,
        );

        return processingAttachment;
      } catch (err: any) {
        const errorMessage = err.message || "Failed to upload file";
        setError(errorMessage);

        // Remove temporary attachment on error
        removeFromChat(targetChatId, tempFileId);

        logError("[useFiles] Upload failed, removed temporary attachment", {
          filename: file.name,
          error: errorMessage,
          tempFileId,
        });

        setIsUploading(false);
        setUploadProgress(null);

        return null;
      }
    },
    [
      apiClient,
      checkClientRateLimit,
      trackUpload,
      addToChat,
      removeFromChat,
      effectiveChatId,
      connectToSSE,
    ],
  );

  /**
   * Upload multiple files
   */
  const uploadFiles = useCallback(
    async (
      files: File[],
      conversationId?: string,
      turnstileToken?: string,
    ): Promise<FileAttachment[]> => {
      setError(null);

      if (files.length === 0) {
        return [];
      }

      setIsUploading(true);

      const attachments: FileAttachment[] = [];
      let failed = 0;

      for (let i = 0; i < files.length; i++) {
        const file = files[i];

        logDebug("[useFiles] Uploading file", {
          index: i + 1,
          total: files.length,
          filename: file.name,
          hasTurnstile: !!turnstileToken,
        });

        const attachment = await uploadFile(
          file,
          conversationId,
          turnstileToken,
        );

        if (attachment) {
          attachments.push(attachment);
        } else {
          failed++;
        }

        // Small delay between uploads to avoid overwhelming the server
        if (i < files.length - 1) {
          await new Promise((resolve) => setTimeout(resolve, 500));
        }
      }

      if (failed > 0) {
        setError(
          `${failed} de ${files.length} archivos fallaron. Revisa los detalles.`,
        );
      }

      setIsUploading(false);

      return attachments;
    },
    [uploadFile],
  );

  return {
    uploadFile,
    uploadFiles,
    isUploading,
    uploadProgress,
    error,
    clearError,
    attachments,
    addAttachment,
    removeAttachment,
    clearAttachments,
    lastReadyFile,
  };
}
