/**
 * Unit tests for conversation utilities
 *
 * NOTE: deriveTitleLocal filters ALL stopwords (not just leading),
 * has a 40-char limit, and limits to 6 words max.
 */

import {
  deriveTitleLocal,
  generateTitleFromMessage,
} from "../conversation-utils";

describe("deriveTitleLocal", () => {
  it("should capitalize first letter and filter stopwords", () => {
    // 'cómo' is stopword (NOT 'el' which is not in list)
    expect(deriveTitleLocal("cómo configurar el servidor")).toBe(
      "Configurar el servidor",
    );
  });

  it("should remove final punctuation and filter stopwords", () => {
    // 'qué' and 'es' are stopwords (case-insensitive)
    expect(deriveTitleLocal("Qué es machine learning?")).toBe(
      "Machine learning",
    );
    // 'explícame' is stopword, 'sobre' is not
    expect(deriveTitleLocal("Explícame sobre APIs.")).toBe("Sobre APIs");
    // Punctuation ¿ stays attached to word, so '¿Cómo' != stopword 'cómo'
    expect(deriveTitleLocal("¿Cómo funciona?!...")).toBe("¿Cómo funciona");
  });

  it("should filter all stopwords (not just leading)", () => {
    // 'hola', 'cómo', 'está' are stopwords (NOT 'el')
    expect(deriveTitleLocal("hola cómo está el clima")).toBe("El clima");
    // 'ayuda', 'por', 'favor' are stopwords
    expect(deriveTitleLocal("ayuda por favor con este error")).toBe(
      "Con este error",
    );
    // 'necesito' and 'ayuda' are both stopwords
    expect(deriveTitleLocal("necesito ayuda urgente")).toBe("Urgente");
  });

  it("should handle markdown formatting", () => {
    // Markdown stripped, stopwords filtered but punctuation marks preserved
    expect(deriveTitleLocal("**¿Qué** es _Python_?")).toBe("¿Qué Python");
    // 'en' is not in stopwords
    expect(deriveTitleLocal("`código` en ##markdown")).toBe(
      "Código en markdown",
    );
  });

  it("should limit to 40 characters with word truncation", () => {
    // Should limit to ~40 chars, truncating at word boundary
    const longText =
      "Este es un texto muy largo que definitivamente excede los setenta caracteres permitidos para el título";
    const result = deriveTitleLocal(longText);
    expect(result.length).toBeLessThanOrEqual(43); // 40 + '...'
    // Actual output keeps first 6 words within 40 char limit
    expect(result).toBe("Este un texto muy largo definitivamente");
  });

  it("should take only first line", () => {
    const multiline = "Primera línea importante\nSegunda línea\nTercera línea";
    expect(deriveTitleLocal(multiline)).toBe("Primera línea importante");
  });

  it("should return fallback for empty or all-stopword input", () => {
    expect(deriveTitleLocal("")).toBe("Nueva conversación");
    expect(deriveTitleLocal("   ")).toBe("Nueva conversación");
    expect(deriveTitleLocal("hola")).toBe("Nueva conversación"); // all stopwords
    expect(deriveTitleLocal("ok")).toBe("Nueva conversación"); // too short after processing
  });

  it("should handle mixed stopwords correctly", () => {
    // 'gracias', 'por', 'la', 'ayuda' are ALL stopwords -> fallback
    expect(deriveTitleLocal("gracias por la ayuda")).toBe("Nueva conversación");
    // 'hey', 'how', 'are' are stopwords
    expect(deriveTitleLocal("hey there how are you")).toBe("There you");
  });

  it("should normalize whitespace", () => {
    expect(deriveTitleLocal("texto   con    espacios    múltiples")).toBe(
      "Texto con espacios múltiples",
    );
  });

  it("should preserve non-stopword content", () => {
    // 'de' is not explicitly in stopwords
    expect(deriveTitleLocal("máquinas de aprendizaje profundo")).toBe(
      "Máquinas de aprendizaje profundo",
    );
    expect(deriveTitleLocal("API REST con autenticación")).toBe(
      "API REST con autenticación",
    );
  });

  it("should handle special characters in names and filter stopwords", () => {
    // 'es' is stopword but 'quién' is NOT (who in English is, but not quien)
    expect(deriveTitleLocal("¿Quién es Ángel Cisneros?")).toBe(
      "¿Quién Ángel Cisneros",
    );
    expect(deriveTitleLocal("José María Pérez")).toBe("José María Pérez");
  });

  it("should filter stopwords even from normal text", () => {
    // 'el', 'del', 'es' are stopwords (or 'del' is kept as 'de' + 'el')
    const normalText = "El resumen del artículo es interesante";
    const result = deriveTitleLocal(normalText);
    // 'el', 'es' are stopwords, 'del' contains 'el'
    expect(result).toBe("El resumen del artículo interesante");
  });

  it("should limit to maximum 6 words", () => {
    // Even if under 40 chars, should limit to 6 words
    const manyWords = "uno dos tres cuatro cinco seis siete ocho";
    const result = deriveTitleLocal(manyWords);
    const wordCount = result.replace("...", "").split(" ").length;
    expect(wordCount).toBeLessThanOrEqual(6);
  });
});

describe("generateTitleFromMessage", () => {
  it("should return local title without calling API when local quality is good", async () => {
    const text = "cómo configurar el servidor de staging para qa";
    const apiClient = {
      generateTitle: jest.fn().mockResolvedValue({ title: "Título remoto" }),
    };

    const result = await generateTitleFromMessage(text, apiClient);

    expect(result).toBe(deriveTitleLocal(text));
    expect(apiClient.generateTitle).not.toHaveBeenCalled();
  });

  it("should call API when local title falls back to default", async () => {
    const text = "hola";
    const apiClient = {
      generateTitle: jest.fn().mockResolvedValue({ title: "Consulta inicial" }),
    };

    const result = await generateTitleFromMessage(text, apiClient);

    expect(apiClient.generateTitle).toHaveBeenCalledTimes(1);
    expect(apiClient.generateTitle).toHaveBeenCalledWith(text);
    expect(result).toBe("Consulta inicial");
  });

  it("should call API when local title is too short", async () => {
    const text = "necesito ayuda urgente";
    const apiClient = {
      generateTitle: jest
        .fn()
        .mockResolvedValue({ title: "Error urgente de autenticación" }),
    };

    const result = await generateTitleFromMessage(text, apiClient);

    expect(apiClient.generateTitle).toHaveBeenCalledTimes(1);
    expect(result).toBe("Error urgente de autenticación");
  });

  it("should fallback to local title when API fails", async () => {
    const text = "hola";
    const apiClient = {
      generateTitle: jest.fn().mockRejectedValue(new Error("network")),
    };
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});

    const result = await generateTitleFromMessage(text, apiClient);

    expect(apiClient.generateTitle).toHaveBeenCalledTimes(1);
    expect(result).toBe(deriveTitleLocal(text));
    warnSpy.mockRestore();
  });

  it("should fallback to local title when API returns empty title", async () => {
    const text = "hola";
    const apiClient = {
      generateTitle: jest.fn().mockResolvedValue({ title: "   " }),
    };

    const result = await generateTitleFromMessage(text, apiClient);

    expect(apiClient.generateTitle).toHaveBeenCalledTimes(1);
    expect(result).toBe(deriveTitleLocal(text));
  });

  it("should truncate long API titles to 40 characters", async () => {
    const text = "hola";
    const apiClient = {
      generateTitle: jest.fn().mockResolvedValue({
        title:
          "Título extremadamente largo que supera por mucho el límite visual de la barra lateral",
      }),
    };

    const result = await generateTitleFromMessage(text, apiClient);

    expect(apiClient.generateTitle).toHaveBeenCalledTimes(1);
    expect(result.length).toBeLessThanOrEqual(40);
    expect(result.endsWith("...")).toBe(true);
  });
});
