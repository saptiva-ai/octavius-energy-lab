/**
 * Normaliza el texto antes de pasarlo por remark-math.
 *
 * - Importes en pesos: "$36,109.50; utilidad bruta $7,253.09" se leía como
 *   fórmula inline (remark-math toma el tramo entre dos `$` como math) y el
 *   chat mostraba "(36,109.50; utilidadbruta7,253.09)" en cursiva (visto en
 *   producción 2026-09-03). Un `$` seguido de dígito es dinero, nunca LaTeX:
 *   se escapa antes de convertir delimitadores.
 * - \[ ... \] -> $$ ... $$ (display math)
 * - \( ... \) -> $ ... $ (inline math)
 * - [ ... ] -> $$ ... $$ solo si claramente es una ecuación LaTeX
 *
 * Vive fuera del componente para poder probarse sin montar react-markdown.
 */
export function normalizeLatexSyntax(content: string): string {
  let normalized = content;

  normalized = normalized.replace(/(^|[^\\$])\$(?=\d)/g, "$1\\$");

  // Convert \[ ... \] to $$ ... $$ (display math)
  // Use a function to avoid issues with $ special characters in replacement string
  normalized = normalized.replace(/\\\[([\s\S]*?)\\\]/g, (_match, equation) => {
    return `$$${equation}$$`;
  });

  // Convert \( ... \) to $ ... $ (inline math)
  normalized = normalized.replace(/\\\(([\s\S]*?)\\\)/g, (_match, equation) => {
    return `$${equation}$`;
  });

  // Convert standalone [ ... ] to $$ ... $$ (display math)
  // VERY conservative: only match if at start of line (not after any other content)
  // and equation contains LaTeX commands
  normalized = normalized.replace(
    /^\s*\[([\s\S]*?)\]\s*$/gm,
    (match, equation) => {
      // Must contain LaTeX commands to be considered an equation
      // Look for: backslash commands (\frac, \alpha, etc), subscripts, superscripts, braces
      const hasLatexCommands = /\\[a-zA-Z]{2,}|[_^{]/.test(equation);
      const hasMultipleSymbols =
        (equation.match(/\\[a-zA-Z]+/g) || []).length >= 2;

      // Only convert if it clearly looks like a LaTeX equation
      if (hasLatexCommands && hasMultipleSymbols) {
        return `$$${equation}$$\n`;
      }

      // Otherwise keep original
      return match;
    },
  );

  return normalized;
}
