/**
 * Equipo (2026-10-21): la burbuja de espera sigue los pasos del turno, en
 * orden. Arranca con "Pensando"; cuando el backend avisa qué tool eligió el
 * decide (`status` consultando), pasa al tema; cuando ya hay datos (`status`
 * redactando), a la redacción con el mismo ícono; cuando llega el texto, se
 * va.
 *
 * `route.fulfill` entrega el cuerpo de golpe, así que el stream lo sirve un
 * servidor SSE mínimo de la prueba, por partes y con pausas.
 *
 * Con CAPTURAS_DIR guarda una captura por tema para revisarlas a ojo.
 */
import http from "node:http";
import type { AddressInfo } from "node:net";

import type { Page } from "@playwright/test";

import { test, expect } from "../fixtures";
import { ChatPage } from "../pages/ChatPage";
import { buildAnalyticsDonePayload } from "../utils/analytics-fixtures";

const ID_CHAT = "6b2f0c22-1111-4222-8333-944455556677";

const CASOS = [
  {
    pregunta: "¿cuánto vendimos el último mes?",
    status: { tool: "retail_analytics", metrica: "venta_hora", dimension: null },
    frase: "Consultando ventas",
    tema: "ventas",
  },
  {
    pregunta: "¿qué tienda vendió más?",
    status: { tool: "retail_analytics", metrica: "venta_hora", dimension: "tienda" },
    frase: "Comparando tiendas",
    tema: "ranking",
  },
  {
    pregunta: "¿cómo andamos de inventario?",
    status: { tool: "retail_analytics", metrica: "faltante", dimension: null },
    frase: "Revisando inventario",
    tema: "inventario",
  },
  {
    pregunta: "¿qué productos están en riesgo mañana?",
    status: { tool: "alerta_quiebre_probable", metrica: null, dimension: null },
    frase: "Buscando riesgos",
    tema: "riesgo",
  },
  {
    pregunta: "¿qué es la utilidad bruta?",
    status: { tool: "retail_definicion", metrica: null, dimension: null },
    frase: "Un momento",
    tema: "ayuda",
  },
];

const PAUSA_ANTES_DEL_STATUS_MS = 1500;
const PAUSA_ANTES_DE_REDACTAR_MS = 3000;
const PAUSA_ANTES_DEL_TEXTO_MS = 3000;

function evento(nombre: string, datos: unknown): string {
  return `event: ${nombre}\ndata: ${JSON.stringify(datos)}\n\n`;
}

let servidor: http.Server;
let puerto = 0;

test.beforeAll(async () => {
  servidor = http.createServer((req, res) => {
    const cors = {
      "Access-Control-Allow-Origin": req.headers.origin ?? "*",
      "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Headers": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
    };
    if (req.method === "OPTIONS") {
      res.writeHead(204, cors);
      res.end();
      return;
    }
    const i = Number(new URL(req.url ?? "/", "http://x").searchParams.get("caso"));
    const caso = CASOS[i];
    res.writeHead(200, {
      ...cors,
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    res.write(evento("meta", { chat_id: ID_CHAT, model: "mock-model" }));
    setTimeout(() => {
      res.write(evento("status", { fase: "consultando", tools: [caso.status] }));
    }, PAUSA_ANTES_DEL_STATUS_MS);
    setTimeout(() => {
      res.write(evento("status", { fase: "redactando", tools: [caso.status] }));
    }, PAUSA_ANTES_DEL_STATUS_MS + PAUSA_ANTES_DE_REDACTAR_MS);
    setTimeout(() => {
      // Sin gráfica: abrir el panel carga Plotly y bloquea el hilo principal
      // unos segundos, y el stream del turno siguiente se lee tarde.
      const done = {
        ...buildAnalyticsDonePayload({
          chatId: ID_CHAT,
          messageId: `msg-${i}`,
          content: `Respuesta ${i + 1}.`,
        }),
        metadata: {},
      };
      res.write(evento("chunk", { content: done.content }));
      res.write(evento("done", done));
      res.end();
    }, PAUSA_ANTES_DEL_STATUS_MS + PAUSA_ANTES_DE_REDACTAR_MS + PAUSA_ANTES_DEL_TEXTO_MS);
  });
  await new Promise<void>((listo) => servidor.listen(0, "127.0.0.1", listo));
  puerto = (servidor.address() as AddressInfo).port;
});

test.afterAll(async () => {
  await new Promise((cerrado) => servidor.close(cerrado));
});

async function captura(page: Page, nombre: string): Promise<void> {
  const dir = process.env.CAPTURAS_DIR;
  if (dir) await page.screenshot({ path: `${dir}/${nombre}.png` });
}

test.describe("Indicador de espera según la consulta", () => {
  test("sigue los pasos del turno: pensando, el tema de la consulta, redactando, y se va con el texto", async ({
    chatPage: page,
    mockApi,
  }) => {
    test.setTimeout(120_000);
    await mockApi.injectAuthState(page);
    let turno = 0;
    await page.route(
      (url) => url.pathname.endsWith("/api/chat"),
      async (route) => {
        if (route.request().method() !== "POST") return route.fallback();
        const caso = turno++;
        return route.continue({ url: `http://127.0.0.1:${puerto}/sse?caso=${caso}` });
      },
    );
    const chat = new ChatPage(page);
    await page.reload();

    for (let i = 0; i < CASOS.length; i++) {
      const caso = CASOS[i];
      await chat.sendMessage(caso.pregunta);

      const pensando = page.getByRole("status", { name: "Pensando" });
      await expect(pensando).toBeVisible({ timeout: 5_000 });
      if (i === 0) await captura(page, "0-pensando");

      const tema = page.getByRole("status", { name: caso.frase });
      await expect(tema).toBeVisible({ timeout: 5_000 });
      await expect(tema.getByTestId("icono-espera")).toHaveAttribute("data-tema", caso.tema);
      await expect(page.getByText(/analizando con|generando respuesta/i)).toHaveCount(0);
      await captura(page, `${i + 1}-${caso.tema}`);

      // Ya hay datos: pasa a redactar con el mismo ícono del tema.
      const redactando = page.getByRole("status", { name: "Redactando la respuesta" });
      await expect(redactando).toBeVisible({ timeout: 6_000 });
      await expect(redactando.getByTestId("icono-espera")).toHaveAttribute("data-tema", caso.tema);
      if (i === 0) await captura(page, "1b-redactando");

      await expect(page.getByText(`Respuesta ${i + 1}.`)).toBeVisible({ timeout: 10_000 });
      await expect(page.getByRole("status", { name: "Redactando la respuesta" })).toHaveCount(0);
    }
  });
});
