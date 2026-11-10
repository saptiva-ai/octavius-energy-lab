/**
 * Indicador de "preparando la respuesta" (Equipo, 2026-10-21). Primero fueron
 * barras verdes sin texto ("parece señal de celular"); ahora el ícono cambia
 * según el tema de la consulta y una frase corta con brillo dice qué hace.
 */
import { act, render, screen } from "@testing-library/react";

import type { TemaEspera } from "../../../lib/espera-por-consulta";
import { TypingIndicator } from "../TypingIndicator";

describe("TypingIndicator", () => {
  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it("sin aviso del backend: anillo, 'Pensando' para lectores y el primer paso a la vista", () => {
    render(<TypingIndicator />);
    expect(screen.getByRole("status")).toHaveAccessibleName("Pensando");
    expect(screen.getByText("Pensando")).toHaveClass("sr-only");
    const visible = screen.getByText("Saptivating…");
    expect(visible).toHaveClass("indicador-brillo");
    expect(visible).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByTestId("icono-espera")).toHaveAttribute("data-tema", "generico");
    expect(screen.queryByText(/generando respuesta|analizando con/i)).toBeNull();
  });

  // Equipo (2026-10-21): "en orden": los pasos avanzan uno tras otro y se
  // quedan en el último; no se sortean ni vuelven a empezar.
  it("avanza los pasos en orden cada 2.5 s y se queda en el último", () => {
    jest.useFakeTimers();
    const pasos = ["Consultando la venta…", "Sumando los tickets…", "Cuadrando la caja…"];
    render(
      <TypingIndicator espera={{ tema: "ventas", frase: "Consultando ventas", frases: pasos }} />,
    );
    expect(screen.getByTestId("icono-espera")).toHaveAttribute("data-tema", "ventas");
    expect(screen.getByText(pasos[0])).toBeVisible();

    act(() => {
      jest.advanceTimersByTime(2500);
    });
    expect(screen.getByText(pasos[1])).toBeVisible();
    act(() => {
      jest.advanceTimersByTime(2500);
    });
    expect(screen.getByText(pasos[2])).toBeVisible();
    act(() => {
      jest.advanceTimersByTime(10000);
    });
    expect(screen.getByText(pasos[2])).toBeVisible();
    expect(screen.getByRole("status")).toHaveAccessibleName("Consultando ventas");
  });

  it("al cambiar de paso del turno vuelve al primer mensaje del nuevo", () => {
    jest.useFakeTimers();
    const { rerender } = render(
      <TypingIndicator
        espera={{ tema: "ventas", frase: "Consultando ventas", frases: ["A…", "B…"] }}
      />,
    );
    act(() => {
      jest.advanceTimersByTime(2500);
    });
    expect(screen.getByText("B…")).toBeVisible();

    rerender(
      <TypingIndicator
        espera={{ tema: "ventas", frase: "Redactando la respuesta", frases: ["C…", "D…"] }}
      />,
    );
    expect(screen.getByText("C…")).toBeVisible();
    expect(screen.getByRole("status")).toHaveAccessibleName("Redactando la respuesta");
  });

  it("sin frases chistosas muestra la frase normal", () => {
    render(<TypingIndicator espera={{ tema: "ayuda", frase: "Un momento", frases: [] }} />);
    expect(screen.getAllByText("Un momento").length).toBeGreaterThan(0);
  });

  it.each<TemaEspera>(["generico", "ventas", "ranking", "inventario", "riesgo", "ayuda"])(
    "el ícono de %s es decorativo y no lo leen los lectores de pantalla",
    (tema) => {
      render(<TypingIndicator espera={{ tema, frase: "Un momento", frases: [] }} />);
      const icono = screen.getByTestId("icono-espera");
      expect(icono).toHaveAttribute("data-tema", tema);
      expect(icono).toHaveAttribute("aria-hidden", "true");
      expect(icono.getAttribute("class")).toMatch(/indicador-espera/);
    },
  );

  it("ya no dibuja las barras de señal en las consultas que no son ranking", () => {
    render(
      <TypingIndicator espera={{ tema: "ventas", frase: "Consultando ventas", frases: [] }} />,
    );
    expect(screen.queryAllByTestId("indicador-barra")).toHaveLength(0);
  });
});
