/**
 * Unit tests for MarkdownMessage table rendering
 *
 * Validates that wide markdown tables (many columns) render with
 * horizontal scroll instead of compressing columns to illegible widths.
 *
 * Bug: 2026-02-04__BUG__ui-font-layout-break
 */

import React from "react";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";

// Mock ESM dependencies that Jest cannot parse
jest.mock("react-markdown", () => {
  return function MockReactMarkdown({
    children,
    components,
  }: {
    children: string;
    components: Record<string, React.ComponentType<any>>;
  }) {
    // Parse simple markdown tables to exercise the custom components
    if (children && children.includes("|")) {
      const lines = children.trim().split("\n");
      const headerLine = lines[0];
      const dataLines = lines.slice(2); // skip separator line

      const headers = headerLine
        .split("|")
        .map((h: string) => h.trim())
        .filter(Boolean);
      const rows = dataLines.map((line: string) =>
        line
          .split("|")
          .map((c: string) => c.trim())
          .filter(Boolean),
      );

      const Table = components?.table || "table";
      const Th = components?.th || "th";
      const Td = components?.td || "td";

      return (
        <Table>
          <thead>
            <tr>
              {headers.map((h: string, i: number) => (
                <Th key={i}>{h}</Th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row: string[], ri: number) => (
              <tr key={ri}>
                {row.map((cell: string, ci: number) => (
                  <Td key={ci}>{cell}</Td>
                ))}
              </tr>
            ))}
          </tbody>
        </Table>
      );
    }

    return <div>{children}</div>;
  };
});

jest.mock("remark-gfm", () => () => {});
jest.mock("remark-math", () => () => {});
jest.mock("rehype-katex", () => () => {});
jest.mock("rehype-sanitize", () => () => {});
jest.mock("remend", () => (s: string) => s);
jest.mock("katex/dist/katex.min.css", () => ({}));
jest.mock("../CodeBlock", () => ({
  CodeBlock: ({ children }: { children: ReactNode }) => <pre>{children}</pre>,
  CodeBlockCopyButton: () => null,
  getLanguageFromClassName: () => "text",
}));

import { MarkdownMessage } from "../MarkdownMessage";

describe("MarkdownMessage - Table rendering", () => {
  const smallTable = [
    "| Producto | Valor |",
    "|-------|-------|",
    "| Alfa | 1.60 |",
    "| Beta | 40,142.53 |",
  ].join("\n");

  const wideTable = [
    "| Periodo | C01 | C02 | C03 | C04 | C05 | C06 | C07 | C08 | C09 | C10 | C11 | C12 | C13 | C14 | C15 | C16 | C17 | C18 | C19 |",
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    "| May 2004 | 1.60 | 116,596.08 | 216.27 | 0.00 | 2.67 | 3.13 | 0.00 | 16,987.66 | 0.00 | 40,142.53 | 0.00 | 25,475.83 | 11,839.45 | 189.25 | 68.97 | 29.08 | 0.00 | 2,912.54 | 11,881.93 |",
  ].join("\n");

  it("wraps table in a scrollable container with max-w-full", () => {
    const { container } = render(<MarkdownMessage content={smallTable} />);

    const scrollWrapper = container.querySelector(".overflow-x-auto");
    expect(scrollWrapper).toBeInTheDocument();
    expect(scrollWrapper?.className).toContain("max-w-full");

    const table = scrollWrapper?.querySelector("table");
    expect(table).toBeInTheDocument();
  });

  it("table uses min-w-full to allow expansion beyond container", () => {
    const { container } = render(<MarkdownMessage content={smallTable} />);

    const table = container.querySelector("table");
    expect(table).toBeInTheDocument();
    expect(table?.className).toContain("min-w-full");
    // Must NOT have standalone w-full (only min-w-full is acceptable)
    expect(table?.className).not.toMatch(/(?<![-\w])w-full(?![-\w])/);
  });

  it("table headers have whitespace-nowrap to prevent vertical text", () => {
    const { container } = render(<MarkdownMessage content={smallTable} />);

    const headers = container.querySelectorAll("th");
    expect(headers.length).toBe(2);

    headers.forEach((th) => {
      expect(th.className).toContain("whitespace-nowrap");
    });
  });

  it("table cells have whitespace-nowrap for numeric data readability", () => {
    const { container } = render(<MarkdownMessage content={smallTable} />);

    const cells = container.querySelectorAll("td");
    expect(cells.length).toBe(4);

    cells.forEach((td) => {
      expect(td.className).toContain("whitespace-nowrap");
    });
  });

  // feedback round 1 (2026-10-16, punto 7): en la tabla de alertas
  // la columna "Razón" no partía renglón y la tabla se salía de la burbuja
  // sin ninguna señal de que había más.
  it("una celda de texto largo parte renglón; los números no", () => {
    const tablaAlertas = [
      "| Producto | Venta en riesgo | Razón principal |",
      "|---|---|---|",
      "| Tequila Don Julio Anejo Cristalino 700 M | $425.58 | Quedan 49 piezas, para unos 31 días de venta, y vendió 6 en la última semana |",
    ].join("\n");
    const { container } = render(<MarkdownMessage content={tablaAlertas} />);

    const celdas = Array.from(container.querySelectorAll("td"));
    const razon = celdas[2];
    const monto = celdas[1];
    expect(razon.className).not.toContain("whitespace-nowrap");
    expect(razon.className).toContain("whitespace-normal");
    expect(monto.className).toContain("whitespace-nowrap");
  });

  it("el contenedor de la tabla muestra su barra y su borde", () => {
    const { container } = render(<MarkdownMessage content={smallTable} />);
    const wrapper = container.querySelector(".overflow-x-auto");
    expect(wrapper?.className).toContain("thin-scroll");
    expect(wrapper?.className).toContain("border");
  });

  it("renders a wide table (20 columns) without errors", () => {
    const { container } = render(<MarkdownMessage content={wideTable} />);

    const table = container.querySelector("table");
    expect(table).toBeInTheDocument();

    const headers = container.querySelectorAll("th");
    expect(headers.length).toBe(20);

    // All headers should have nowrap
    headers.forEach((th) => {
      expect(th.className).toContain("whitespace-nowrap");
    });
  });
});
