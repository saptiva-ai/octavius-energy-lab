/**
 * useDocumentReview - Hook for document upload and review management
 *
 * Integrates with chat store to persist file review messages
 */

import { useState, useCallback } from "react";
import { useApiClient } from "../lib/api-client";
import { useChatStore } from "../lib/stores/chat-store";
import { logDebug } from "../lib/logger";
import { sha256Hex } from "../lib/hash";

export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export interface DocumentMetadata {
  docId: string;
  filename: string;
  totalPages: number;
  status: string;
}

export interface ReviewJob {
  jobId: string;
  status: string;
  progress: number;
  currentStage?: string;
  errorMessage?: string;
}

export interface UseDocumentReviewReturn {
  // Upload
  uploadFile: (
    file: File,
    conversationId?: string,
  ) => Promise<DocumentMetadata | null>;
  uploadProgress: UploadProgress | null;
  isUploading: boolean;

  // Review
  startReview: (
    docId: string,
    options?: ReviewOptions,
  ) => Promise<string | null>;
  getReviewStatus: (jobId: string) => Promise<ReviewJob | null>;
  getReviewReport: (docId: string) => Promise<any | null>;

  // State
  error: string | null;
  clearError: () => void;
}

export interface ReviewOptions {
  model?: string;
  rewritePolicy?: "conservative" | "moderate" | "aggressive";
  summary?: boolean;
  colorAudit?: boolean;
}

export function useDocumentReview(): UseDocumentReviewReturn {
  const apiClient = useApiClient();
  const { addFileReviewMessage, updateFileReviewMessage } = useChatStore();

  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(
    null,
  );
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const uploadFile = useCallback(
    async (
      file: File,
      conversationId?: string,
    ): Promise<DocumentMetadata | null> => {
      setError(null);
      setIsUploading(true);
      setUploadProgress({ loaded: 0, total: file.size, percentage: 0 });

      // 1. Create optimistic message in chat store
      const messageId = crypto.randomUUID();
      const timestamp = new Date().toISOString();

      logDebug("[useDocumentReview] Creating optimistic message", {
        messageId,
        filename: file.name,
      });

      addFileReviewMessage({
        id: messageId,
        role: "system",
        kind: "file-review",
        content: `Subiendo ${file.name}…`,
        timestamp,
        review: {
          filename: file.name,
          fileSize: file.size,
          totalPages: 0,
          status: "uploading",
          stages: [],
        },
      });

      try {
        // 2. Upload file to backend
        const formData = new FormData();
        formData.append("files", file);
        if (conversationId) {
          formData.append("conversation_id", conversationId);
        }

        const legacyFormData = new FormData();
        legacyFormData.append("file", file);
        if (conversationId) {
          legacyFormData.append("conversation_id", conversationId);
        }

        const traceId = crypto.randomUUID();
        const buffer = await file.arrayBuffer();
        const digest = await sha256Hex(buffer);
        const idempotencyKey = `${digest}:${conversationId || "no-chat"}`;

        const uploadResponse = await fetch("/api/files/upload", {
          method: "POST",
          body: formData,
          headers: {
            Authorization: `Bearer ${apiClient.getToken()}`,
            "X-Trace-Id": traceId,
            "Idempotency-Key": idempotencyKey,
          },
          credentials: "include",
        });

        const response = uploadResponse.ok
          ? uploadResponse
          : await fetch("/api/documents/upload", {
              method: "POST",
              body: legacyFormData,
              headers: {
                Authorization: `Bearer ${apiClient.getToken()}`,
                "X-Trace-Id": traceId,
                "Idempotency-Key": idempotencyKey,
              },
              credentials: "include",
            });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || "Upload failed");
        }

        const payload = await response.json();
        const ingest = Array.isArray(payload?.files)
          ? payload.files[0]
          : payload;

        if (!ingest) {
          throw new Error("Invalid upload response");
        }

        const docId = ingest.doc_id ?? ingest.file_id;
        const totalPages = ingest.total_pages ?? ingest.pages ?? 0;
        const status = (ingest.status || "READY").toLowerCase();

        setUploadProgress({
          loaded: file.size,
          total: file.size,
          percentage: 100,
        });

        // 3. Update message with doc_id and uploaded status
        logDebug("[useDocumentReview] Upload complete", { docId });

        updateFileReviewMessage(messageId, {
          docId,
          totalPages,
          status: status === "ready" ? "uploaded" : "processing",
        });

        return {
          docId,
          filename: ingest.filename ?? file.name,
          totalPages,
          status: ingest.status,
        };
      } catch (err: any) {
        setError(err.message || "Failed to upload file");

        // Update message with error state
        updateFileReviewMessage(messageId, {
          status: "error",
          errors: [err.message || "Failed to upload file"],
        });

        return null;
      } finally {
        setIsUploading(false);
      }
    },
    [apiClient, addFileReviewMessage, updateFileReviewMessage],
  );

  const startReview = useCallback(
    async (
      docId: string,
      options: ReviewOptions = {},
    ): Promise<string | null> => {
      setError(null);

      try {
        const response = await apiClient.startDocumentReview({
          doc_id: docId,
          model: options.model || "Saptiva Turbo",
          rewrite_policy: options.rewritePolicy || "conservative",
          summary: options.summary !== false,
          color_audit: options.colorAudit !== false,
        });

        return response.job_id;
      } catch (err: any) {
        setError(apiClient.handleError(err));
        return null;
      }
    },
    [apiClient],
  );

  const getReviewStatus = useCallback(
    async (jobId: string): Promise<ReviewJob | null> => {
      try {
        const data = await apiClient.getReviewStatus(jobId);
        return {
          jobId: data.job_id,
          status: data.status,
          progress: data.progress,
          currentStage: data.current_stage,
          errorMessage: data.error_message,
        };
      } catch (err: any) {
        setError(apiClient.handleError(err));
        return null;
      }
    },
    [apiClient],
  );

  const getReviewReport = useCallback(
    async (docId: string): Promise<any | null> => {
      try {
        const data = await apiClient.getReviewReport(docId);
        return data;
      } catch (err: any) {
        setError(apiClient.handleError(err));
        return null;
      }
    },
    [apiClient],
  );

  return {
    uploadFile,
    uploadProgress,
    isUploading,
    startReview,
    getReviewStatus,
    getReviewReport,
    error,
    clearError,
  };
}
