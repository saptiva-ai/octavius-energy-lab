/**
 * Fixtures del contrato retail `AnalyticsResponse` para e2e.
 *
 * Reemplaza a los borrados bank-chart-fixtures: aquél mockeaba el evento SSE
 * `bank_chart` que la app YA NO procesa; el contrato real viaja en
 * `metadata.retail_analytics` del payload `done` (ver ChatView →
 * getRetailAnalytics → canvas-store.openChart).
 */
import type { SSEEvent } from "./mock-sse";

const FIXED_CREATED_AT = "2026-02-09T00:00:00.000Z";

/** AnalyticsResponse mínimo VÁLIDO para isAnalyticsResponse (guard real). */
export function buildAnalyticsResponse(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    schema_version: "1",
    metric_name: "venta_hora",
    chart_type: "bar",
    series: [
      {
        name: "Venta por hora",
        points: [
          { label: "mundo_e", value: 2795, dimension: null },
          { label: "control", value: 2787, dimension: null },
        ],
      },
    ],
    table_data: [
      { label: "mundo_e", value: 2795, importe_pesos: 61785.3 },
      { label: "control", value: 2787, importe_pesos: 65509.7 },
    ],
    response_text:
      "Venta por hora: 2 puntos. Total del periodo: 5582 unidades.",
    grounding: {
      source: "retail-advisor",
      metric: "venta_hora",
      dimension: "tienda",
      period: "last_7_days",
      freshness: "intraday",
      data_as_of: "2026-07-07",
    },
    freshness: "intraday",
    data_as_of: "2026-07-07",
    ...overrides,
  };
}

export interface AnalyticsChatTurnParams {
  chatId: string;
  messageId: string;
  content?: string;
  analytics?: Record<string, unknown>;
}

/** Payload `done` como lo emite el backend (metadata.retail_analytics). */
export function buildAnalyticsDonePayload(params: AnalyticsChatTurnParams) {
  return {
    chat_id: params.chatId,
    message_id: params.messageId,
    content:
      params.content ??
      "Mundo E lleva 2,795 unidades esta semana, 8 más que la tienda control.",
    role: "assistant",
    model: "mock-model",
    created_at: FIXED_CREATED_AT,
    metadata: {
      retail_analytics: params.analytics ?? buildAnalyticsResponse(),
    },
  };
}

/** Secuencia SSE completa de un turno con respuesta analytics. */
export function buildAnalyticsSSEEvents(
  params: AnalyticsChatTurnParams,
): SSEEvent[] {
  const payload = buildAnalyticsDonePayload(params);
  return [
    {
      event: "meta",
      data: { chat_id: payload.chat_id, model: payload.model },
    },
    { event: "chunk", data: { content: payload.content } },
    { event: "done", data: payload },
  ];
}
