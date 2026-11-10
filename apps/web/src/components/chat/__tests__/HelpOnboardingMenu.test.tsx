/**
 * feedback round 1 (2026-10-16, puntos 14 y 15): el modal de vistas
 * predefinidas traía solo "¿Qué puedes hacer?" y un "Generar Reporte
 * Benchmark" heredado del Bank Advisor, con un selector de periodo que no
 * hacía nada. Ahora lista las vistas que declara el plugin (relevadas por
 * /api/features/views) y explica cómo ver alertas de otra fecha.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { HelpOnboardingMenu } from "../HelpOnboardingMenu";
import { HELP_ONBOARDING_PROMPT_EVENT } from "@/lib/help-onboarding-events";
import { useComposerStore } from "@/lib/stores/composer-store";

const VISTAS = [
  {
    id: "venta_mes",
    titulo: "Venta del mes",
    descripcion: "Cuánto se vendió este mes.",
    prompt: "¿Cuánto vendimos este mes?",
    icono: "🧾",
    perfiles: ["gerente_tienda", "compras"],
  },
  {
    id: "riesgo_manana",
    titulo: "Productos en riesgo para mañana",
    descripcion: "Las alertas del último corte.",
    prompt: "¿Qué productos están en riesgo de faltante mañana?",
    icono: "🚨",
    perfiles: ["gerente_tienda"],
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

// La guía rápida la declara el plugin con los datos de la base (QA,
// P2.2, 2026-10-21); antes estaba fija aquí con "14 tiendas" y "septiembre".
const GUIA = {
  puedes: [
    "Preguntar en tus palabras, de las catorce tiendas o de una sola, por la venta y el pronóstico de venta de los próximos días.",
    "La venta va de agosto de 2024 a septiembre de 2026; los datos llegan al 30 de septiembre de 2026.",
    "Ver las alertas de faltante de una fecha pasada y qué pasó después, por ejemplo las del 24 de septiembre de 2026.",
  ],
  no_tiene: ["Precios de proveedor: no vienen en la entrega."],
};

function respuestaPara(url: string, guia = GUIA) {
  if (url.includes("suggestions")) return { suggestions: SUGERENCIAS };
  if (url.includes("guide")) return { guide: guia };
  return { views: VISTAS };
}

beforeEach(() => {
  // El store del compositor es global: cada prueba empieza con la ayuda cerrada.
  useComposerStore.setState({ ayudaAbierta: null, texto: "", chatId: null });
  global.fetch = jest.fn((url: string) =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve(respuestaPara(String(url))),
    }),
  ) as jest.Mock;
});

async function abrir() {
  render(<HelpOnboardingMenu />);
  fireEvent.click(screen.getByTestId("help-onboarding-trigger"));
  await waitFor(() =>
    expect(screen.getByTestId("help-onboarding-menu")).toBeInTheDocument(),
  );
}

describe("HelpOnboardingMenu · vistas predefinidas del plugin", () => {
  it("lista las vistas del backend y no el benchmark heredado", async () => {
    await abrir();
    await waitFor(() =>
      expect(screen.getByText("Venta del mes")).toBeInTheDocument(),
    );
    expect(
      screen.getByText("Productos en riesgo para mañana"),
    ).toBeInTheDocument();
    expect(screen.getByText("Cuánto se vendió este mes.")).toBeInTheDocument();
    expect(screen.queryByText(/Benchmark/i)).toBeNull();
    expect(screen.queryByText(/PPTX/i)).toBeNull();
    expect(screen.queryByText(/Último disponible/i)).toBeNull();
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/features/views",
      expect.anything(),
    );
  });

  it("al elegir una vista manda su prompt al chat y cierra", async () => {
    const recibido = jest.fn();
    window.addEventListener(HELP_ONBOARDING_PROMPT_EVENT, ((e: CustomEvent) =>
      recibido(e.detail.prompt)) as EventListener);
    await abrir();
    await waitFor(() =>
      expect(screen.getByText("Venta del mes")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("help-onboarding-prompt-venta_mes"));
    await waitFor(() =>
      expect(screen.queryByTestId("help-onboarding-menu")).toBeNull(),
    );
    // Llega cuando el diálogo terminó de cerrar (P2.7).
    await waitFor(() =>
      expect(recibido).toHaveBeenCalledWith("¿Cuánto vendimos este mes?"),
    );
  });

  it("la guía explica cómo ver alertas de otra fecha", async () => {
    await abrir();
    fireEvent.click(await screen.findByTestId("help-onboarding-guide-toggle"));
    await waitFor(() =>
      expect(screen.getByText(/24 de septiembre/)).toBeInTheDocument(),
    );
  });

  it("la guía dice lo que declara el plugin: pronóstico, meses y lo que no hay", async () => {
    await abrir();
    fireEvent.click(await screen.findByTestId("help-onboarding-guide-toggle"));
    expect(await screen.findByText(/pronóstico de venta/)).toBeInTheDocument();
    expect(
      screen.getByText(/de agosto de 2024 a septiembre de 2026/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Precios de proveedor/)).toBeInTheDocument();
    expect(screen.queryByText(/14 tiendas/)).toBeNull();
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/features/guide",
      expect.anything(),
    );
  });

  it("sin guía del plugin no muestra la guía rápida", async () => {
    (global.fetch as jest.Mock).mockImplementation((url: string) =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(
            respuestaPara(String(url), { puedes: [], no_tiene: [] }),
          ),
      }),
    );
    await abrir();
    await waitFor(() =>
      expect(screen.getByText("Venta del mes")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("help-onboarding-guide-toggle")).toBeNull();
  });

  it("con el plugin caído dice que no hay vistas, sin romperse", async () => {
    (global.fetch as jest.Mock).mockImplementation(() =>
      Promise.resolve({ ok: false, json: () => Promise.resolve({}) }),
    );
    await abrir();
    await waitFor(() =>
      expect(
        screen.getByTestId("help-onboarding-no-results"),
      ).toBeInTheDocument(),
    );
  });
});

describe("HelpOnboardingMenu · preguntas sugeridas (antes chips del chat)", () => {
  it("lista las sugerencias del plugin agrupadas por categoría", async () => {
    await abrir();
    await waitFor(() =>
      expect(screen.getByText("Tendencia de Refrescos")).toBeInTheDocument(),
    );
    expect(screen.getByText("Preguntas sugeridas")).toBeInTheDocument();
    expect(screen.getByText("Ventas")).toBeInTheDocument();
    expect(screen.getByText("Inventario")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/features/suggestions",
      expect.anything(),
    );
  });

  it("al elegir una sugerencia manda su prompt al chat y cierra", async () => {
    const recibido = jest.fn();
    window.addEventListener(HELP_ONBOARDING_PROMPT_EVENT, ((e: CustomEvent) =>
      recibido(e.detail.prompt)) as EventListener);
    await abrir();
    await waitFor(() =>
      expect(screen.getByText("Alertas de mañana")).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId("help-onboarding-sugerencia-alertas_faltante"),
    );
    await waitFor(() =>
      expect(screen.queryByTestId("help-onboarding-menu")).toBeNull(),
    );
    await waitFor(() =>
      expect(recibido).toHaveBeenCalledWith(
        "¿Qué productos están en riesgo de faltante mañana?",
      ),
    );
  });

  it("el buscador filtra vistas y sugerencias a la vez", async () => {
    await abrir();
    await waitFor(() =>
      expect(screen.getByText("Tendencia de Refrescos")).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByTestId("help-onboarding-search"), {
      target: { value: "refrescos" },
    });
    expect(screen.getByText("Tendencia de Refrescos")).toBeInTheDocument();
    expect(screen.queryByText("Alertas de mañana")).toBeNull();
    expect(screen.queryByText("Venta del mes")).toBeNull();
  });
});

describe("HelpOnboardingMenu · foco al cerrar (QA, P2.7)", () => {
  // "La ventana de ayuda se quedó encima del chat" y "el botón de enviar no
  // funcionó": al cerrar, headlessui devolvía el foco al botón "?" después de
  // que el compositor lo tomaba; un Enter volvía a abrir la ayuda.
  it("al elegir una pregunta el foco queda en el compositor, no en el botón de ayuda", async () => {
    const compositor = document.createElement("textarea");
    document.body.appendChild(compositor);
    // Así se comporta el compositor real al recibir el prompt.
    const enfocar = () => compositor.focus();
    window.addEventListener(HELP_ONBOARDING_PROMPT_EVENT, enfocar);
    try {
      render(<HelpOnboardingMenu />);
      const trigger = screen.getByTestId("help-onboarding-trigger");
      trigger.focus();
      fireEvent.click(trigger);
      fireEvent.click(
        await screen.findByTestId(
          "help-onboarding-sugerencia-alertas_faltante",
        ),
      );
      await waitFor(() =>
        expect(screen.queryByTestId("help-onboarding-menu")).toBeNull(),
      );
      await new Promise((r) => setTimeout(r, 50));
      expect(document.activeElement).toBe(compositor);
    } finally {
      window.removeEventListener(HELP_ONBOARDING_PROMPT_EVENT, enfocar);
      compositor.remove();
    }
  });
});

describe("HelpOnboardingMenu · iconos", () => {
  it("pinta SVG y no los emojis que trae el catálogo", async () => {
    await abrir();
    await waitFor(() =>
      expect(screen.getByText("Tendencia de Refrescos")).toBeInTheDocument(),
    );
    const menu = screen.getByTestId("help-onboarding-menu");
    for (const emoji of ["🧾", "🚨", "📈"]) {
      expect(menu.textContent).not.toContain(emoji);
    }
    expect(
      screen
        .getByTestId("help-onboarding-prompt-venta_mes")
        .querySelector("svg"),
    ).not.toBeNull();
    expect(
      screen
        .getByTestId("help-onboarding-sugerencia-tendencia_refrescos")
        .querySelector("svg"),
    ).not.toBeNull();
  });
});

describe("HelpOnboardingMenu · sobrevive a que la vista se vuelva a montar (P2.7)", () => {
  it("la ayuda abierta sigue abierta al montar otra vez y la pregunta queda en el borrador", async () => {
    const { unmount } = render(<HelpOnboardingMenu ubicacion="encabezado" />);
    fireEvent.click(screen.getByTestId("help-onboarding-trigger"));
    await waitFor(() =>
      expect(screen.getByTestId("help-onboarding-menu")).toBeInTheDocument(),
    );
    // Un chat nuevo pasa de su id temporal al real: la vista se monta otra vez.
    unmount();
    render(<HelpOnboardingMenu ubicacion="encabezado" />);
    await waitFor(() =>
      expect(screen.getByTestId("help-onboarding-menu")).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByText("Alertas de mañana")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText("Alertas de mañana"));
    expect(useComposerStore.getState().texto).toBeTruthy();
    expect(useComposerStore.getState().chatId).toBeNull();
    await waitFor(() =>
      expect(screen.queryByTestId("help-onboarding-menu")).toBeNull(),
    );
  });

  it("otro botón de ayuda (otra ubicación) no abre un segundo diálogo", async () => {
    render(
      <>
        <HelpOnboardingMenu ubicacion="encabezado" />
        <HelpOnboardingMenu ubicacion="movil" />
      </>,
    );
    fireEvent.click(screen.getAllByTestId("help-onboarding-trigger")[0]);
    await waitFor(() =>
      expect(screen.getAllByTestId("help-onboarding-menu")).toHaveLength(1),
    );
  });
});

