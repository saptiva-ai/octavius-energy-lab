/**
 * Tests for Model Catalog Configuration
 *
 * Verifica que el catálogo de modelos esté correctamente configurado
 * con la estructura esperada y los campos requeridos.
 */

import {
  MODEL_CATALOG,
  getModelBySlug,
  getAllModels,
  type UiModel,
} from "../src/config/modelCatalog";

describe("Model Catalog Configuration", () => {
  describe("Model catalog structure", () => {
    it("should be an array", () => {
      expect(Array.isArray(MODEL_CATALOG)).toBe(true);
    });

    it("should have all expected models", () => {
      const expectedSlugs = ["turbo", "cortex", "ops"];
      const actualSlugs = MODEL_CATALOG.map((m) => m.slug);

      expectedSlugs.forEach((slug) => {
        expect(actualSlugs).toContain(slug);
      });
    });

    it("should have required fields for each model", () => {
      MODEL_CATALOG.forEach((model) => {
        expect(model).toHaveProperty("slug");
        expect(model).toHaveProperty("displayName");
        expect(model).toHaveProperty("description");
        expect(model).toHaveProperty("badges");
        expect(model).toHaveProperty("order");
        expect(model).toHaveProperty("aliases");
      });
    });

    it("should have unique slugs", () => {
      const slugs = MODEL_CATALOG.map((m) => m.slug);
      const uniqueSlugs = new Set(slugs);

      expect(slugs.length).toBe(uniqueSlugs.size);
    });

    it("should have non-empty descriptions", () => {
      MODEL_CATALOG.forEach((model) => {
        expect(model.description.length).toBeGreaterThan(0);
      });
    });
  });

  describe("Turbo model configuration", () => {
    const turbo = MODEL_CATALOG.find((m) => m.slug === "turbo");

    it("should exist", () => {
      expect(turbo).toBeDefined();
    });

    it("should have correct displayName", () => {
      expect(turbo?.displayName).toBe("Saptiva Turbo");
    });

    it("should have aliases", () => {
      expect(turbo?.aliases).toContain("Saptiva Turbo");
      expect(turbo?.aliases).toContain("saptiva_turbo");
      expect(turbo?.aliases).toContain("SAPTIVA_TURBO");
      expect(turbo?.aliases).toContain("turbo");
    });

    it("should have speed-related characteristics", () => {
      const description = turbo?.description.toLowerCase() || "";
      expect(
        description.includes("rápid") ||
          description.includes("veloz") ||
          description.includes("eficiente"),
      ).toBe(true);
    });

    it("should have FAST badge", () => {
      expect(turbo?.badges).toContain("FAST");
    });
  });

  describe("Cortex model configuration", () => {
    const cortex = MODEL_CATALOG.find((m) => m.slug === "cortex");

    it("should exist", () => {
      expect(cortex).toBeDefined();
    });

    it("should have correct displayName", () => {
      expect(cortex?.displayName).toBe("Saptiva Cortex");
    });

    it("should have aliases", () => {
      expect(cortex?.aliases).toContain("Saptiva Cortex");
      expect(cortex?.aliases).toContain("saptiva_cortex");
      expect(cortex?.aliases).toContain("SAPTIVA_CORTEX");
      expect(cortex?.aliases).toContain("cortex");
    });

    it("should have analysis-related characteristics", () => {
      const description = cortex?.description.toLowerCase() || "";
      expect(
        description.includes("análisis") ||
          description.includes("profundo") ||
          description.includes("razonamiento"),
      ).toBe(true);
    });

    it("should have REASONING badge", () => {
      expect(cortex?.badges).toContain("REASONING");
    });
  });

  describe("Ops model configuration", () => {
    const ops = MODEL_CATALOG.find((m) => m.slug === "ops");

    it("should exist", () => {
      expect(ops).toBeDefined();
    });

    it("should have correct displayName", () => {
      expect(ops?.displayName).toBe("Saptiva Ops");
    });

    it("should have aliases", () => {
      expect(ops?.aliases).toContain("Saptiva Ops");
      expect(ops?.aliases).toContain("saptiva_ops");
      expect(ops?.aliases).toContain("SAPTIVA_OPS");
      expect(ops?.aliases).toContain("ops");
    });

    it("should have operations-related characteristics", () => {
      const description = ops?.description.toLowerCase() || "";
      expect(
        description.includes("operativas") ||
          description.includes("operaciones") ||
          description.includes("concisas") ||
          description.includes("tareas"),
      ).toBe(true);
    });

    it("should have CHAT badge", () => {
      expect(ops?.badges).toContain("CHAT");
    });
  });

  describe("Model aliases for fuzzy matching", () => {
    it("should support case-insensitive matching", () => {
      MODEL_CATALOG.forEach((model) => {
        expect(model.aliases).toBeDefined();
        expect(Array.isArray(model.aliases)).toBe(true);
        expect(model.aliases.length).toBeGreaterThan(0);
      });
    });

    it("should include variations with underscores", () => {
      MODEL_CATALOG.forEach((model) => {
        const hasUnderscore = model.aliases.some((alias) =>
          alias.includes("_"),
        );
        expect(hasUnderscore).toBe(true);
      });
    });

    it("should include proper case variations", () => {
      MODEL_CATALOG.forEach((model) => {
        const hasProperCase = model.aliases.some(
          (alias) => alias.includes(" ") && alias[0] === alias[0].toUpperCase(),
        );
        expect(hasProperCase).toBe(true);
      });
    });
  });

  describe("Badge configuration", () => {
    it("should have valid badges for each model", () => {
      const validBadges = ["CORE", "REASONING", "CHAT", "FAST", "EXPERIMENTAL"];

      MODEL_CATALOG.forEach((model) => {
        expect(model.badges.length).toBeGreaterThan(0);
        model.badges.forEach((badge) => {
          expect(validBadges).toContain(badge);
        });
      });
    });

    it("should have CORE badge for all main models", () => {
      MODEL_CATALOG.forEach((model) => {
        expect(model.badges).toContain("CORE");
      });
    });
  });
});

describe("Model Selection Logic", () => {
  describe("Model lookup functions", () => {
    it("should find model by slug", () => {
      const turbo = getModelBySlug("turbo");
      expect(turbo).toBeDefined();
      expect(turbo?.slug).toBe("turbo");
    });

    it("should return undefined for non-existent slug", () => {
      const nonExistent = getModelBySlug("nonexistent");
      expect(nonExistent).toBeUndefined();
    });

    it("should get all models sorted by order", () => {
      const allModels = getAllModels();
      expect(allModels.length).toBe(MODEL_CATALOG.length);

      // Verify sorted by order
      for (let i = 1; i < allModels.length; i++) {
        expect(allModels[i].order).toBeGreaterThanOrEqual(
          allModels[i - 1].order,
        );
      }
    });
  });

  describe("Model validation", () => {
    it("should validate slug format", () => {
      const validSlugPattern = /^[a-z]+$/;

      MODEL_CATALOG.forEach((model) => {
        expect(model.slug).toMatch(validSlugPattern);
      });
    });

    it("should have unique order values", () => {
      const orders = MODEL_CATALOG.map((m) => m.order);
      const uniqueOrders = new Set(orders);

      expect(orders.length).toBe(uniqueOrders.size);
    });
  });
});

describe("Model Metadata", () => {
  describe("Display information", () => {
    it("should have user-friendly display names", () => {
      MODEL_CATALOG.forEach((model) => {
        expect(model.displayName.length).toBeGreaterThan(2);
        expect(model.displayName.length).toBeLessThan(50);
      });
    });

    it("should have concise descriptions", () => {
      MODEL_CATALOG.forEach((model) => {
        expect(model.description.length).toBeGreaterThan(10);
        expect(model.description.length).toBeLessThan(200);
      });
    });
  });

  describe("Consistency", () => {
    it("should follow consistent naming pattern", () => {
      MODEL_CATALOG.forEach((model) => {
        // Display names should start with "Saptiva"
        expect(model.displayName).toMatch(/^Saptiva\s+/);
      });
    });

    it("should have consistent alias patterns", () => {
      MODEL_CATALOG.forEach((model) => {
        // Each model should have at least 4 aliases
        expect(model.aliases.length).toBeGreaterThanOrEqual(4);

        // Should include the display name
        expect(model.aliases).toContain(model.displayName);

        // Should include SCREAMING_SNAKE_CASE version
        const screamingSnakeCase = model.aliases.find(
          (a) => a === a.toUpperCase() && a.includes("_"),
        );
        expect(screamingSnakeCase).toBeDefined();
      });
    });
  });
});
