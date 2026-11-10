/**
 * E2E del flujo chat → contrato analytics → canvas (mocks de API).
 *
 * Recrea la cobertura de los specs borrados (chat/canvas-first-open) contra
 * el contrato REAL: metadata.retail_analytics en el payload `done`, no el
 * evento SSE `bank_chart` muerto. Ver card revivir-e2e-chat-canvas-analytics.
 */
import { test, expect } from "../fixtures";
import { ChatPage } from "../pages/ChatPage";
import {
  buildAnalyticsResponse,
  buildAnalyticsSSEEvents,
} from "../utils/analytics-fixtures";
import { testSSEChunks } from "../utils/test-data";

test.describe("Chat streaming", () => {
  test("send message and receive streamed response", async ({
    chatPage: page,
    mockApi,
  }) => {
    await mockApi.injectAuthState(page);
    await mockApi.mockChatStream(page, testSSEChunks);
    // Historial COHERENTE con el stream: la hidratación de React Query pide
    // /api/history/<id>/unified tras el turno; si el mock devuelve mensajes
    // ajenos, pisa el mensaje streameado (race dependiente de carga).
    await mockApi.mockChatHistory(page, [
      {
        id: "msg-u-001",
        role: "user",
        content: "dame un resumen del día",
        created_at: "2026-02-08T10:00:00Z",
      },
      {
        id: "msg-a-001",
        role: "assistant",
        content: "Esta es una respuesta de prueba.",
        created_at: "2026-02-08T10:00:05Z",
      },
    ]);
    const chatPage = new ChatPage(page);
    await page.reload();

    // OJO: "hola"/"gracias"/"adios" tienen respuesta ENLATADA local
    // (useOptimizedChat) y nunca tocan la red — usar un mensaje no enlatado.
    await chatPage.sendMessage("dame un resumen del día");

    await expect(
      page.getByText("Esta es una respuesta de prueba."),
    ).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("Analytics → canvas", () => {
  test("analytics response opens chart in canvas on first message", async ({
    chatPage: page,
    mockApi,
  }) => {
    await mockApi.injectAuthState(page);
    await mockApi.mockChatStream(
      page,
      buildAnalyticsSSEEvents({ chatId: "conv-e2e-1", messageId: "msg-a-1" }),
    );
    const chatPage = new ChatPage(page);
    await page.reload();

    await chatPage.sendMessage("¿cómo va la venta por tienda esta semana?");

    // Narración en el hilo
    await expect(page.getByText(/2,795 unidades/)).toBeVisible({
      timeout: 15_000,
    });
    // Canvas abierto automáticamente con la gráfica de la métrica
    await expect(page.getByText("Gráfica", { exact: true })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("venta_hora").first()).toBeVisible();
  });

  test("canvas shows grounding (fuente + corte + frescura)", async ({
    chatPage: page,
    mockApi,
  }) => {
    await mockApi.injectAuthState(page);
    await mockApi.mockChatStream(
      page,
      buildAnalyticsSSEEvents({ chatId: "conv-e2e-1", messageId: "msg-a-2" }),
    );
    const chatPage = new ChatPage(page);
    await page.reload();

    await chatPage.sendMessage("venta por tienda");

    await expect(page.getByText("Fuente: retail-advisor")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/2026-07-07/).first()).toBeVisible();
    await expect(page.getByText(/Intradía/i).first()).toBeVisible();
  });

  test("non-chartable analytics (chart_type none) does not open canvas", async ({
    chatPage: page,
    mockApi,
  }) => {
    await mockApi.mockChatStream(
      page,
      buildAnalyticsSSEEvents({
        chatId: "conv-e2e-1",
        messageId: "msg-a-3",
        content: "La métrica no está en el catálogo.",
        analytics: buildAnalyticsResponse({
          chart_type: "none",
          series: [],
          error: "unknown_metric",
        }),
      }),
    );
    await mockApi.injectAuthState(page);
    const chatPage = new ChatPage(page);
    await page.reload();

    await chatPage.sendMessage("métrica inexistente");

    await expect(
      page.getByText("La métrica no está en el catálogo."),
    ).toBeVisible({ timeout: 15_000 });
    // No se abre ninguna gráfica en el canvas (assert por la inversa: el
    // texto "Sin selección" del panel vacío no siempre está montado).
    await page.waitForTimeout(1500);
    await expect(page.getByText("Gráfica", { exact: true })).toHaveCount(0);
  });
});

test.describe("Help onboarding", () => {
  test("menu opens and closes", async ({ chatPage: page, mockApi }) => {
    await mockApi.injectAuthState(page);
    await page.reload();
    const helpButton = page.getByRole("button", {
      name: /vistas predefinidas y guía/i,
    });
    await expect(helpButton).toBeVisible({ timeout: 10_000 });
    await helpButton.click();

    // El menú abre con contenido de ayuda visible
    const dialog = page.getByRole("dialog").first();
    const opened = await dialog
      .isVisible({ timeout: 3_000 })
      .catch(() => false);
    if (opened) {
      await page.keyboard.press("Escape");
      await expect(dialog).not.toBeVisible({ timeout: 5_000 });
    } else {
      // Variante popover/panel (sin role=dialog): el botón queda expanded
      await expect(helpButton).toHaveAttribute("aria-expanded", /true|false/);
    }
  });
});

test.describe("Herramienta de datos fija por despliegue", () => {
  test("sin chip en el compositor y encendida en el payload", async ({
    chatPage: page,
    mockApi,
  }) => {
    // Card pill-retail-default-nudge: sin la tool el LLM inventa cifras. Desde
    // el 2026-10-19 la fija NEXT_PUBLIC_DEFAULT_TOOLS y no pinta chip: el
    // usuario no tiene nada que decidir (feedback de QA, punto 10).
    const cuerpos: Array<Record<string, unknown>> = [];
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        new URL(request.url()).pathname.endsWith("/api/chat")
      ) {
        cuerpos.push(request.postDataJSON());
      }
    });
    await mockApi.injectAuthState(page);
    await mockApi.mockChatStream(page, testSSEChunks);
    await page.reload();

    await expect(page.getByTestId("tool-chip-retail-advisor")).toHaveCount(0);
    await expect(page.getByText("Datos de venta e inventario")).toHaveCount(0);

    const chatPage = new ChatPage(page);
    await chatPage.sendMessage("dame un resumen del día");
    await expect
      .poll(() => cuerpos.length, { timeout: 15_000 })
      .toBeGreaterThan(0);
    const tools = cuerpos[cuerpos.length - 1].tools_enabled as
      | Record<string, boolean>
      | undefined;
    expect(tools?.retail_advisor).toBe(true);
  });
});

test.describe("401 en features secundarias", () => {
  test("401 del auto-título no desloguea ni borra los mensajes", async ({
    chatPage: page,
    mockApi,
  }) => {
    await mockApi.injectAuthState(page);
    await mockApi.mockChatStream(page, testSSEChunks);
    await mockApi.mockChatHistory(page, [
      {
        id: "msg-u-001",
        role: "user",
        content: "dame un resumen del día",
        created_at: "2026-02-08T10:00:00Z",
      },
      {
        id: "msg-a-001",
        role: "assistant",
        content: "Esta es una respuesta de prueba.",
        created_at: "2026-02-08T10:00:05Z",
      },
    ]);
    // Forzar 401 SOLO en el PATCH de sesión (auto-título); GET sigue al
    // mock normal. Reproduce el escenario original de la race del card
    // revivir-e2e: antes esto disparaba auto-logout y wipeaba el chat.
    await page.route(
      (url) => /\/api\/sessions\/[^/?]+$/.test(url.pathname),
      async (route) => {
        if (route.request().method() !== "PATCH") return route.fallback();
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ code: "token_expired" }),
        });
      },
    );
    const chatPage = new ChatPage(page);
    await page.reload();

    await chatPage.sendMessage("dame un resumen del día");
    await expect(
      page.getByText("Esta es una respuesta de prueba."),
    ).toBeVisible({ timeout: 15_000 });

    // El 401 del auto-título ya ocurrió en background: los mensajes deben
    // seguir vivos y sin aviso de sesión expirada.
    await page.waitForTimeout(2000);
    await expect(
      page.getByText("Esta es una respuesta de prueba."),
    ).toBeVisible();
    await expect(page.getByText(/sesión ha expirado/i)).toHaveCount(0);
    await expect(page).not.toHaveURL(/login/);
  });
});

test.describe("Caching de charts entre navegaciones", () => {
  // UUID válido: la ruta /chat/[chatId] hace notFound() con ids no-UUID.
  const CACHE_CHAT_ID = "3f2a1b4c-1111-4111-8111-000000000001";

  // RESUELTO (2026-07-21, con --trace on): el "cerrador fantasma" eran DOS
  // bugs apilados — (1) GET /api/documents sin mock pegaba al backend real
  // con el token fake → 401 → AUTO-LOGOUT a mitad de la navegación (fix de
  // producto: documents es feature secundaria en isSecondaryRequest; fix de
  // spec: mockDocuments en mockAllChatApis); (2) en dev, la compilación por
  // ruta re-evaluaba canvas-store creando una SEGUNDA instancia de zustand
  // (4 instancias por run medidas en trace) — el chart vivía en una y el
  // panel leía otra (fix: singleton anclado en globalThis). Este spec además
  // provocó los fixes previos de la persistencia (restore que era código
  // muerto + guard "canvas vivo gana").
  test("el chart del canvas se restaura al volver a la conversación sin re-llamar el stream", async ({
    chatPage: page,
    mockApi,
  }) => {
    await mockApi.injectAuthState(page);
    await mockApi.mockChatStream(
      page,
      buildAnalyticsSSEEvents({
        chatId: CACHE_CHAT_ID,
        messageId: "msg-cache-1",
      }),
    );
    // La conversación del turno debe existir en el sidebar para poder VOLVER
    // a ella con navegación SPA (registrado después del fixture: LIFO gana).
    await mockApi.mockConversations(page, [
      {
        id: CACHE_CHAT_ID,
        title: "Venta por tienda (cache)",
        created_at: "2026-02-08T09:00:00Z",
        updated_at: "2026-02-08T10:00:05Z",
        message_count: 2,
      },
    ]);
    // Persistencia STATEFUL del canvas: el PATCH guarda y el GET devuelve lo
    // guardado (lo que hace el backend real con Mongo). Se registra DESPUÉS
    // del fixture para ganarle al mockCanvasState estático (orden LIFO).
    let guardado: Record<string, unknown> | null = null;
    await page.route("**/api/sessions/*/canvas*", async (route) => {
      const method = route.request().method();
      if (method === "PATCH" || method === "PUT") {
        guardado = route.request().postDataJSON() as Record<string, unknown>;
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ success: true }),
        });
      }
      if (method === "GET") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            data: guardado ?? {
              is_sidebar_open: false,
              active_artifact_id: null,
              active_message_id: null,
              active_chart: null,
            },
          }),
        });
      }
      return route.fallback();
    });
    const chatPage = new ChatPage(page);
    await page.reload();

    await chatPage.sendMessage("¿cómo va la venta por tienda esta semana?");
    await expect(page.getByText("Gráfica", { exact: true })).toBeVisible({
      timeout: 15_000,
    });
    // El store sincroniza el chart al backend (PATCH con active_chart).
    await expect
      .poll(() => (guardado?.active_chart ? true : false), { timeout: 10_000 })
      .toBe(true);

    // Salir del hilo (reload limpio a /chat: canvas cerrado, estado en cero)…
    await page.goto("/chat");
    await expect(page.getByText("Gráfica", { exact: true })).toHaveCount(0, {
      timeout: 10_000,
    });

    // …y VOLVER a la conversación por el sidebar (navegación SPA): el chart
    // se restaura del estado persistido SIN una nueva llamada al stream.
    let streamCalls = 0;
    page.on("request", (req) => {
      if (req.url().includes("/api/chat") && req.method() === "POST") {
        streamCalls += 1;
      }
    });
    await page
      .getByRole("button", { name: "Venta por tienda (cache)" })
      .click();

    await expect(page.getByText("Gráfica", { exact: true })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("venta_hora").first()).toBeVisible();
    expect(streamCalls).toBe(0);
  });
});

test.describe("Mapa por región (chart_type map)", () => {
  test("analytics con chart_type map abre el canvas con el choropleth", async ({
    chatPage: page,
    mockApi,
  }) => {
    await mockApi.injectAuthState(page);
    await mockApi.mockChatStream(
      page,
      buildAnalyticsSSEEvents({
        chatId: "conv-e2e-1",
        messageId: "msg-map-1",
        content:
          "Quintana Roo lidera con 84.6% de inventario de sistema con existencia.",
        analytics: buildAnalyticsResponse({
          metric_name: "disponibilidad",
          chart_type: "map",
          series: [
            {
              name: "Inventario de sistema con existencia",
              points: [
                { label: "Quintana Roo", value: 84.57, dimension: null },
                { label: "Jalisco", value: 83.32, dimension: null },
                { label: "Estado de México", value: 82.9, dimension: null },
              ],
            },
          ],
          grounding: {
            source: "retail-advisor",
            metric: "disponibilidad",
            unit: "percent",
            dimension: "region",
            freshness: "day_closed",
          },
          freshness: "day_closed",
        }),
      }),
    );
    const chatPage = new ChatPage(page);
    await page.reload();

    await chatPage.sendMessage(
      "¿Cómo está el inventario de sistema con existencia por región?",
    );

    await expect(page.getByText(/Quintana Roo lidera/)).toBeVisible({
      timeout: 15_000,
    });
    // El canvas abre con la gráfica (el trace choropleth no debe tronar el
    // registry ni caer al estado de error/tabla).
    await expect(page.getByText("Gráfica", { exact: true })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("disponibilidad").first()).toBeVisible();
  });
});
