"use client";

import * as React from "react";
import { cn, formatRelativeTime, copyToClipboard } from "../../lib/utils";
import { logDebug } from "../../lib/logger";
import { Button, Badge } from "../ui";
import { StreamingMessage } from "./StreamingMessage";
import { FileReviewMessage } from "./FileReviewMessage";
import { MessageAuditCard } from "./MessageAuditCard";
import { PreviewAttachment } from "./PreviewAttachment";
import { featureFlags } from "../../lib/feature-flags";
import type {
  ChatMessage as ChatMessageType,
  ChatMessageKind,
  FileReviewData,
} from "../../lib/types";
import type { AuditReportResponse, ToolInvocation } from "@/lib/types";
import type { AuditArtifact, ChatMessageMetadata } from "@/lib/contracts";
import {
  getAuditArtifact,
  getAuditAttachments,
  getAuditDisplayName,
  getAuditReportPdfUrl,
  getRetailAnalytics,
  isAuditReportMetadata,
} from "@/lib/contracts";
import { analyticsResponseToChartData } from "@/lib/charts/analytics-to-chart-data";
import { esperaDeConsulta } from "@/lib/espera-por-consulta";
import type { FileAttachment } from "../../types/files";
import { ArtifactCard } from "./artifact-card";
import { parseToolCalls } from "../../lib/tool-parser";
import { AuditSummaryCard } from "./artifacts/AuditSummaryCard";
import { MessageFeedback } from "./MessageFeedback";
import { ClarificationPrompt } from "../ClarificationPrompt";
import { useCanvasStore } from "@/lib/stores/canvas-store";

export interface ChatMessageProps {
  id?: string;
  role: "user" | "assistant" | "system";
  kind?: ChatMessageKind;
  content: string;
  timestamp?: Date | string;
  model?: string;
  status?: "sending" | "delivered" | "error" | "streaming";
  tokens?: number;
  latencyMs?: number;
  isStreaming?: boolean;
  task_id?: string;
  metadata?: ChatMessageMetadata;
  review?: FileReviewData;
  onCopy?: (text: string) => void;
  onRetry?: (messageId: string) => void;
  onRegenerate?: (messageId: string) => void;
  onStop?: () => void;
  onViewReport?: (taskId: string, taskTitle: string) => void;
  onViewAuditReport?: (
    validationReportId: string,
    documentId: string,
    filename?: string,
  ) => void;
  onReAuditDocument?: (
    documentId: string,
    jobId?: string,
    filename?: string,
  ) => void;
  onSendMessage?: (message: string) => void;
  className?: string;
  // Additional props for UX-005
  isError?: boolean;
  latency?: number;
  artifact?: AuditArtifact | null;
  // Message feedback props
  conversationId?: string;
  onFeedback?: (
    messageId: string,
    rating: "up" | "down",
    reason?: string,
  ) => Promise<void>;
}

export function ChatMessage({
  id,
  role,
  kind,
  content,
  timestamp,
  model,
  status = "delivered",
  tokens,
  latencyMs,
  isStreaming = false,
  task_id,
  metadata,
  review,
  onCopy,
  onRetry,
  onRegenerate,
  onStop,
  onViewReport,
  onViewAuditReport,
  onReAuditDocument,
  onSendMessage,
  className,
  isError = false,
  latency,
  artifact,
  conversationId,
  onFeedback,
}: ChatMessageProps) {
  const [copied, setCopied] = React.useState(false);

  // 🆕 Canvas highlight synchronization (Phase 2)
  const activeMessageId = useCanvasStore((state) => state.activeMessageId);
  const isActiveInCanvas = activeMessageId === id;
  const canvasAbierto = useCanvasStore((state) => state.isSidebarOpen);

  // La gráfica de esta respuesta vive en `metadata.retail_analytics` y se
  // abre sola al llegar; cerrada con la X no había cómo volver a verla
  // (Equipo, 2026-10-21). El botón la vuelve a abrir, también en respuestas
  // anteriores.
  const graficaDelMensaje = React.useMemo(
    () => (role === "assistant" ? getRetailAnalytics(metadata) : undefined),
    [role, metadata],
  );
  const verGrafica = React.useCallback(() => {
    if (!graficaDelMensaje) return;
    useCanvasStore
      .getState()
      .openChart(
        analyticsResponseToChartData(graficaDelMensaje),
        id || "temp",
        id || "",
      );
  }, [graficaDelMensaje, id]);

  const isFileReview = kind === "file-review";

  const isUser = role === "user";
  const isSystem = role === "system";
  const isAssistant = role === "assistant";
  // Respuesta en camino sin un solo carácter aún: la burbuja muestra el
  // indicador compacto (Equipo, 2026-10-21).
  const esperando = isAssistant && isStreaming && content.length === 0;
  const espera = React.useMemo(
    () => (esperando ? esperaDeConsulta(metadata?.espera) : undefined),
    [esperando, metadata?.espera],
  );

  // Parse inline tool calls from content
  const { content: displayContent, toolInvocations: inlineToolInvocations } =
    React.useMemo(() => parseToolCalls(content), [content]);

  const toolInvocations = React.useMemo(() => {
    const metadataTools = metadata?.tool_invocations ?? [];
    return [...metadataTools, ...inlineToolInvocations];
  }, [metadata, inlineToolInvocations]);

  const artifactInvocations = React.useMemo(() => {
    const seen = new Set<string>();

    return toolInvocations.filter((inv) => {
      if (
        !inv ||
        typeof inv !== "object" ||
        inv.tool_name !== "create_artifact" ||
        !inv.result?.id
      ) {
        return false;
      }

      // Deduplicate repeated tool invocations coming from metadata + inline content.
      const artifactId = String(inv.result.id);
      const artifactType = String(inv.result.type || "");
      const dedupeKey = `${artifactId}:${artifactType}`;

      if (seen.has(dedupeKey)) {
        return false;
      }

      seen.add(dedupeKey);
      return true;
    });
  }, [toolInvocations]);

  React.useEffect(() => {
    if (isUser) {
      logDebug("[ChatMessage] Rendering user message", {
        id,
        hasMetadata: !!metadata,
        metadata,
        file_ids: metadata?.file_ids,
        files: metadata?.files,
        shouldShowIndicator: !!(
          metadata?.file_ids && metadata.file_ids.length > 0
        ),
      });
    }
  }, [isUser, metadata, id]);

  // Render file review message if kind === 'file-review'
  if (isFileReview) {
    const message: ChatMessageType = {
      id: id || "",
      role,
      kind,
      content,
      timestamp: timestamp || new Date(),
      review,
    };
    return <FileReviewMessage message={message} />;
  }

  // Identify audit messages to append inline audit card after content
  const isAuditMessage =
    featureFlags.auditInline &&
    metadata &&
    typeof metadata === "object" &&
    "validation_report_id" in metadata &&
    metadata.validation_report_id;

  // Precedencia centralizada en el contrato (antes: fallbacks con `as any`)
  const auditArtifact = getAuditArtifact(artifact, metadata);
  const auditDisplayName = getAuditDisplayName(auditArtifact);

  const handleCopy = async () => {
    const success = await copyToClipboard(displayContent);
    if (success) {
      setCopied(true);
      onCopy?.(displayContent);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const getStatusBadge = () => {
    switch (status) {
      case "sending":
        return (
          <Badge variant="info" size="sm">
            Enviando...
          </Badge>
        );
      case "streaming":
        return null; // TypingIndicator already shows this in StreamingMessage
      case "error":
        return (
          <Badge variant="error" size="sm">
            Error
          </Badge>
        );
      default:
        return null;
    }
  };

  if (isSystem) {
    return (
      <div className="flex justify-center my-4">
        <div className="bg-gray-100 text-gray-600 px-3 py-1 rounded-full text-sm">
          {displayContent}
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group flex gap-3 px-4 py-6 transition-colors duration-150",
        isUser ? "flex-row-reverse" : "flex-row",
        "hover:bg-surface-2/50",
        className,
      )}
      role="article"
      aria-label={`${isUser ? "Mensaje del usuario" : "Respuesta del asistente"} - ${formatRelativeTime(timestamp || new Date())}`}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-medium uppercase",
          isUser ? "bg-primary/20 text-primary" : "bg-muted/20 text-muted",
        )}
      >
        {isUser ? "Tú" : "AI"}
      </div>

      {/* Message content */}
      {/*
        LAYOUT FIX: Flex child with min-w-0 to allow shrinking below content size
        This prevents code blocks from pushing the message container wider than available space
      */}
      <div
        className={cn("flex-1 min-w-0", isUser ? "text-right" : "text-left")}
      >
        {/* Removed: Header with "Usuario Just now" and "Saptiva Turbo Just now" for minimal UI */}

        {/* File attachments thumbnails ABOVE user message */}
        {isUser && metadata?.files && metadata.files.length > 0 && (
          <div
            className={cn(
              "mb-3 flex gap-2",
              isUser ? "justify-end" : "justify-start",
            )}
          >
            {metadata.files.map((file, index) => {
              // Convert file metadata to FileAttachment format
              const attachment: FileAttachment = {
                file_id: file.file_id || `file-${index}`,
                filename: file.filename || `Archivo ${index + 1}`,
                mimetype:
                  file.content_type ||
                  file.mimetype ||
                  "application/octet-stream",
                bytes: file.bytes || file.size || 0,
                pages: file.pages,
                status: "READY",
              };

              return (
                <PreviewAttachment
                  key={attachment.file_id}
                  attachment={attachment}
                  className="w-32 h-48"
                  showAuditButton={false}
                />
              );
            })}
          </div>
        )}

        {/*
          LAYOUT FIX: Message bubble container
          - Changed inline-flex → flex to establish proper block-level flex container
          - Kept max-w-full to respect parent boundaries
          - Added w-full to ensure bubble takes available width and can constrain children
          - This prevents code blocks from escaping the bubble
        */}
        <div
          className={cn(
            "flex max-w-full flex-col rounded-3xl text-left text-sm leading-relaxed",
            // Mientras se prepara la respuesta, una burbuja compacta y verde
            // con el indicador, no una caja gris de todo el ancho.
            esperando
              ? "w-fit bg-primary/10 px-5 py-3"
              : "w-full px-5 py-4",
            !esperando &&
              (isUser
                ? "bg-primary/15 text-foreground"
                : "bg-surface text-foreground"),
            isError && "bg-danger/5",
          )}
          style={
            isUser || esperando
              ? {
                  boxShadow:
                    "inset 0 0 0 0.5px rgba(73, 247, 217, 0.4), 0 0 12px rgba(73, 247, 217, 0.15)",
                }
              : {
                  boxShadow: "inset 0 0 0 0.5px var(--hairline)",
                }
          }
          role="region"
          aria-label="Contenido del mensaje"
        >
          <div
            className={cn(
              "min-w-0 break-words",
              !isAssistant && "whitespace-pre-wrap",
            )}
          >
            {isAssistant ? (
              <StreamingMessage
                content={displayContent}
                isStreaming={isStreaming}
                isComplete={status === "delivered"}
                espera={espera}
              />
            ) : (
              displayContent
            )}
          </div>
        </div>

        {/* Inline audit card after the assistant's summary */}
        {isAssistant && isAuditMessage && isAuditReportMetadata(metadata) && (
          <div className="mt-3">
            <MessageAuditCard
              metadata={metadata}
              onViewFull={() =>
                onViewAuditReport?.(
                  metadata.validation_report_id,
                  metadata.document_id,
                  metadata.filename,
                )
              }
              onReAudit={() =>
                onReAuditDocument?.(
                  metadata.document_id,
                  metadata.job_id,
                  metadata.filename,
                )
              }
            />
          </div>
        )}

        {/* Structured audit summary card when artifact is present */}
        {isAssistant &&
          auditArtifact &&
          (auditArtifact.type === "audit_report_ui" || !auditArtifact.type) && (
            <div className="mt-3">
              <AuditSummaryCard
                data={{
                  // Use artifact root directly (it now has complete AuditReportResponse structure)
                  doc_name: auditArtifact.doc_name || "",
                  stats: auditArtifact.stats || {
                    critical: 0,
                    high: 0,
                    medium: 0,
                    low: 0,
                    total: 0,
                  },
                  // Boundary cast a los tipos NOMBRADOS del backend: el artifact
                  // ES un AuditReportResponse serializado (contrato del auditor).
                  categories: (auditArtifact.categories ??
                    {}) as AuditReportResponse["categories"],
                  actions: (auditArtifact.actions ??
                    []) as AuditReportResponse["actions"],
                  metadata: {
                    ...(auditArtifact.metadata || {}),
                    // Precedencia PDF/attachments centralizada en el contrato
                    report_pdf_url: getAuditReportPdfUrl(
                      auditArtifact,
                      metadata,
                    ),
                    attachments: getAuditAttachments(auditArtifact, metadata),
                    display_name: auditDisplayName,
                  },
                }}
                className={cn(isUser ? "ml-auto max-w-lg" : "max-w-lg")}
              />
            </div>
          )}

        {/* Clarification UI: shown when the backend asks the user to refine an
            ambiguous query. Generic mechanism, populated via metadata. */}
        {isAssistant && metadata?.clarification_data && (
          <ClarificationPrompt
            payload={metadata.clarification_data}
            onResolve={(selections) => {
              if (onSendMessage) {
                // Quick path: related query button
                if (selections.quick_query) {
                  onSendMessage(selections.quick_query);
                  return;
                }

                // Build a refined query based on selections
                const originalQuery =
                  metadata?.clarification_data?.original_query || content;

                // Extract labels for natural language query reconstruction
                const selectionLabels = Object.entries(selections).map(
                  ([field, value]) => {
                    const fieldData = (
                      metadata.clarification_data?.clarifications ?? []
                    ).find((c) => c.field === field);
                    const option = fieldData?.options.find(
                      (o) => o.value === value,
                    );
                    return option?.label || value;
                  },
                );

                const refinedQuery = `${originalQuery} (${selectionLabels.join(", ")})`;
                onSendMessage(refinedQuery);
              }
            }}
          />
        )}

        {graficaDelMensaje && !isStreaming && (
          <button
            type="button"
            onClick={verGrafica}
            aria-pressed={isActiveInCanvas && canvasAbierto}
            className={cn(
              "mt-2 inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
              isActiveInCanvas && canvasAbierto
                ? "border-primary/50 bg-primary/15 text-foreground"
                : "border-border bg-surface text-muted hover:border-primary/40 hover:text-foreground",
            )}
          >
            <svg
              aria-hidden="true"
              className="h-3.5 w-3.5 shrink-0 text-primary"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <rect x="2" y="10" width="3.5" height="8" rx="1" />
              <rect x="8.25" y="5" width="3.5" height="13" rx="1" />
              <rect x="14.5" y="2" width="3.5" height="16" rx="1" />
            </svg>
            <span className="shrink-0">Ver gráfica</span>
            <span className="truncate text-muted">
              {graficaDelMensaje.visualization?.headline ??
                graficaDelMensaje.visualization?.title ??
                graficaDelMensaje.metric_name}
            </span>
          </button>
        )}

        {/* Artifact cards should appear after the assistant's summary (and audit card) */}
        {artifactInvocations.length > 0 && (
          <div
            className={cn(
              "mt-3 flex flex-col gap-2",
              isUser ? "items-end" : "items-start",
            )}
          >
            {artifactInvocations.map((inv) => {
              const artifactId = (inv.result?.id as string) || "";
              const artifactType = (inv.result?.type as string) || "markdown";

              return (
                <ArtifactCard
                  key={artifactId || inv.tool_name}
                  id={artifactId}
                  title={(inv.result?.title as string) || "Artefacto"}
                  type={artifactType}
                />
              );
            })}
          </div>
        )}

        {/* Removed: Footer with "XXX tokens Saptiva Turbo" for minimal UI */}
        {/* Only show error retry button */}
        {status === "error" && onRetry && id && (
          <div
            className={cn(
              "mt-2 flex items-center",
              isUser ? "justify-end" : "justify-start",
            )}
          >
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onRetry(id)}
              className="px-2 text-xs font-medium text-danger hover:text-danger/80"
            >
              Reintentar
            </Button>
          </div>
        )}

        {/* Actions (visible on hover or when streaming) - UX-005 */}
        <div
          className={cn(
            "mt-2 flex items-center gap-1 transition-opacity duration-150",
            // focus-within: el cuadro de feedback no desaparece mientras se
            // escribe (feedback de QA, 2026-10-16, punto 12).
            isStreaming
              ? "opacity-100"
              : "opacity-0 group-hover:opacity-100 focus-within:opacity-100",
            isUser ? "justify-end" : "justify-start",
          )}
        >
          {/* Detener vive en el compositor: aquí se repetía como "STOP"
              (Equipo, 2026-10-21). */}

          {/* Copy button */}
          {!isStreaming && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCopy}
              className="px-2 text-xs font-bold uppercase tracking-wide text-muted hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-1 focus-visible:ring-offset-surface"
              aria-label={
                copied ? "Texto copiado al portapapeles" : "Copiar mensaje"
              }
            >
              {copied ? (
                <>
                  <svg
                    className="h-3 w-3 mr-1"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                  Copiado
                </>
              ) : (
                <>
                  <svg
                    className="h-3 w-3 mr-1"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                    />
                  </svg>
                  Copy
                </>
              )}
            </Button>
          )}

          {/* Regenerate button for assistant messages */}
          {isAssistant && !isStreaming && onRegenerate && id && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onRegenerate(id)}
              className="px-2 text-xs font-bold uppercase tracking-wide text-muted hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-1 focus-visible:ring-offset-surface"
              aria-label="Regenerar respuesta"
            >
              <svg
                className="h-3 w-3 mr-1"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              Regenerate
            </Button>
          )}

          {/* Research report button */}
          {task_id &&
            metadata?.research_task &&
            onViewReport &&
            !isStreaming && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  onViewReport(task_id, displayContent.slice(0, 50) + "...")
                }
                className="px-2 text-xs font-bold uppercase tracking-wide text-muted hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-1 focus-visible:ring-offset-surface"
                aria-label={`Ver reporte de investigación: ${metadata?.research_task?.status}`}
              >
                <svg
                  className="h-3 w-3 mr-1"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
                Report ({metadata.research_task.status})
              </Button>
            )}

          {/* Message Feedback - only for assistant messages that are not streaming */}
          {isAssistant && !isStreaming && id && onFeedback && (
            <MessageFeedback
              messageId={id}
              conversationId={conversationId}
              onFeedback={onFeedback}
            />
          )}
        </div>
      </div>
    </div>
  );
}
