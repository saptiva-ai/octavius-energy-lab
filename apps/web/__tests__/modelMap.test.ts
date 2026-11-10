/**
 * Tests for model mapping logic
 *
 * These tests verify the fuzzy matching between backend model names
 * and the UI catalog, ensuring robust handling of inconsistent casing
 * and naming variations from the backend.
 */

// Note: These tests are designed for Jest/Vitest. Run with: pnpm test
// If using TypeScript without test runner, comment out the imports below
import {
  findUiModelByBackendName,
  buildModelList,
  getDefaultModelSlug,
  isValidSlug,
} from "../src/lib/modelMap";
import { MODEL_CATALOG } from "../src/config/modelCatalog";

describe("modelMap - findUiModelByBackendName", () => {
  describe("Exact alias matching (case-insensitive)", () => {
    it('should match "Saptiva Turbo" to turbo', () => {
      const result = findUiModelByBackendName("Saptiva Turbo");
      expect(result?.slug).toBe("turbo");
    });

    it('should match "saptiva turbo" (lowercase) to turbo', () => {
      const result = findUiModelByBackendName("saptiva turbo");
      expect(result?.slug).toBe("turbo");
    });

    it('should match "SAPTIVA TURBO" (uppercase) to turbo', () => {
      const result = findUiModelByBackendName("SAPTIVA TURBO");
      expect(result?.slug).toBe("turbo");
    });

    it('should match "Saptiva Cortex" to cortex', () => {
      const result = findUiModelByBackendName("Saptiva Cortex");
      expect(result?.slug).toBe("cortex");
    });

    it('should match "Saptiva Ops" to ops', () => {
      const result = findUiModelByBackendName("Saptiva Ops");
      expect(result?.slug).toBe("ops");
    });
  });

  describe("Normalized matching (underscores, hyphens)", () => {
    it('should match "saptiva-turbo" (hyphen) to turbo', () => {
      const result = findUiModelByBackendName("saptiva-turbo");
      expect(result?.slug).toBe("turbo");
    });

    it('should match "saptiva_turbo" (underscore) to turbo', () => {
      const result = findUiModelByBackendName("saptiva_turbo");
      expect(result?.slug).toBe("turbo");
    });

    it('should match "sap_turbo" (shortened underscore) to turbo', () => {
      const result = findUiModelByBackendName("sap_turbo");
      expect(result?.slug).toBe("turbo");
    });

    it('should match "SAPTIVA_CORTEX" (uppercase underscore) to cortex', () => {
      const result = findUiModelByBackendName("SAPTIVA_CORTEX");
      expect(result?.slug).toBe("cortex");
    });

    it('should match "saptiva-ops" (hyphen) to ops', () => {
      const result = findUiModelByBackendName("saptiva-ops");
      expect(result?.slug).toBe("ops");
    });
  });

  describe("Partial matching (contains slug)", () => {
    it('should match "turbo" (short name) to turbo', () => {
      const result = findUiModelByBackendName("turbo");
      expect(result?.slug).toBe("turbo");
    });

    it('should match "cortex" (short name) to cortex', () => {
      const result = findUiModelByBackendName("cortex");
      expect(result?.slug).toBe("cortex");
    });

    it('should match "ops" (short name) to ops', () => {
      const result = findUiModelByBackendName("ops");
      expect(result?.slug).toBe("ops");
    });

    it('should match "Saptiva  Turbo" (extra spaces) to turbo', () => {
      const result = findUiModelByBackendName("Saptiva  Turbo");
      expect(result?.slug).toBe("turbo");
    });
  });

  describe("Unknown models", () => {
    it("should return null for unknown model name", () => {
      const result = findUiModelByBackendName("Unknown Model");
      expect(result).toBeNull();
    });

    it("should return null for empty string", () => {
      const result = findUiModelByBackendName("");
      expect(result).toBeNull();
    });

    it("should return null for completely unrelated name", () => {
      const result = findUiModelByBackendName("GPT-4");
      expect(result).toBeNull();
    });
  });

  describe("Edge cases", () => {
    it("should handle mixed case with special characters", () => {
      const result = findUiModelByBackendName("SaPtIvA_TuRbO");
      expect(result?.slug).toBe("turbo");
    });

    it("should handle trailing/leading whitespace", () => {
      const result = findUiModelByBackendName("  Saptiva Turbo  ");
      expect(result?.slug).toBe("turbo");
    });
  });
});

describe("modelMap - buildModelList", () => {
  // Contrato: /api/models es la FUENTE DE VERDAD. El catálogo local solo
  // aporta presentación. Regresión cubierta: con el catálogo como fuente, al
  // migrar el gateway a InferNode el selector mostraba modelos Saptiva
  // inexistentes y ocultaba los reales.
  it("lista exactamente los modelos que ofrece el backend", () => {
    const backendModels = ["Saptiva Turbo", "Saptiva Cortex"];
    const result = buildModelList(backendModels);

    expect(result).toHaveLength(backendModels.length);
    expect(result.every((item) => item.available)).toBe(true);
    expect(result.map((item) => item.backendId)).toEqual(backendModels);
  });

  it("NO incluye modelos del catálogo que el backend no ofrece", () => {
    const result = buildModelList(["Saptiva Turbo"]);

    expect(result).toHaveLength(1);
    expect(result.map((m) => m.model.slug)).not.toContain("cortex");
    expect(result[0]?.backendId).toBe("Saptiva Turbo");
  });

  it("incluye modelos desconocidos usando su id tal cual", () => {
    const result = buildModelList(["qwen3.6-35b-a3b-fp8"]);

    expect(result).toHaveLength(1);
    // No se inventa un nombre "bonito": enviar un id inexistente fue lo que
    // rompió el chat (model_not_found).
    expect(result[0]?.model.slug).toBe("qwen3.6-35b-a3b-fp8");
    expect(result[0]?.model.displayName).toBe("qwen3.6-35b-a3b-fp8");
    expect(result[0]?.model.badges).toEqual([]);
    expect(result[0]?.available).toBe(true);
  });

  it("should handle case-insensitive backend names", () => {
    const backendModels = ["saptiva turbo", "SAPTIVA_CORTEX"];
    const result = buildModelList(backendModels);

    const turbo = result.find((m) => m.model.slug === "turbo");
    const cortex = result.find((m) => m.model.slug === "cortex");

    expect(turbo?.available).toBe(true);
    expect(turbo?.backendId).toBe("saptiva turbo");

    expect(cortex?.available).toBe(true);
    expect(cortex?.backendId).toBe("SAPTIVA_CORTEX");
  });

  it("preserva el orden que envía el backend", () => {
    const backendModels = ["gemma-4-26b", "Saptiva Turbo", "qwen3.6-27b-fp8"];

    expect(buildModelList(backendModels).map((m) => m.backendId)).toEqual(
      backendModels,
    );
  });

  it("con backend vacío devuelve lista vacía", () => {
    expect(buildModelList([])).toEqual([]);
  });
});

describe("modelMap - getDefaultModelSlug", () => {
  it('should return correct slug for "Saptiva Turbo"', () => {
    const result = getDefaultModelSlug("Saptiva Turbo");
    expect(result).toBe("turbo");
  });

  it('should return correct slug for "saptiva cortex"', () => {
    const result = getDefaultModelSlug("saptiva cortex");
    expect(result).toBe("cortex");
  });

  it('should return correct slug for "SAPTIVA_OPS"', () => {
    const result = getDefaultModelSlug("SAPTIVA_OPS");
    expect(result).toBe("ops");
  });

  it("devuelve el id del backend cuando el catálogo no lo conoce", () => {
    // Debe ser SELECCIONABLE: el slug tiene que coincidir con el que produce
    // buildModelList para ese mismo id.
    const result = getDefaultModelSlug("qwen3.6-35b-a3b-fp8");
    expect(result).toBe("qwen3.6-35b-a3b-fp8");

    const lista = buildModelList(["qwen3.6-35b-a3b-fp8", "gemma-4-26b"]);
    expect(lista.some((m) => m.model.slug === result && m.available)).toBe(
      true,
    );
  });

  it("should fallback to first catalog model for null", () => {
    const result = getDefaultModelSlug(null);
    expect(result).toBe(MODEL_CATALOG[0]?.slug || "turbo");
  });

  it("should fallback to first catalog model for empty string", () => {
    const result = getDefaultModelSlug("");
    expect(result).toBe(MODEL_CATALOG[0]?.slug || "turbo");
  });
});

describe("modelMap - isValidSlug", () => {
  it("should return true for valid slugs", () => {
    expect(isValidSlug("turbo")).toBe(true);
    expect(isValidSlug("cortex")).toBe(true);
    expect(isValidSlug("ops")).toBe(true);
    expect(isValidSlug("legacy")).toBe(true);
  });

  it("should return false for invalid slugs", () => {
    expect(isValidSlug("invalid")).toBe(false);
    expect(isValidSlug("gpt-4")).toBe(false);
    expect(isValidSlug("")).toBe(false);
  });
});

describe("Integration tests - Full workflow", () => {
  it("mapea nombres del backend a la UI conservando el id exacto", () => {
    // Backend con convenciones de nombre variadas (las que el catálogo conoce).
    const backendModels = [
      "Saptiva Turbo",
      "saptiva_cortex",
      "SAPTIVA-OPS",
      "Saptiva Legacy",
    ];

    const modelList = buildModelList(backendModels);

    expect(modelList).toHaveLength(backendModels.length);
    expect(modelList.every((m) => m.available)).toBe(true);

    expect(modelList.find((m) => m.model.slug === "turbo")?.backendId).toBe(
      "Saptiva Turbo",
    );
    expect(modelList.find((m) => m.model.slug === "cortex")?.backendId).toBe(
      "saptiva_cortex",
    );
    expect(modelList.find((m) => m.model.slug === "ops")?.backendId).toBe(
      "SAPTIVA-OPS",
    );
    expect(modelList.find((m) => m.model.slug === "legacy")?.backendId).toBe(
      "Saptiva Legacy",
    );
  });

  it("gateway nuevo: se muestran sus modelos y ninguno del catálogo viejo", () => {
    // Escenario real de la migración a InferNode.
    const backendModels = ["qwen3.6-35b-a3b-fp8", "gemma-4-26b"];

    const modelList = buildModelList(backendModels);
    const defaultSlug = getDefaultModelSlug("qwen3.6-35b-a3b-fp8");

    expect(modelList.map((m) => m.backendId)).toEqual(backendModels);
    expect(modelList.every((m) => m.available)).toBe(true);
    // Ningún modelo Saptiva del catálogo local se cuela.
    expect(modelList.map((m) => m.model.slug)).not.toContain("turbo");
    // El default del backend es seleccionable y resuelve a un id real.
    const seleccionado = modelList.find((m) => m.model.slug === defaultSlug);
    expect(seleccionado?.backendId).toBe("qwen3.6-35b-a3b-fp8");
  });
});
