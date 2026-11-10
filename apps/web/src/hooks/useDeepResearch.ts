import { useCallback, useEffect, useRef, useState } from "react";
import { logWarn } from "@/lib/logger";

export type ResearchPhase =
  | "IDLE"
  | "PLAN"
  | "SEARCH"
  | "EVIDENCE"
  | "SYNTHESIS"
  | "REVIEW"
  | "COMPLETED"
  | "FAILED";

export interface ResearchSourceEvent {
  type: "source";
  id?: string;
  title?: string;
  url?: string;
  snippet?: string;
  relevance_score?: number;
  credibility_score?: number;
  [key: string]: unknown;
}

export interface ResearchEvidenceEvent {
  type: "evidence";
  id?: string;
  claim?: string;
  support_level?: "weak" | "mixed" | "strong";
  confidence?: number;
  source_id?: string;
  [key: string]: unknown;
}

export interface ResearchStateEvent {
  type: "state";
  state: ResearchPhase;
  progress?: number;
  message?: string;
  [key: string]: unknown;
}

export interface ResearchReportEvent {
  type: "report";
  summary?: string;
  tl_dr?: string;
  findings?: unknown;
  [key: string]: unknown;
}

export interface ResearchErrorEvent {
  type: "error";
  error: string;
  code?: string;
  [key: string]: unknown;
}

type ResearchStreamEvent =
  | ResearchStateEvent
  | ResearchSourceEvent
  | ResearchEvidenceEvent
  | ResearchReportEvent
  | ResearchErrorEvent
  | { type: "log"; message?: string; [key: string]: unknown };

interface UseDeepResearchResult {
  phase: ResearchPhase;
  progress: number;
  sources: ResearchSourceEvent[];
  evidences: ResearchEvidenceEvent[];
  report: ResearchReportEvent | null;
  error: ResearchErrorEvent | null;
  logs: string[];
  isStreaming: boolean;
  stop: () => void;
  reset: () => void;
}

const DEFAULT_PHASE: ResearchPhase = "IDLE";

export function useDeepResearch(streamUrl?: string): UseDeepResearchResult {
  const eventSourceRef = useRef<EventSource | null>(null);
  const [phase, setPhase] = useState<ResearchPhase>(DEFAULT_PHASE);
  const [progress, setProgress] = useState(0);
  const [sources, setSources] = useState<ResearchSourceEvent[]>([]);
  const [evidences, setEvidences] = useState<ResearchEvidenceEvent[]>([]);
  const [report, setReport] = useState<ResearchReportEvent | null>(null);
  const [error, setError] = useState<ResearchErrorEvent | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const closeStream = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setIsStreaming(false);
  }, []);

  const reset = useCallback(() => {
    closeStream();
    setPhase(DEFAULT_PHASE);
    setProgress(0);
    setSources([]);
    setEvidences([]);
    setReport(null);
    setError(null);
    setLogs([]);
  }, [closeStream]);

  useEffect(() => {
    if (!streamUrl) {
      reset();
      return undefined;
    }

    if (typeof window === "undefined") {
      return undefined;
    }

    // Reset previous data and open a new stream
    setPhase("PLAN");
    setProgress(0);
    setSources([]);
    setEvidences([]);
    setReport(null);
    setError(null);
    setLogs([]);

    const source = new EventSource(streamUrl);
    eventSourceRef.current = source;
    setIsStreaming(true);

    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as ResearchStreamEvent;

        switch (payload.type) {
          case "state": {
            const nextPhase = payload.state ?? DEFAULT_PHASE;
            setPhase(nextPhase);
            setProgress(
              typeof payload.progress === "number" ? payload.progress : 0,
            );
            if (payload.message) {
              setLogs((prev) =>
                [payload.message as string, ...prev].slice(0, 50),
              );
            }
            break;
          }
          case "source":
            setSources((prev) =>
              [payload as ResearchSourceEvent, ...prev].slice(0, 50),
            );
            break;
          case "evidence":
            setEvidences((prev) => [payload as ResearchEvidenceEvent, ...prev]);
            break;
          case "report":
            setReport(payload as ResearchReportEvent);
            setPhase("COMPLETED");
            setProgress(100);
            closeStream();
            break;
          case "log":
            if (payload.message) {
              setLogs((prev) =>
                [payload.message as string, ...prev].slice(0, 100),
              );
            }
            break;
          case "error":
            setError(payload as ResearchErrorEvent);
            setPhase("FAILED");
            closeStream();
            break;
          default:
            break;
        }
      } catch (err) {
        if (process.env.NODE_ENV !== "production") {
          // eslint-disable-next-line no-console
          logWarn("[useDeepResearch] invalid SSE payload", err);
        }
      }
    };

    source.onerror = () => {
      setError({ type: "error", error: "stream_error" });
      setPhase("FAILED");
      closeStream();
    };

    return () => {
      source.close();
      if (eventSourceRef.current === source) {
        eventSourceRef.current = null;
      }
      setIsStreaming(false);
    };
  }, [streamUrl, closeStream, reset]);

  const stop = useCallback(() => {
    closeStream();
    setPhase((current) => (current === "COMPLETED" ? current : "FAILED"));
  }, [closeStream]);

  return {
    phase,
    progress,
    sources,
    evidences,
    report,
    error,
    logs,
    isStreaming,
    stop,
    reset,
  };
}
