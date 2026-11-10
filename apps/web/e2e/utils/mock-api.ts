/**
 * Backend API mocking utilities for Playwright E2E tests.
 *
 * All mocks use page.route() to intercept requests at the network level,
 * ensuring tests never hit a real backend.
 */
import type { Page } from "@playwright/test";

import { createSSEResponse, sseHeaders, type SSEEvent } from "./mock-sse";
import {
  testConversations,
  testMessages,
  testSSEChunks,
  testTokens,
  testUser,
} from "./test-data";

// ---------------------------------------------------------------------------
// Auth mocks
// ---------------------------------------------------------------------------

/** Mock a successful login response. */
export async function mockLogin(page: Page): Promise<void> {
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...testTokens,
        user: testUser,
      }),
    }),
  );
}

/** Mock a failed login (bad credentials). */
export async function mockLoginFailure(page: Page): Promise<void> {
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({
        detail: {
          type: "auth_error",
          title: "Authentication Failed",
          status: 401,
          detail: "Correo o contraseña incorrectos.",
          code: "BAD_CREDENTIALS",
        },
      }),
    }),
  );
}

/** Mock the /auth/me endpoint. */
export async function mockMe(page: Page): Promise<void> {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(testUser),
    }),
  );
}

/** Mock a successful logout. */
export async function mockLogout(page: Page): Promise<void> {
  await page.route("**/api/auth/logout", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ message: "Logged out" }),
    }),
  );
}

/** Mock token refresh. */
export async function mockRefresh(page: Page): Promise<void> {
  await page.route("**/api/auth/refresh", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "refreshed-token-abc",
        expires_in: 3600,
      }),
    }),
  );
}

// ---------------------------------------------------------------------------
// Chat mocks
// ---------------------------------------------------------------------------

type ChatRequestBody = Record<string, unknown> | undefined;

interface ChatScenarioContext {
  message: string;
  body: ChatRequestBody;
  requestIndex: number;
}

type ChatScenarioMatcher =
  | RegExp
  | ((message: string, body: ChatRequestBody) => boolean);

type ChatScenarioEvents =
  | SSEEvent[]
  | ((context: ChatScenarioContext) => SSEEvent[]);

export interface ChatStreamScenario {
  name: string;
  matcher: ChatScenarioMatcher;
  events: ChatScenarioEvents;
}

function extractMessageFromBody(body: ChatRequestBody): string {
  if (!body) return "";
  const maybeMessage = body.message;
  return typeof maybeMessage === "string" ? maybeMessage : "";
}

function matchesScenario(
  matcher: ChatScenarioMatcher,
  message: string,
  body: ChatRequestBody,
): boolean {
  if (matcher instanceof RegExp) {
    return matcher.test(message);
  }
  return matcher(message, body);
}

/** Mock a streaming chat response with custom SSE chunks. */
export async function mockChatStream(
  page: Page,
  chunks?: SSEEvent[],
): Promise<void> {
  const body = createSSEResponse(chunks ?? testSSEChunks);
  // Predicado de URL (no glob): el glob "**/api/chat" no interceptaba el
  // fetch real y los requests llegaban al backend vivo (specs pasaban en
  // falso o fallaban con respuestas del LLM real).
  await page.route(
    (url) => url.pathname === "/api/chat" || url.pathname.endsWith("/api/chat"),
    (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 200,
          headers: sseHeaders(),
          body,
        });
      }
      return route.fallback();
    },
  );
}

/**
 * Mock /api/chat with semantic query routing.
 *
 * Useful for multi-turn tests where each query should return different
 * artifacts based on user intent instead of brittle request order.
 */
export async function mockChatStreamByQuery(
  page: Page,
  scenarios: ChatStreamScenario[],
  options?: { defaultEvents?: SSEEvent[]; unmatchedStatus?: number },
): Promise<void> {
  await page.unroute("**/api/chat").catch(() => undefined);
  let requestIndex = 0;

  await page.route("**/api/chat", async (route) => {
    if (route.request().method() !== "POST") {
      return route.fallback();
    }

    requestIndex += 1;

    let body: ChatRequestBody;
    try {
      body = route.request().postDataJSON() as ChatRequestBody;
    } catch {
      body = undefined;
    }
    const message = extractMessageFromBody(body);
    const scenario = scenarios.find((candidate) =>
      matchesScenario(candidate.matcher, message, body),
    );

    if (!scenario && !options?.defaultEvents) {
      return route.fulfill({
        status: options?.unmatchedStatus ?? 422,
        contentType: "application/json",
        body: JSON.stringify({
          detail: `No mock scenario matched message: ${message || "<empty>"}`,
        }),
      });
    }

    const selectedEvents = scenario
      ? typeof scenario.events === "function"
        ? scenario.events({ message, body, requestIndex })
        : scenario.events
      : (options?.defaultEvents ?? []);

    return route.fulfill({
      status: 200,
      headers: sseHeaders(),
      body: createSSEResponse(selectedEvents),
    });
  });
}

/** Mock conversation sessions list. */
export async function mockConversations(
  page: Page,
  conversations?: typeof testConversations,
): Promise<void> {
  const sessions = conversations ?? testConversations;
  await page.route("**/api/sessions*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        sessions,
        total: sessions.length,
      }),
    }),
  );
}

/** Mock conversation creation (POST /api/conversations).
 *
 * Sin esto el flujo de "primer mensaje" crea conversaciones en el backend
 * REAL y los specs dejan de ser herméticos (flaky en corridas consecutivas).
 */
export async function mockCreateConversation(
  page: Page,
  id = "conv-e2e-1",
): Promise<void> {
  await page.route(
    (url) => url.pathname.endsWith("/api/conversations"),
    (route) => {
      if (route.request().method() !== "POST") {
        return route.fallback();
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id,
          title: "Nueva conversación",
          created_at: "2026-02-09T00:00:00.000Z",
          updated_at: "2026-02-09T00:00:00.000Z",
          message_count: 0,
          model: "SAPTIVA_CORTEX",
          tools_enabled: { create_artifact: true },
          state: "draft",
        }),
      });
    },
  );
}

// Mock session detail/update (GET/PATCH/PUT /api/sessions/:id).
//
// El glob de mockConversations (asterisco simple) NO cruza "/" — el
// auto-title del chat hace PATCH a /api/sessions/<id>, iba al backend REAL
// con token de mentira → 401 → Auto-logout que limpiaba TODO el estado del
// chat a media prueba (la "race" de mensajes que desaparecían era esto).
export async function mockSessionDetail(page: Page): Promise<void> {
  await page.route(
    (url) => /\/api\/sessions\/[^/?]+$/.test(url.pathname),
    (route) => {
      const id = new URL(route.request().url()).pathname.split("/").pop();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id,
          title: "Conversación de prueba",
          created_at: "2026-02-09T00:00:00.000Z",
          updated_at: "2026-02-09T00:00:00.000Z",
          message_count: 2,
          model: "SAPTIVA_CORTEX",
          tools_enabled: { create_artifact: true },
          state: "active",
        }),
      });
    },
  );
}

/** Mock unified chat history for a specific conversation.
 *
 * FORMA REAL del payload unified: { events: [{ message_id, event_type:
 * "chat_message", chat_data: { role, content, model }, timestamp }] } —
 * el mock anterior devolvía { messages: [...] } (forma inexistente) y la
 * hidratación de React Query resolvía historial VACÍO, limpiando el hilo
 * recién streameado (race: en solo el assert ganaba; en lote perdía).
 * También se hace eco del chat_id pedido en la URL.
 */
export async function mockChatHistory(
  page: Page,
  messages?: typeof testMessages,
): Promise<void> {
  const msgs = messages ?? testMessages;
  await page.route("**/api/history/*/unified*", (route) => {
    const match = new URL(route.request().url()).pathname.match(
      /\/api\/history\/([^/]+)\/unified/,
    );
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        chat_id: match?.[1] ?? "conv-001",
        events: msgs.map((m) => ({
          message_id: m.id,
          event_type: "chat_message",
          chat_data: {
            role: m.role,
            content: m.content,
            model: "mock-model",
          },
          timestamp: m.created_at,
        })),
      }),
    });
  });
}

/** Mock available models endpoint. */
export async function mockModels(page: Page): Promise<void> {
  await page.route("**/api/models", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        default_model: "Saptiva Turbo",
        allowed_models: ["Saptiva Turbo", "Saptiva Cortex"],
      }),
    }),
  );
}

/** Mock feature flags endpoint. */
export async function mockFeatureFlags(page: Page): Promise<void> {
  await page.route("**/api/feature-flags", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        deep_research_kill_switch: false,
        deep_research_enabled: false,
        deep_research_auto: false,
        deep_research_complexity_threshold: 0.7,
        create_chat_optimistic: true,
      }),
    }),
  );
}

/** Mock health endpoint for connection checks. */
export async function mockHealth(page: Page): Promise<void> {
  await page.route("**/api/health*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "healthy",
        timestamp: "2026-02-09T00:00:00Z",
        version: "e2e-mock",
        uptime_seconds: 12345,
        checks: {
          api: "ok",
        },
      }),
    }),
  );
}

/** Mock chat status endpoint used by draft/refresh logic. */
export async function mockChatStatus(page: Page): Promise<void> {
  await page.route("**/api/history/*/status*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        state: "active",
        message_count: 0,
      }),
    }),
  );
}

/** Mock canvas state load/save endpoints. */
export async function mockCanvasState(page: Page): Promise<void> {
  await page.route("**/api/sessions/*/canvas*", (route) => {
    const method = route.request().method();
    if (method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            is_sidebar_open: false,
            active_artifact_id: null,
            active_message_id: null,
            active_bank_chart: null,
          },
        }),
      });
    }
    if (method === "PATCH") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      });
    }
    return route.fallback();
  });
}

// ---------------------------------------------------------------------------
// Bank data mocks
// ---------------------------------------------------------------------------

/** Mock bank analytics data response. */
export async function mockBankData(page: Page, data?: unknown): Promise<void> {
  await page.route("**/api/analytics/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(data ?? { success: true }),
    }),
  );
}

// ---------------------------------------------------------------------------
// File upload mocks
// ---------------------------------------------------------------------------

/** Mock del listado de documentos/adjuntos de una conversación.
 *
 * Sin este mock, la navegación a /chat/<id> disparaba GET /api/documents
 * contra el backend REAL con el token fake → 401 → auto-logout a mitad del
 * test (el "cerrador fantasma" del spec de chart-caching, cazado con trace
 * el 2026-07-21). */
export async function mockDocuments(page: Page): Promise<void> {
  await page.route("**/api/documents*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ documents: [], total: 0 }),
    }),
  );
}

/** Mock file upload endpoint. */
export async function mockUpload(page: Page): Promise<void> {
  await page.route("**/api/proxy/upload*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "file-001",
        filename: "test-document.pdf",
        size: 1024,
        status: "uploaded",
      }),
    }),
  );
}

/** Mock file events SSE endpoint. */
export async function mockFileEvents(page: Page): Promise<void> {
  const sseBody = createSSEResponse([
    { event: "meta", data: { job_id: "job-001" } },
    { event: "status", data: { status: "processing" } },
    { event: "progress", data: { progress: 100 } },
    { event: "ready", data: { status: "ready" } },
  ]);
  await page.route("**/api/files/events/**", (route) =>
    route.fulfill({
      status: 200,
      headers: sseHeaders(),
      body: sseBody,
    }),
  );
}

// ---------------------------------------------------------------------------
// Composite helpers
// ---------------------------------------------------------------------------

/** Set up all common API mocks for an authenticated chat session. */
export async function mockAllChatApis(page: Page): Promise<void> {
  await Promise.all([
    mockMe(page),
    mockRefresh(page),
    mockConversations(page),
    mockCreateConversation(page),
    mockSessionDetail(page),
    mockChatHistory(page),
    mockChatStatus(page),
    mockCanvasState(page),
    mockDocuments(page),
    mockModels(page),
    mockFeatureFlags(page),
    mockHealth(page),
    mockChatStream(page),
    mockLogout(page),
  ]);
}

/** Inject mock auth state into localStorage (bypass login form).
 *
 * Computes expiresAt inside the browser so the token is always fresh,
 * regardless of when the Node.js process imported test-data.ts.
 */
export async function injectAuthState(page: Page): Promise<void> {
  await page.addInitScript((user) => {
    const authState = {
      state: {
        user,
        accessToken: "e2e-mock-access-token-abc123",
        refreshToken: "e2e-mock-refresh-token-xyz789",
        expiresAt: Date.now() + 3600 * 1000,
      },
      version: 1,
    };
    window.localStorage.setItem(
      "copilotos-auth-state",
      JSON.stringify(authState),
    );
  }, testUser);
}
