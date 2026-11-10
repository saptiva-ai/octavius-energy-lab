/**
 * Contrato de `metadata` de los mensajes de chat.
 *
 * Antes: `{ [key: string]: any }` — todo acceso profundo colapsaba a `any`
 * (42 `as any` en el core del render). Ahora: slices opcionales TIPADOS +
 * index signature `unknown` (tolera campos no modelados pero FUERZA
 * narrowing) + helpers que centralizan la precedencia de fallbacks que antes
 * estaba copiada en cada call-site.
 */

import type { EstadoEspera } from "../espera-por-consulta";
import type { ToolInvocation } from "../types";
// Type-only import (leaf de tipos puros); candidato a mudarse aquí en F4/F5.
import type { ClarificationPayload } from "../../components/ClarificationPrompt/types";
import type { AnalyticsResponse } from "./analytics";
import { isAnalyticsResponse } from "./analytics";

// ---------------------------------------------------------------------------
// Auditoría (Copiloto Audit)
// ---------------------------------------------------------------------------

export interface AuditArtifactMeta {
  display_name?: string;
  filename?: string;
  report_pdf_url?: string;
  attachments?: unknown;
  [key: string]: unknown;
}

export interface AuditStats {
  critical: number;
  high: number;
  medium: number;
  low: number;
  total: number;
  [key: string]: unknown;
}

/** Artifact de reporte de auditoría (estructura de AuditReportResponse). */
export interface AuditArtifact {
  type?: string; // "audit_report_ui" | ausente en legacy
  doc_name?: string;
  stats?: AuditStats;
  categories?: Record<string, unknown>;
  actions?: unknown[];
  metadata?: AuditArtifactMeta;
  [key: string]: unknown;
}

export interface DecisionMetadata {
  audit_artifact?: AuditArtifact;
  report_pdf_url?: string;
  attachments?: unknown;
  validation_report_id?: string;
  warnings?: string[];
  docs_used?: number;
  docs_expired?: string[];
  [key: string]: unknown;
}

/** Metadata del mensaje de validación/auditoría (lo que MessageAuditCard pinta).
 * Requeridos solo los campos que el guard garantiza; el resto lo normaliza la card. */
export interface AuditReportMessageMetadata {
  validation_report_id: string;
  document_id: string;
  job_id?: string;
  status?: "completed" | "error";
  filename?: string;
  sample_findings?: unknown[];
  actions?: unknown[];
  error_message?: string;
  summary: {
    total_findings: number;
    findings_by_severity: Record<string, number>;
    findings_by_category?: Record<string, number>;
    disclaimer_coverage?: number;
    logo_detected?: boolean;
    total_pages: number;
    policy_id: string;
    policy_name: string;
    validation_duration_ms: number;
    fonts_used?: string[];
    colors_detected?: string[];
    grammar_issues?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Metadata del mensaje (slices opcionales; un mensaje puede combinar varios)
// ---------------------------------------------------------------------------

/** Metadata de archivo adjunta al mensaje del usuario (Files V1). */
export interface MessageFileMeta {
  file_id?: string;
  filename?: string;
  content_type?: string;
  mimetype?: string;
  bytes?: number;
  size?: number;
  pages?: number;
  [key: string]: unknown;
}

export interface ResearchTaskMetadata {
  id: string;
  status: string;
  progress?: number;
  created_at: string;
  updated_at: string;
  estimated_completion?: string;
  [key: string]: unknown;
}

export interface ChatMessageMetadata {
  latency_ms?: number;
  tool_invocations?: ToolInvocation[];
  research_task?: ResearchTaskMetadata;
  // Auditoría: el artifact puede venir en 3 slots según la época del backend
  artifact?: AuditArtifact;
  audit_artifact?: AuditArtifact;
  decision_metadata?: DecisionMetadata;
  validation_report_id?: string;
  document_id?: string;
  job_id?: string;
  filename?: string;
  report_pdf_url?: string;
  attachments?: unknown;
  // Archivos adjuntos del mensaje del usuario (Files V1)
  file_ids?: string[];
  files?: MessageFileMeta[];
  // Clarificación (el backend pide refinar una consulta ambigua)
  clarification_data?: ClarificationPayload;
  // Visualizaciones (canvas / retail): payload del chart adjunto al mensaje
  chart_data?: Record<string, unknown>;
  // AnalyticsResponse crudo del plugin de dominio (retail-advisor), adjunto
  // cuando la tool ejecutó en este turno (function-calling o pre-fetch).
  retail_analytics?: AnalyticsResponse;
  // Tool que eligió el decide mientras se prepara la respuesta (evento SSE
  // `status`); el indicador de espera cambia de tema con ella.
  espera?: EstadoEspera;
  // Campos no modelados: unknown (NUNCA any) — narrows obligatorio
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Helpers de precedencia (antes copiados con `as any` en cada call-site)
// ---------------------------------------------------------------------------

/** Artifact de auditoría: prop del mensaje > metadata.artifact > decision > slot directo. */
export function getAuditArtifact(
  artifact: AuditArtifact | undefined | null,
  metadata: ChatMessageMetadata | undefined,
): AuditArtifact | undefined {
  return (
    artifact ||
    metadata?.artifact ||
    metadata?.decision_metadata?.audit_artifact ||
    metadata?.audit_artifact ||
    undefined
  );
}

export function getAuditDisplayName(
  auditArtifact: AuditArtifact | undefined,
): string | undefined {
  return (
    auditArtifact?.metadata?.display_name ||
    auditArtifact?.metadata?.filename ||
    auditArtifact?.doc_name
  );
}

export function getAuditReportPdfUrl(
  auditArtifact: AuditArtifact | undefined,
  metadata: ChatMessageMetadata | undefined,
): string | undefined {
  return (
    auditArtifact?.metadata?.report_pdf_url ||
    metadata?.decision_metadata?.report_pdf_url ||
    metadata?.report_pdf_url
  );
}

export function getAuditAttachments(
  auditArtifact: AuditArtifact | undefined,
  metadata: ChatMessageMetadata | undefined,
): unknown {
  return (
    auditArtifact?.metadata?.attachments ??
    metadata?.decision_metadata?.attachments ??
    metadata?.attachments
  );
}

/** Guard: la metadata trae el reporte de auditoría completo para la card. */
export function isAuditReportMetadata(
  metadata: ChatMessageMetadata | undefined,
): metadata is ChatMessageMetadata & AuditReportMessageMetadata {
  return (
    !!metadata &&
    typeof metadata.validation_report_id === "string" &&
    typeof metadata.document_id === "string" &&
    typeof metadata.summary === "object" &&
    metadata.summary !== null
  );
}

export function hasChartData(
  metadata: ChatMessageMetadata | undefined,
): boolean {
  return !!metadata?.chart_data && typeof metadata.chart_data === "object";
}

/** AnalyticsResponse del plugin, si el mensaje trae uno válido y graficable.
 *
 * Además del guard estructural, filtra respuestas NO graficables: con `error`
 * o `chart_type: "none"` el canvas no debe abrirse (el backend normalmente no
 * las promueve a metadata, pero el frontend no debe confiarse del emisor).
 */
export function getRetailAnalytics(
  metadata: ChatMessageMetadata | undefined,
): AnalyticsResponse | undefined {
  const candidate = metadata?.retail_analytics;
  if (!isAnalyticsResponse(candidate)) return undefined;
  if (candidate.error || candidate.chart_type === "none") return undefined;
  return candidate;
}
