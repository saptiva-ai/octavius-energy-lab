/**
 * Review Command Detector
 *
 * Detecta comandos de usuario para iniciar revisión de documentos
 * y evita que se envíen al chat LLM
 */

export interface ReviewCommandMatch {
  isReviewCommand: boolean;
  action: "review" | "summarize" | null;
  filename?: string;
}

/**
 * Detecta si un mensaje es un comando de revisión de documentos
 *
 * Patrones detectados:
 * - "revisar documento"
 * - "revisar tipografia_esp.pdf"
 * - "resumir documento"
 * - "resumir el documento"
 * - "revisa este documento"
 * - "haz un resumen del documento"
 */
export function detectReviewCommand(text: string): ReviewCommandMatch {
  const trimmed = text.trim().toLowerCase();

  // Patrones de revisión
  const reviewPatterns = [
    /^\s*(revisar?|revisa|revise)\s+(este|el)?\s*(documento|pdf|archivo)/i,
    /^\s*(revisar?|revisa|revise)\s+([a-zA-Z0-9_\-\.]+\.pdf)/i,
    /^\s*(hacer?|haz)\s+una\s+revisi[oó]n\s+(del?|de\s+este)?\s*(documento|pdf)/i,
  ];

  // Patrones de resumen
  const summaryPatterns = [
    /^\s*(resumir?|resume|resuma)\s+(este|el)?\s*(documento|pdf|archivo)/i,
    /^\s*(resumir?|resume|resuma)\s+([a-zA-Z0-9_\-\.]+\.pdf)/i,
    /^\s*(hacer?|haz)\s+un\s+resumen\s+(del?|de\s+este)?\s*(documento|pdf)/i,
    /^\s*dame\s+un\s+resumen\s+(del?|de\s+este)?\s*(documento|pdf)/i,
  ];

  // Check review patterns
  for (const pattern of reviewPatterns) {
    const match = trimmed.match(pattern);
    if (match) {
      const filename = match[2]?.match(/\.pdf$/i) ? match[2] : undefined;
      return {
        isReviewCommand: true,
        action: "review",
        filename,
      };
    }
  }

  // Check summary patterns
  for (const pattern of summaryPatterns) {
    const match = trimmed.match(pattern);
    if (match) {
      const filename = match[2]?.match(/\.pdf$/i) ? match[2] : undefined;
      return {
        isReviewCommand: true,
        action: "summarize",
        filename,
      };
    }
  }

  return {
    isReviewCommand: false,
    action: null,
  };
}
