/**
 * feedback round 1 (2026-10-16): la interfaz del chat en un
 * navegador real, con API simulada, en tema claro y oscuro.
 *
 * - Punto 7: la tabla de la respuesta queda dentro de la burbuja con borde y
 *   el texto largo parte renglón.
 * - Punto 9: Copy y Regenerate se leen en tema claro.
 * - Punto 10: la herramienta de datos va fija por despliegue, sin chip
 *   (2026-10-19); sigue encendida en el payload de /api/chat.
 * - Punto 11: el historial dice Energy Ontology Advisor.
 * - Punto 12: el feedback llega a POST /api/feedback con el id del chat.
 * - Puntos 14 y 15: el modal lista las vistas del plugin, sin benchmark,
 *   y las preguntas sugeridas que antes eran chips bajo el compositor, con
 *   iconos SVG (sin emojis).
 *
 * Las capturas quedan en test-results/feedback-round1/ para validate.md.
 */
import type { Page } from "@playwright/test";

import { test, expect } from "../fixtures";
import { ChatPage } from "../pages/ChatPage";

// Playwright limpia test-results en cada corrida: E2E_CAPTURAS_DIR guarda las
// capturas fuera para validate.md.
const DIR = process.env.E2E_CAPTURAS_DIR ?? "test-results/feedback-round1";

const VISTAS = [
  {
    id: "venta_mes",
    titulo: "Venta del mes",
    descripcion: "Cuánto se vendió este mes, en piezas y pesos.",
    prompt: "¿Cuánto vendimos este mes?",
    icono: "🧾",
    perfiles: ["gerente_tienda", "jefe_departamento", "compras"],
  },
  {
    id: "riesgo_manana",
    titulo: "Productos en riesgo para mañana",
    descripcion: "Las alertas de faltante del último corte.",
    prompt: "¿Qué productos están en riesgo de faltante mañana?",
    icono: "🚨",
    perfiles: ["gerente_tienda", "jefe_departamento", "compras"],
  },
];

const SUGERENCIAS = [
  {
    id: "tendencia_refrescos",
    titulo: "Tendencia de Refrescos",
    prompt: "Muéstrame la tendencia de venta de refrescos del último mes",
    icono: "📈",
    categoria: "ventas",
  },
  {
    id: "alertas_faltante",
    titulo: "Alertas de mañana",
    prompt: "¿Qué productos están en riesgo de faltante mañana?",
    icono: "🚨",
    categoria: "inventario",
  },
];

// Guía rápida declarada por el plugin (QA, P2.2, 2026-10-21).
const GUIA = {
  puedes: [
    "Preguntar en tus palabras, de las catorce tiendas o de una sola, por la venta y el pronóstico de venta de los próximos días.",
    "Ver las alertas de faltante de una fecha pasada y qué pasó después, por ejemplo las del 24 de septiembre de 2026.",
  ],
  no_tiene: ["Precios de proveedor: no vienen en la entrega."],
};

const RESPUESTA_ALERTAS = [
  "Para mañana hay **3 productos** con riesgo de faltante en Centro.",
  "",
  "| Producto | Venta en riesgo (MXN) | Confianza | Razón principal |",
  "| :--- | :--- | :--- | :--- |",
  "| Tequila Don Julio Anejo Cristalino 700 M | **$425.58** | media | Quedan 49 piezas, para unos 31 días de venta, y vendió 6 en la última semana; si mañana no se vende, revisa que esté en anaquel. |",
  "| Coca Cola Cereza Zero 600 Ml | **$212.40** | alta | Sin existencia al cierre; se venden unas 8 piezas al día. |",
  "| Agua Mineral Ciel 1.75 Lt Pet | **$98.10** | alta | Quedan 3 piezas, para unos 2 días de venta. |",
  "",
  "Datos al 30 de septiembre de 2026.",
].join("\n");

const CHUNKS_ALERTAS = [
  {
    event: "meta",
    data: { chat_id: "conv-e2e-1", user_message_id: "msg-u-001", model: "x" },
  },
  { event: "chunk", data: { content: RESPUESTA_ALERTAS } },
  {
    event: "done",
    data: {
      id: "msg-a-001",
      role: "assistant",
      content: RESPUESTA_ALERTAS,
      chat_id: "conv-e2e-1",
      created_at: "2026-10-19T10:01:00Z",
    },
  },
];

async function conTema(page: Page, tema: "light" | "dark") {
  await page.addInitScript((t) => {
    window.localStorage.setItem("theme", t);
  }, tema);
}

async function prepararRutas(page: Page, feedback: unknown[]) {
  await page.route("**/api/features/views*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ views: VISTAS }),
    }),
  );
  await page.route("**/api/features/suggestions*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ suggestions: SUGERENCIAS }),
    }),
  );
  await page.route("**/api/features/guide*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ guide: GUIA }),
    }),
  );
  await page.route(
    (url) => url.pathname.endsWith("/api/feedback"),
    async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      feedback.push(route.request().postDataJSON());
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: "fb-1",
          feedback_id: "FDBK-0001",
          created_at: "2026-10-19T10:02:00Z",
        }),
      });
    },
  );
}

/** Contraste WCAG entre dos colores CSS rgb(). */
function contraste(a: string, b: string): number {
  const lum = (c: string) => {
    const [r, g, bl] = (c.match(/\d+(\.\d+)?/g) ?? ["0", "0", "0"])
      .slice(0, 3)
      .map((v) => Number(v) / 255)
      .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

for (const tema of ["light", "dark"] as const) {
  test.describe(`Feedback round 1 · tema ${tema}`, () => {
    test("sin chips en el chat, nombre del producto y modal de ayuda", async ({
      chatPage: page,
      mockApi,
    }) => {
      await prepararRutas(page, []);
      await conTema(page, tema);
      await mockApi.injectAuthState(page);
      await page.reload();

      await expect(
        page.getByPlaceholder(/pregúntame algo/i).first(),
      ).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("tool-chip-retail-advisor")).toHaveCount(0);
      await expect(page.getByText("Tendencia de Refrescos")).toHaveCount(0);
      await expect(page.getByText("OctaviOS Chat")).toHaveCount(0);
      await page.screenshot({ path: `${DIR}/chat-${tema}.png` });

      await page
        .getByRole("button", { name: /vistas predefinidas y guía/i })
        .first()
        .click();
      await expect(page.getByText("Venta del mes")).toBeVisible();
      await expect(page.getByText("Preguntas sugeridas")).toBeVisible();
      await expect(page.getByText("Tendencia de Refrescos")).toBeVisible();
      const textoModal = await page
        .getByTestId("help-onboarding-menu")
        .textContent();
      expect(textoModal ?? "").not.toContain("📈");
      await expect(page.getByText(/Benchmark/i)).toHaveCount(0);
      await page.getByTestId("help-onboarding-guide-toggle").click();
      await expect(page.getByText(/24 de septiembre/)).toBeVisible();
      // La guía entra con transición de opacidad; Playwright la da por
      // visible desde opacidad 0, así que se espera a que termine.
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${DIR}/vistas-${tema}.png` });

      await page.getByTestId("help-onboarding-prompt-venta_mes").click();
      await expect(page.getByTestId("help-onboarding-menu")).toHaveCount(0);
    });

    test("tabla de alertas, acciones legibles y feedback enviado", async ({
      chatPage: page,
      mockApi,
    }) => {
      const feedback: unknown[] = [];
      await prepararRutas(page, feedback);
      await mockApi.mockChatStream(page, CHUNKS_ALERTAS);
      await conTema(page, tema);
      await mockApi.injectAuthState(page);
      await page.reload();

      const chatPage = new ChatPage(page);
      await chatPage.sendMessage(
        "¿Qué productos están en riesgo de faltante mañana?",
      );
      const tabla = page.locator("table").last();
      await expect(tabla).toBeVisible({ timeout: 15_000 });

      // Punto 7: la celda larga parte renglón y la tabla cabe en la burbuja.
      const razon = tabla.locator("td").nth(3);
      await expect(razon).toHaveClass(/whitespace-normal/);
      const anchos = await tabla.evaluate((t) => ({
        tabla: t.scrollWidth,
        contenedor: (t.parentElement as HTMLElement).clientWidth,
      }));
      expect(anchos.tabla).toBeLessThanOrEqual(anchos.contenedor + 1);

      // Punto 9: Copy se lee contra el fondo de la burbuja.
      await tabla.hover();
      const copiar = page
        .getByRole("button", { name: /copiar mensaje/i })
        .last();
      await expect(copiar).toBeVisible();
      const colores = await copiar.evaluate((b) => {
        let el: HTMLElement | null = b as HTMLElement;
        let fondo = "rgba(0, 0, 0, 0)";
        while (el) {
          const c = getComputedStyle(el).backgroundColor;
          if (c && !c.startsWith("rgba(0, 0, 0, 0)") && c !== "transparent") {
            fondo = c;
            break;
          }
          el = el.parentElement;
        }
        return { texto: getComputedStyle(b).color, fondo };
      });
      expect(contraste(colores.texto, colores.fondo)).toBeGreaterThanOrEqual(3);
      await page.screenshot({ path: `${DIR}/alertas-${tema}.png` });

      // Punto 12: el feedback sale al backend con el id del chat.
      await page.getByRole("button", { name: "Respuesta útil" }).last().click();
      await page
        .getByPlaceholder("¿Qué te gustó de esta respuesta? (opcional)")
        .fill("La razón de cada producto es clara");
      await page
        .getByTestId("message-feedback")
        .last()
        .getByRole("button", { name: "Enviar", exact: true })
        .click();
      await expect(page.getByText("Gracias por tu feedback")).toBeVisible();
      expect(feedback).toHaveLength(1);
      const enviado = feedback[0] as Record<string, string>;
      expect(enviado.conversation_id).toBeTruthy();
      expect(enviado.conversation_id.startsWith("temp-")).toBe(false);
      expect(enviado.rating).toBe("up");
    });
  });
}
