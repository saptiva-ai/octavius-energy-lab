/**
 * Los importes en pesos no son fórmulas: "$36,109.50; utilidad bruta $7,253.09"
 * se renderizaba como math inline (visto en producción 2026-09-03).
 *
 * Card: 2026-09-03__FIX__markdown-chat-pesos-como-latex
 */

import { normalizeLatexSyntax } from "@/lib/markdown-normalize";

describe("normalizeLatexSyntax: importes en pesos", () => {
  it("escapa el $ de dinero para que remark-math no lo tome como fórmula", () => {
    const texto =
      "Total del periodo: 1727 unidades ($36,109.50; utilidad bruta $7,253.09).";
    expect(normalizeLatexSyntax(texto)).toBe(
      "Total del periodo: 1727 unidades (\\$36,109.50; utilidad bruta \\$7,253.09).",
    );
  });

  it("escapa también un importe al inicio del texto", () => {
    expect(normalizeLatexSyntax("$1,420 MDP en riesgo")).toBe(
      "\\$1,420 MDP en riesgo",
    );
  });

  it("no toca un $ ya escapado ni el display math $$", () => {
    expect(normalizeLatexSyntax("vale \\$12")).toBe("vale \\$12");
    expect(normalizeLatexSyntax("$$x^2$$")).toBe("$$x^2$$");
  });

  it("sigue convirtiendo \\( \\) en inline math", () => {
    expect(normalizeLatexSyntax("\\(a+b\\)")).toBe("$a+b$");
  });
});
