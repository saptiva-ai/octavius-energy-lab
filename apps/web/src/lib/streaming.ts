/**
 * Server-Sent Events (SSE) streaming utilities
 */

import { logDebug, logError } from "./logger";

export interface StreamEvent {
  event_type: string;
  task_id: string;
  timestamp: string;
  data: Record<string, any>;
  progress?: number;
}

export interface StreamOptions {
  onOpen?: () => void;
  onMessage?: (event: StreamEvent) => void;
  onError?: (error: Event) => void;
  onClose?: () => void;
  reconnect?: boolean;
  maxReconnectAttempts?: number;
  reconnectInterval?: number;
}

export class StreamingClient {
  private eventSource: EventSource | null = null;
  private url: string;
  private options: StreamOptions;
  private reconnectAttempts = 0;
  private isManuallyClosing = false;

  constructor(url: string, options: StreamOptions = {}) {
    this.url = url;
    this.options = {
      reconnect: true,
      maxReconnectAttempts: 5,
      reconnectInterval: 2000,
      ...options,
    };
  }

  connect(): void {
    if (
      this.eventSource &&
      this.eventSource.readyState !== EventSource.CLOSED
    ) {
      return; // Already connected
    }

    this.isManuallyClosing = false;

    try {
      if (typeof window !== "undefined") {
        this.eventSource = new EventSource(this.url);
      }

      if (this.eventSource) {
        this.eventSource.onopen = (event) => {
          logDebug("SSE connection opened:", this.url);
          this.reconnectAttempts = 0;
          this.options.onOpen?.();
        };

        this.eventSource.onmessage = (event) => {
          try {
            const streamEvent: StreamEvent = JSON.parse(event.data);
            this.options.onMessage?.(streamEvent);
          } catch (error) {
            logError("Error parsing SSE message:", error, event.data);
          }
        };

        this.eventSource.onerror = (event) => {
          logError("SSE error:", event);
          this.options.onError?.(event);

          // Handle reconnection
          if (this.options.reconnect && !this.isManuallyClosing) {
            this.handleReconnection();
          }
        };
      }
    } catch (error) {
      logError("Error creating EventSource:", error);
      this.options.onError?.(error as Event);
    }
  }

  private handleReconnection(): void {
    if (this.reconnectAttempts >= (this.options.maxReconnectAttempts || 5)) {
      logError("Max reconnection attempts reached");
      return;
    }

    this.reconnectAttempts++;
    const delay =
      this.options.reconnectInterval! *
      Math.pow(1.5, this.reconnectAttempts - 1);

    logDebug(
      `Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts})`,
    );

    setTimeout(() => {
      if (!this.isManuallyClosing) {
        this.close();
        this.connect();
      }
    }, delay);
  }

  close(): void {
    this.isManuallyClosing = true;
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.options.onClose?.();
  }

  getReadyState(): number {
    return this.eventSource?.readyState ?? EventSource.CLOSED;
  }

  isConnected(): boolean {
    return this.eventSource?.readyState === EventSource.OPEN;
  }
}

// Hook for React components to use streaming
import { useEffect, useRef, useCallback } from "react";

export function useStreaming(url: string | null, options: StreamOptions = {}) {
  const streamingClientRef = useRef<StreamingClient | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined);

  const connect = useCallback(() => {
    if (!url) return;

    // Close existing connection
    if (streamingClientRef.current) {
      streamingClientRef.current.close();
    }

    // Create new streaming client
    streamingClientRef.current = new StreamingClient(url, options);
    streamingClientRef.current.connect();
  }, [url, options]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    if (streamingClientRef.current) {
      streamingClientRef.current.close();
      streamingClientRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (url) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [url, connect, disconnect]);

  return {
    connect,
    disconnect,
    isConnected: streamingClientRef.current?.isConnected() ?? false,
    readyState:
      streamingClientRef.current?.getReadyState() ?? EventSource.CLOSED,
  };
}

// Utility to create streaming URL for a task
export function createStreamingUrl(taskId: string, baseUrl?: string): string {
  const base =
    baseUrl || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  return `${base}/api/stream/${taskId}`;
}

// Event type constants
export const STREAM_EVENTS = {
  CONNECTION_ESTABLISHED: "connection_established",
  TASK_STARTED: "task_started",
  SEARCH_STARTED: "search_started",
  SOURCES_FOUND: "sources_found",
  PROCESSING_SOURCES: "processing_sources",
  EVIDENCE_EXTRACTION: "evidence_extraction",
  SYNTHESIS_STARTED: "synthesis_started",
  TASK_COMPLETED: "task_completed",
  TASK_CANCELLED: "task_cancelled",
  STREAM_ERROR: "stream_error",
  STREAM_COMPLETED: "stream_completed",
} as const;

// Helper to format progress messages
export function formatProgressMessage(event: StreamEvent): string {
  const { event_type, data } = event;

  switch (event_type) {
    case STREAM_EVENTS.TASK_STARTED:
      return "Starting research task...";
    case STREAM_EVENTS.SEARCH_STARTED:
      return "Searching the web for relevant information...";
    case STREAM_EVENTS.SOURCES_FOUND:
      return `Found ${data.sources_count || "several"} relevant sources`;
    case STREAM_EVENTS.PROCESSING_SOURCES:
      return `Processing sources (${data.processed || 0}/${data.total || 0})`;
    case STREAM_EVENTS.EVIDENCE_EXTRACTION:
      return `Extracting evidence (${data.evidence_items || 0} items found)`;
    case STREAM_EVENTS.SYNTHESIS_STARTED:
      return "Synthesizing findings into comprehensive report...";
    case STREAM_EVENTS.TASK_COMPLETED:
      return "Research completed successfully!";
    case STREAM_EVENTS.TASK_CANCELLED:
      return "Research task was cancelled";
    case STREAM_EVENTS.STREAM_ERROR:
      return `Error: ${data.error || "Unknown error occurred"}`;
    default:
      return data.message || "Processing...";
  }
}

// Progress calculation helper
export function calculateProgress(event: StreamEvent): number {
  if (typeof event.progress === "number") {
    return Math.max(0, Math.min(1, event.progress));
  }

  // Fallback based on event type
  const progressMap: Record<string, number> = {
    [STREAM_EVENTS.CONNECTION_ESTABLISHED]: 0,
    [STREAM_EVENTS.TASK_STARTED]: 0.1,
    [STREAM_EVENTS.SEARCH_STARTED]: 0.2,
    [STREAM_EVENTS.SOURCES_FOUND]: 0.4,
    [STREAM_EVENTS.PROCESSING_SOURCES]: 0.6,
    [STREAM_EVENTS.EVIDENCE_EXTRACTION]: 0.8,
    [STREAM_EVENTS.SYNTHESIS_STARTED]: 0.9,
    [STREAM_EVENTS.TASK_COMPLETED]: 1.0,
  };

  return progressMap[event.event_type] || 0;
}
