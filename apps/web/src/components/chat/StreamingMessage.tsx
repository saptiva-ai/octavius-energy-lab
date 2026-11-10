"use client";

import * as React from "react";
import { cn } from "../../lib/utils";
import { TypingIndicator, StreamingCursor } from "../ui/TypingIndicator";
import { MarkdownMessage } from "./MarkdownMessage";
import type { Espera } from "../../lib/espera-por-consulta";

interface StreamingMessageProps {
  content: string;
  isStreaming?: boolean;
  isComplete?: boolean;
  className?: string;
  /** Tema y frase del indicador mientras no hay texto. */
  espera?: Espera;
}

export function StreamingMessage({
  content,
  isStreaming = false,
  isComplete = false,
  className,
  espera,
}: StreamingMessageProps) {
  const [throttledContent, setThrottledContent] = React.useState(content);
  const lastUpdateRef = React.useRef<number>(0);
  const pendingContentRef = React.useRef<string>(content);

  // Throttle markdown re-renders during streaming to every 150ms
  // This provides smooth visual updates without excessive re-renders
  React.useEffect(() => {
    if (!isStreaming || isComplete) {
      // When streaming ends, immediately show final content
      setThrottledContent(content);
      return;
    }

    pendingContentRef.current = content;
    const now = Date.now();
    const timeSinceLastUpdate = now - lastUpdateRef.current;

    if (timeSinceLastUpdate >= 150) {
      // Update immediately if 150ms have passed
      setThrottledContent(content);
      lastUpdateRef.current = now;
    } else {
      // Schedule update for remaining time
      const timeout = setTimeout(() => {
        setThrottledContent(pendingContentRef.current);
        lastUpdateRef.current = Date.now();
      }, 150 - timeSinceLastUpdate);

      return () => clearTimeout(timeout);
    }
  }, [content, isStreaming, isComplete]);

  const showCursor = isStreaming && !isComplete && content.length > 0;

  // Mostrar typing indicator si no hay contenido aún
  if (isStreaming && content.length === 0) {
    return (
      <div className={cn("flex", className)}>
        <TypingIndicator size="md" espera={espera} />
      </div>
    );
  }

  return (
    <div className={cn("relative", className)}>
      {/* Renderizar Markdown progresivamente durante el streaming con throttle */}
      <MarkdownMessage
        content={throttledContent}
        highlightCode={!isStreaming}
        skipSqlStripping={isStreaming} // BA-003: Only strip SQL after streaming completes
      />
      {/* Cursor de streaming */}
      {showCursor && (
        <div className="pointer-events-none absolute bottom-0 left-full ml-2 translate-y-1/4">
          <StreamingCursor />
        </div>
      )}
    </div>
  );
}

export function MessageSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("animate-pulse space-y-2", className)}>
      <div className="h-4 bg-surface rounded w-3/4"></div>
      <div className="h-4 bg-surface rounded w-1/2"></div>
      <div className="h-4 bg-surface rounded w-2/3"></div>
    </div>
  );
}
