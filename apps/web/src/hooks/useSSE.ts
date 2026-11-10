/**
 * useSSE - Hook for Server-Sent Events (SSE) connection
 *
 * Manages EventSource connection for real-time review progress updates
 * Integrates with chat store to update file review messages
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { useChatStore } from "../lib/stores/chat-store";
import { logDebug, logError } from "../lib/logger";
import type { ReviewStage } from "../lib/types";

export interface SSEEvent {
  jobId: string;
  status: string;
  progress: number;
  currentStage?: string;
  message?: string;
  timestamp: string;
  phase?: string;
  traceId?: string;
  errorCode?: string;
}

export interface UseSSEReturn {
  isConnected: boolean;
  lastEvent: SSEEvent | null;
  error: string | null;
  reconnect: () => void;
  disconnect: () => void;
}

export function useSSE(
  jobId: string | null,
  docId: string | null,
  enabled: boolean = true,
): UseSSEReturn {
  const { findFileReviewMessage, updateFileReviewMessage } = useChatStore();
  const eventSourceRef = useRef<EventSource | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null);
  const [error, setError] = useState<string | null>(null);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      setIsConnected(false);
    }
  }, []);

  const connect = useCallback(() => {
    if (!jobId || !enabled) return;

    // Close existing connection
    disconnect();

    try {
      const traceId = crypto.randomUUID();

      const parseAndApply = (raw: any, statusOverride?: string) => {
        const normalizedStatus =
          statusOverride ?? raw.status ?? raw.phase ?? "processing";
        const progress =
          typeof raw.pct === "number" ? raw.pct : (raw.progress ?? 0);

        const payload: SSEEvent = {
          jobId: raw.file_id ?? raw.job_id ?? jobId,
          status: String(normalizedStatus).toUpperCase(),
          progress,
          currentStage: raw.current_stage,
          message: raw.message,
          timestamp: raw.timestamp ?? new Date().toISOString(),
          phase: raw.phase,
          traceId: raw.trace_id,
          errorCode: raw.error?.code,
        };

        setLastEvent(payload);
        logDebug("[SSE] Status update", payload);

        if (docId) {
          const message = findFileReviewMessage(docId);
          if (message) {
            const newStages = [...(message.review?.stages || [])];
            if (
              payload.status &&
              !newStages.includes(payload.status as ReviewStage)
            ) {
              newStages.push(payload.status as ReviewStage);
            }

            let fileStatus:
              | "uploading"
              | "uploaded"
              | "processing"
              | "ready"
              | "reviewing"
              | "completed"
              | "error" = "processing";
            if (payload.status === "FAILED") {
              fileStatus = "error";
            } else if (
              payload.status === "READY" ||
              payload.status === "COMPLETE"
            ) {
              fileStatus = "uploaded";
            }

            updateFileReviewMessage(message.id, {
              jobId: payload.jobId,
              stages: newStages,
              status: fileStatus,
              progress: payload.progress,
              currentStage: payload.phase || payload.currentStage,
              errors: payload.errorCode
                ? [payload.errorCode]
                : raw.message
                  ? [raw.message]
                  : undefined,
            });
          }
        }

        if (payload.status === "READY" || payload.status === "FAILED") {
          setTimeout(() => disconnect(), 1000);
        }
      };

      const connectEventSource = (endpoint: string) =>
        new EventSource(endpoint, { withCredentials: true });

      let eventSource: EventSource | null = null;

      const openStream = (endpoint: string, allowFallback = true) => {
        try {
          eventSource = connectEventSource(endpoint);
        } catch (err: any) {
          if (allowFallback) {
            openStream(
              `/api/review/events/${jobId}?t=${encodeURIComponent(traceId)}`,
              false,
            );
          } else {
            throw err;
          }
          return;
        }

        eventSource!.onopen = () => {
          setIsConnected(true);
          setError(null);
          logDebug("[SSE] Connected", { jobId, endpoint });
        };

        eventSource!.addEventListener("meta", (event) => {
          try {
            const data = JSON.parse(event.data);
            logDebug("[SSE] Meta event", data);
          } catch (err) {
            logError("[SSE] Failed to parse meta event", err);
          }
        });

        const eventNames = ["status", "progress", "ready", "failed"];
        for (const name of eventNames) {
          eventSource!.addEventListener(name, (event) => {
            try {
              const data = JSON.parse(event.data);
              parseAndApply(
                data,
                name === "ready"
                  ? "READY"
                  : name === "failed"
                    ? "FAILED"
                    : undefined,
              );
            } catch (err) {
              logError(`[SSE] Failed to parse ${name} event`, err);
            }
          });
        }

        eventSource!.onerror = (err) => {
          logError("[SSE] Connection error", err);
          if (allowFallback) {
            disconnect();
            openStream(
              `/api/review/events/${jobId}?t=${encodeURIComponent(traceId)}`,
              false,
            );
            return;
          }

          setError("Connection lost");
          setIsConnected(false);
          disconnect();
        };

        eventSourceRef.current = eventSource!;
      };

      openStream(`/api/files/events/${jobId}?t=${encodeURIComponent(traceId)}`);
    } catch (err: any) {
      setError(err.message || "Failed to connect");
      logError("[SSE] Failed to create EventSource", err);
    }
  }, [
    jobId,
    enabled,
    disconnect,
    docId,
    findFileReviewMessage,
    updateFileReviewMessage,
  ]);

  const reconnect = useCallback(() => {
    disconnect();
    setTimeout(connect, 100);
  }, [disconnect, connect]);

  // Connect/disconnect based on jobId and enabled
  useEffect(() => {
    if (jobId && enabled) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [jobId, enabled, connect, disconnect]);

  return {
    isConnected,
    lastEvent,
    error,
    reconnect,
    disconnect,
  };
}
