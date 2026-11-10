/**
 * P2.7 del reporte de QA (2026-10-20): "dos veces el botón de enviar
 * no funcionó y hubo que recargar; la ventana de ayuda se quedó encima del
 * chat". En producción quedó un chat creado sin mensajes (21 de octubre,
 * 18:14 UTC) justo después de usar la ayuda.
 *
 * Un chat nuevo nace con id temporal y, cuando el servidor responde, cambia al
 * id real. Lo que el usuario escribió o eligió en la ayuda en ese segundo debe
 * seguir en el compositor y poder enviarse. La creación se simula con la
 * latencia de producción (1.2 s).
 */
import type { Page } from "@playwright/test";

import { test, expect } from "../fixtures";
import { ChatPage } from "../pages/ChatPage";
import { SidebarPage } from "../pages/SidebarPage";

const ID_REAL = "3f6c2a10-1111-4222-8333-944455556666";
const PROMPT_AYUDA = "¿Cuánto vendimos la semana pasada?";

async function crearConLatencia(page: Page): Promise<void> {
  await page.route(
    (url) => url.pathname.endsWith("/api/conversations"),
    async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      await new Promise((r) => setTimeout(r, 1200));
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: ID_REAL,
          title: "Nueva conversación",
          created_at: "2026-10-21T18:14:24.000Z",
          updated_at: "2026-10-21T18:14:24.000Z",
          message_count: 0,
          model: "SAPTIVA_CORTEX",
          tools_enabled: { retail_advisor: true },
          state: "draft",
        }),
      });
    },
  );
}

async function ayudaSimulada(page: Page): Promise<void> {
  await page.route(
    (url) => url.pathname.endsWith("/api/features/suggestions"),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          suggestions: [
            {
              id: "venta_semana_pasada",
              titulo: "Venta de la semana pasada",
              prompt: PROMPT_AYUDA,
              categoria: "consultar",
            },
          ],
        }),
      }),
  );
  await page.route(
    (url) => url.pathname.endsWith("/api/features/views"),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ views: [] }),
      }),
  );
  await page.route(
    (url) => url.pathname.endsWith("/api/features/guide"),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ guide: { puedes: [], no_tiene: [] } }),
      }),
  );
}

test.describe("Chat nuevo: el compositor sobrevive al cambio de id (P2.7)", () => {
  test.beforeEach(async ({ authenticatedPage: page }) => {
    await crearConLatencia(page);
    await ayudaSimulada(page);
  });

  test("lo escrito al abrir un chat nuevo sigue ahí cuando llega el id real", async ({
    authenticatedPage: page,
  }) => {
    await page.goto("/chat");
    const chat = new ChatPage(page);
    const sidebar = new SidebarPage(page);
    await expect(chat.composerInput).toBeVisible();

    await sidebar.createNewChat();
    await chat.composerInput.fill("hola, prueba de P2.7");
    await page.waitForURL(`**/chat/${ID_REAL}`, { timeout: 10_000 });
    await page.waitForTimeout(800);

    await expect(chat.composerInput).toHaveValue("hola, prueba de P2.7");
  });

  test("la pregunta elegida en la ayuda sigue en el compositor y la ayuda se cierra", async ({
    authenticatedPage: page,
  }) => {
    await page.goto("/chat");
    const chat = new ChatPage(page);
    const sidebar = new SidebarPage(page);
    await expect(chat.composerInput).toBeVisible();

    await sidebar.createNewChat();
    // Como usuario: el chat nuevo ya se ve, abre la ayuda y elige una pregunta
    // mientras llega el id real y se hidrata el historial vacío.
    await expect(chat.composerInput).toBeVisible({ timeout: 10_000 });
    await chat.helpOnboardingTrigger.click();
    await page
      .getByTestId("help-onboarding-sugerencia-venta_semana_pasada")
      .click();
    await page.waitForURL(`**/chat/${ID_REAL}`, { timeout: 10_000 });
    await page.waitForTimeout(1500);

    await expect(chat.helpOnboardingMenu).toBeHidden();
    await expect(page.getByTestId("help-onboarding-overlay")).toBeHidden();
    await expect(chat.composerInput).toHaveValue(PROMPT_AYUDA);
    await expect(chat.sendButton).toBeEnabled();
  });

  test("la ayuda abierta en cuanto se pulsa nuevo chat no se queda encima", async ({
    authenticatedPage: page,
  }) => {
    await page.goto("/chat");
    const chat = new ChatPage(page);
    const sidebar = new SidebarPage(page);
    await expect(chat.composerInput).toBeVisible();

    await sidebar.createNewChat();
    // Sin esperar: la ayuda se abre mientras el chat nuevo se crea.
    await chat.helpOnboardingTrigger.click();
    await page.waitForURL(`**/chat/${ID_REAL}`, { timeout: 10_000 });
    await page.waitForTimeout(1500);

    // Si la ayuda sigue abierta, se puede usar; si se cerró, no deja fondo.
    if (await chat.helpOnboardingMenu.isVisible()) {
      await page
        .getByTestId("help-onboarding-sugerencia-venta_semana_pasada")
        .click({ timeout: 5_000 });
      await expect(chat.composerInput).toHaveValue(PROMPT_AYUDA);
    }
    await expect(chat.helpOnboardingMenu).toBeHidden();
    await expect(page.getByTestId("help-onboarding-overlay")).toBeHidden();
    await chat.composerInput.fill("sigue funcionando");
    await expect(chat.sendButton).toBeEnabled();
  });

  test("elegir en la ayuda en cuanto se pulsa nuevo chat deja la pregunta lista para enviar", async ({
    authenticatedPage: page,
  }) => {
    await page.goto("/chat");
    const chat = new ChatPage(page);
    const sidebar = new SidebarPage(page);
    await expect(chat.composerInput).toBeVisible();

    await sidebar.createNewChat();
    await chat.helpOnboardingTrigger.click();
    await page
      .getByTestId("help-onboarding-sugerencia-venta_semana_pasada")
      .click({ timeout: 8_000 });
    await page.waitForURL(`**/chat/${ID_REAL}`, { timeout: 10_000 });
    await page.waitForTimeout(1500);

    await expect(chat.helpOnboardingMenu).toBeHidden();
    await expect(chat.composerInput).toHaveValue(PROMPT_AYUDA);
    await expect(chat.sendButton).toBeEnabled();
  });
});

