/**
 * Equipo (2026-10-21):
 * - Mientras se prepara la respuesta había dos indicadores (uno gris en la
 *   burbuja y una barra verde "Analizando con Saptiva Turbo…" bajo el
 *   compositor). Queda uno: verde, en la burbuja y sin texto visible.
 * - La gráfica cerrada con la X no se podía volver a abrir. Cada respuesta
 *   con gráfica lleva "Ver gráfica", también las anteriores de la
 *   conversación (el historial trae `metadata.retail_analytics`).
 *
 * Con CAPTURAS_DIR guarda capturas para revisarlas a ojo.
 */
import type { Page } from "@playwright/test";

import { test, expect } from "../fixtures";
import { ChatPage } from "../pages/ChatPage";
import {
  buildAnalyticsResponse,
  buildAnalyticsSSEEvents,
} from "../utils/analytics-fixtures";
import { createSSEResponse } from "../utils/mock-sse";

const ID_CHAT = "5a1f0c22-1111-4222-8333-944455556666";

async function captura(page: Page, nombre: string): Promise<void> {
  const dir = process.env.CAPTURAS_DIR;
  if (!dir) return;
  // El panel entra con una transición de 200 ms: capturar ya asentado.
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${dir}/${nombre}.png` });
}

/** La gráfica cabe en el panel: Plotly mide su contenedor al montarse y, si
 * el panel todavía se estaba acomodando, se quedaba más ancha y cortada. */
async function graficaCabeEnPanel(page: Page): Promise<void> {
  const panel = page.getByTestId("canvas-panel");
  const svg = panel.locator(".main-svg").first();
  await expect(svg).toBeVisible({ timeout: 10_000 });
  await expect
    .poll(
      async () => {
        const derechaSvg = await svg.evaluate((e) => e.getBoundingClientRect().right);
        const derechaPanel = await panel.evaluate((e) => e.getBoundingClientRect().right);
        return Math.round(derechaSvg - derechaPanel);
      },
      { timeout: 3_000 },
    )
    .toBeLessThanOrEqual(0);
}

function analytics(titulo: string, valor: number) {
  return buildAnalyticsResponse({
    visualization: { title: titulo, task: "ranking" },
    series: [
      {
        name: titulo,
        points: [
          { label: "Polanco", value: valor, dimension: null },
          { label: "Mundo E", value: Math.round(valor / 2), dimension: null },
        ],
      },
    ],
  });
}

async function streamLento(page: Page, retrasoMs: number): Promise<void> {
  const body = createSSEResponse(
    buildAnalyticsSSEEvents({
      chatId: ID_CHAT,
      messageId: "msg-a-grafica",
      content: "Polanco vendió 782,847 piezas el último mes.",
      analytics: analytics("Venta por tienda", 782847),
    }),
  );
  await page.route(
    (url) => url.pathname.endsWith("/api/chat"),
    async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      await new Promise((r) => setTimeout(r, retrasoMs));
      return route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body,
      });
    },
  );
}

test.describe("Espera y gráficas de la conversación", () => {
  test("un solo indicador verde sin texto, y la gráfica cerrada se vuelve a abrir", async ({
    chatPage: page,
    mockApi,
  }) => {
    await mockApi.injectAuthState(page);
    await streamLento(page, 2500);
    const chat = new ChatPage(page);
    await page.reload();

    await chat.sendMessage("¿cuánto vendió cada tienda el último mes?");

    const espera = page.getByRole("status", { name: "Pensando" });
    await expect(espera).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/analizando con/i)).toHaveCount(0);
    await expect(page.getByText(/generando respuesta/i)).toHaveCount(0);
    await captura(page, "1-esperando");

    await expect(page.getByText(/782,847 piezas/)).toBeVisible({ timeout: 15_000 });
    const verGrafica = page.getByRole("button", { name: /ver gráfica/i });
    await expect(verGrafica).toBeVisible();
    await expect(page.getByText("Gráfica", { exact: true })).toBeVisible();
    await captura(page, "2-respuesta-con-grafica");

    await page.getByTitle("Cerrar").click();
    // El panel se cierra a ancho 0 (el texto sigue en el DOM): el botón dice
    // que su gráfica ya no está a la vista.
    await expect(verGrafica).toHaveAttribute("aria-pressed", "false");
    await captura(page, "3-grafica-cerrada");

    await verGrafica.click();
    await expect(page.getByText("Gráfica", { exact: true })).toBeVisible();
    await expect(verGrafica).toHaveAttribute("aria-pressed", "true");
    await graficaCabeEnPanel(page);
    await captura(page, "4-grafica-reabierta");
  });

  test("las gráficas de respuestas anteriores se abren desde su botón", async ({
    authenticatedPage: page,
  }) => {
    await page.route("**/api/history/*/unified*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          chat_id: ID_CHAT,
          events: [
            ["u1", "user", "venta por tienda", undefined],
            ["a1", "assistant", "Polanco encabeza la venta.", analytics("Venta por tienda", 782847)],
            ["u2", "user", "quiebre por tienda", undefined],
            ["a2", "assistant", "Ticul tiene más quiebre.", analytics("Quiebre por tienda", 11)],
          ].map(([id, role, content, retail], i) => ({
            message_id: id,
            event_type: "chat_message",
            chat_data: {
              role,
              content,
              model: "mock-model",
              metadata: retail ? { retail_analytics: retail } : undefined,
            },
            timestamp: `2026-10-21T18:0${i}:00Z`,
          })),
        }),
      }),
    );
    await page.goto(`/chat/${ID_CHAT}`);

    const botones = page.getByRole("button", { name: /ver gráfica/i });
    await expect(botones).toHaveCount(2, { timeout: 15_000 });
    await expect(botones.nth(0)).toContainText("Venta por tienda");
    await expect(botones.nth(1)).toContainText("Quiebre por tienda");

    await botones.nth(0).click();
    await expect(page.getByText("Gráfica", { exact: true })).toBeVisible();
    await expect(botones.nth(0)).toHaveAttribute("aria-pressed", "true");
    await expect(botones.nth(1)).toHaveAttribute("aria-pressed", "false");

    await botones.nth(1).click();
    await expect(botones.nth(1)).toHaveAttribute("aria-pressed", "true");
    await expect(botones.nth(0)).toHaveAttribute("aria-pressed", "false");
    await graficaCabeEnPanel(page);
    await captura(page, "5-historial-dos-graficas");
  });
});
