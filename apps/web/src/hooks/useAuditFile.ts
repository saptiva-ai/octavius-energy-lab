/**
 * useAuditFile Hook
 *
 * Manages the complete audit file workflow:
 * 1. Upload PDF document
 * 2. Wait for document processing (ready status)
 * 3. Trigger validation audit (Copiloto Audit)
 * 4. Return findings report
 *
 * Usage:
 *   const { upload, validate, reset, ...state } = useAuditFile();
 *   await upload(file);
 *   await validate('ClientName');
 *   // state.report contains ValidationReportResponse
 */

import { useState, useCallback } from "react";
import { apiClient } from "@/lib/api-client";
import type {
  AuditFileState,
  ValidationReportResponse,
} from "@/types/validation";
import type {
  ChatMessage as ChatMessageType,
  ChatMessageStatus,
} from "@/lib/types";
import { logDebug, logError, logWarn } from "@/lib/logger";

const initialState: AuditFileState = {
  file: null,
  uploading: false,
  validating: false,
  error: null,
  documentId: null,
  report: null,
};

const MAX_POLL_ATTEMPTS = 30; // 30 attempts * 2s = 60s max wait
const POLL_INTERVAL_MS = 2000; // 2 seconds

export function useAuditFile() {
  const [state, setState] = useState<AuditFileState>(initialState);

  /**
   * Poll document status until it's ready or timeout
   */
  const pollDocumentStatus = useCallback(
    async (documentId: string): Promise<boolean> => {
      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
        try {
          // Check document status
          // @ts-ignore - TODO: Add public method to ApiClient for this
          const response = await apiClient.client.get(
            `/api/files/status/${documentId}`,
            {
              withCredentials: true,
            },
          );

          const status = response.data?.status?.toLowerCase();
          logDebug(
            `[useAuditFile] Poll attempt ${attempt + 1}: status=${status}`,
          );

          if (status === "ready") {
            return true;
          } else if (status === "error" || status === "failed") {
            throw new Error("Document processing failed");
          }

          // Wait before next poll
          await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        } catch (error) {
          logError("[useAuditFile] Error polling document status:", error);
          throw error;
        }
      }

      throw new Error("Document processing timeout (60s exceeded)");
    },
    [],
  );

  /**
   * Upload file and wait for processing
   */
  const upload = useCallback(async (file: File): Promise<string> => {
    setState((prev) => ({
      ...prev,
      file,
      uploading: true,
      error: null,
      documentId: null,
      report: null,
    }));

    try {
      logDebug("[useAuditFile] Uploading file:", file.name);

      // Upload document
      const uploadResponse = await apiClient.uploadDocument(file, {
        onProgress: (progress) => {
          logDebug(`[useAuditFile] Upload progress: ${progress}%`);
        },
      });

      const documentId = uploadResponse.document_id || uploadResponse.doc_id;
      if (!documentId) {
        throw new Error("Upload response missing document_id");
      }

      logDebug("[useAuditFile] Document uploaded:", documentId);

      setState((prev) => ({
        ...prev,
        documentId,
        uploading: false,
      }));

      // NOTE: Backend processes document synchronously, so if upload succeeds,
      // the document is already ready (status="ready" in uploadResponse)
      // No need for polling - the upload endpoint waits for OCR to complete
      logDebug(
        "[useAuditFile] Document ready (from upload response):",
        documentId,
      );
      return documentId;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Upload failed";
      logError("[useAuditFile] Upload error:", error);

      setState((prev) => ({
        ...prev,
        uploading: false,
        error: errorMessage,
      }));

      throw error;
    }
  }, []);

  /**
   * Validate document with Copiloto Audit auditors
   */
  const validate = useCallback(
    async (
      clientName?: string,
      options: {
        enableDisclaimer?: boolean;
        enableFormat?: boolean;
        enableLogo?: boolean;
      } = {},
    ): Promise<ValidationReportResponse> => {
      if (!state.documentId) {
        throw new Error("No document uploaded. Call upload() first.");
      }

      setState((prev) => ({
        ...prev,
        validating: true,
        error: null,
        report: null,
      }));

      try {
        logDebug("[useAuditFile] Starting validation:", {
          documentId: state.documentId,
          clientName,
          options,
        });

        // Call validation endpoint
        const report = await apiClient.auditDocument(state.documentId, {
          clientName,
          ...options,
        });

        logDebug("[useAuditFile] Validation completed:", {
          jobId: report.job_id,
          status: report.status,
          totalFindings: report.summary.total_findings,
        });

        setState((prev) => ({
          ...prev,
          validating: false,
          report,
        }));

        return report;
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : "Validation failed";
        logError("[useAuditFile] Validation error:", error);

        setState((prev) => ({
          ...prev,
          validating: false,
          error: errorMessage,
        }));

        throw error;
      }
    },
    [state.documentId],
  );

  /**
   * Upload and validate in one step
   */
  const uploadAndValidate = useCallback(
    async (
      file: File,
      clientName?: string,
      options?: {
        enableDisclaimer?: boolean;
        enableFormat?: boolean;
        enableLogo?: boolean;
      },
    ): Promise<ValidationReportResponse> => {
      setState((prev) => ({
        ...prev,
        file,
        uploading: true,
        error: null,
        documentId: null,
        report: null,
      }));

      try {
        logDebug("[useAuditFile] Uploading file:", file.name);

        // Upload document
        const uploadResponse = await apiClient.uploadDocument(file, {
          onProgress: (progress) => {
            logDebug(`[useAuditFile] Upload progress: ${progress}%`);
          },
        });

        const documentId = uploadResponse.document_id || uploadResponse.doc_id;
        if (!documentId) {
          throw new Error("Upload response missing document_id");
        }

        logDebug("[useAuditFile] Document uploaded and ready:", documentId);

        setState((prev) => ({
          ...prev,
          documentId,
          uploading: false,
          validating: true,
        }));

        // Now validate with the documentId we just got
        logDebug("[useAuditFile] Starting validation:", {
          documentId,
          clientName,
          options,
        });

        const report = await apiClient.auditDocument(documentId, {
          clientName,
          ...options,
        });

        logDebug("[useAuditFile] Validation completed:", {
          jobId: report.job_id,
          status: report.status,
          totalFindings: report.summary.total_findings,
        });

        setState((prev) => ({
          ...prev,
          validating: false,
          report,
        }));

        return report;
      } catch (error) {
        const errorMessage =
          error instanceof Error
            ? error.message
            : "Upload or validation failed";
        logError("[useAuditFile] Upload/validation error:", error);

        setState((prev) => ({
          ...prev,
          uploading: false,
          validating: false,
          error: errorMessage,
        }));

        throw error;
      }
    },
    [],
  );

  /**
   * Reset state
   */
  const reset = useCallback(() => {
    setState(initialState);
  }, []);

  const auditFileInChat = useCallback(
    async (
      fileId: string,
      chatId: string,
      clientName: string,
    ): Promise<ChatMessageType> => {
      try {
        const auditResponse = await apiClient.auditFileInChat(
          fileId,
          chatId,
          clientName,
        );

        const responseMetadata = {
          ...(auditResponse.metadata ?? {}),
        } as Record<string, any>;

        if (
          auditResponse.validation_report_id &&
          !responseMetadata.validation_report_id
        ) {
          responseMetadata.validation_report_id =
            auditResponse.validation_report_id;
        }

        const rawStatus = auditResponse.status
          ? (auditResponse.status.toLowerCase() as ChatMessageStatus)
          : undefined;
        const allowedStatuses: ChatMessageStatus[] = [
          "sending",
          "streaming",
          "delivered",
          "error",
        ];
        const normalizedStatus: ChatMessageStatus =
          rawStatus && allowedStatuses.includes(rawStatus)
            ? rawStatus
            : "delivered";

        const chatMessage: ChatMessageType = {
          id: auditResponse.id,
          role: (auditResponse.role ?? "assistant") as ChatMessageType["role"],
          content: auditResponse.content ?? "",
          timestamp: auditResponse.created_at ?? new Date().toISOString(),
          status: normalizedStatus,
          model: auditResponse.model ?? undefined,
          tokens: auditResponse.tokens ?? undefined,
          latency: auditResponse.latency_ms ?? undefined,
          task_id: auditResponse.task_id ?? undefined,
          metadata: responseMetadata,
        };

        if (auditResponse.chat_id && auditResponse.chat_id !== chatId) {
          logWarn("Audit response chat_id mismatch", {
            expected: chatId,
            received: auditResponse.chat_id,
            message_id: auditResponse.id,
          });
        }

        return chatMessage;
      } catch (error) {
        logError("[useAuditFile] Audit in chat failed", { error });
        throw error;
      }
    },
    [],
  );

  return {
    // State
    file: state.file,
    uploading: state.uploading,
    validating: state.validating,
    error: state.error,
    documentId: state.documentId,
    report: state.report,
    isLoading: state.uploading || state.validating,

    // Actions
    upload,
    validate,
    uploadAndValidate,
    reset,
    auditFileInChat,
  };
}
