/**
 * Model Mapping - los modelos REALES vienen de `/api/models`
 *
 * La lista del backend es la fuente de verdad de qué modelos existen; el
 * catálogo local (`modelCatalog.ts`) solo aporta presentación (nombre visible,
 * descripción, badges) para los que reconoce, con matching tolerante a
 * mayúsculas/guiones/espacios. Un modelo que el catálogo no conoce se muestra
 * con su id tal cual, no se oculta.
 *
 * Key functions:
 * - findUiModelByBackendName: metadata de presentación para un id del backend
 * - buildModelList: lista de modelos del backend lista para la UI
 * - getDefaultModelSlug: slug seleccionable que corresponde al default del backend
 */

import { MODEL_CATALOG, type UiModel } from "../config/modelCatalog";

/**
 * Normalize a model name for fuzzy matching
 * - Lowercase
 * - Replace underscores and hyphens with spaces
 * - Collapse multiple spaces to single space
 * - Trim whitespace
 */
function normalizeModelName(name: string): string {
  return name.toLowerCase().replace(/[_-]/g, " ").replace(/\s+/g, " ").trim();
}

/**
 * Find UI model by backend model name using fuzzy matching
 *
 * Matching strategy:
 * 1. Exact match in aliases (case-insensitive)
 * 2. Normalized match (handles underscores, hyphens, extra spaces)
 * 3. Contains match (for partial names like "turbo" → "Saptiva Turbo")
 *
 * @param backendName - Model name from backend API
 * @returns UI model entry or null if no match
 */
export function findUiModelByBackendName(backendName: string): UiModel | null {
  if (!backendName) return null;

  const normalized = normalizeModelName(backendName);

  // Strategy 1: Exact alias match (case-insensitive)
  for (const model of MODEL_CATALOG) {
    const aliasMatch = model.aliases.find(
      (alias) => normalizeModelName(alias) === normalized,
    );
    if (aliasMatch) return model;
  }

  // Strategy 2: Partial match - check if normalized name contains model slug
  for (const model of MODEL_CATALOG) {
    if (normalized.includes(model.slug)) return model;
  }

  // Strategy 3: Reverse partial - check if any alias contains the backend name
  for (const model of MODEL_CATALOG) {
    const containsMatch = model.aliases.find((alias) =>
      normalizeModelName(alias).includes(normalized),
    );
    if (containsMatch) return model;
  }

  return null;
}

/**
 * Build complete model list with availability status
 *
 * Creates a list of all catalog models with:
 * - availability flag (is this model available in backend?)
 * - backendId (exact name to send to API, null if unavailable)
 *
 * @param backendAvailableNames - Array of model names from /api/models
 * @returns Array of models with availability and backend ID info
 */
export function buildModelList(backendAvailableNames: string[]): Array<{
  model: UiModel;
  available: boolean;
  backendId: string | null;
}> {
  // La lista del BACKEND es la fuente de verdad: se recorre `/api/models`, no
  // el catálogo local. El catálogo solo aporta presentación (nombre bonito,
  // descripción, badges) cuando reconoce el modelo. Antes se recorría el
  // catálogo, así que al cambiar de gateway el selector mostraba modelos
  // inexistentes y ocultaba los reales.
  return backendAvailableNames.map((backendId, index) => {
    const catalogo = findUiModelByBackendName(backendId);
    if (catalogo) {
      return {
        model: { ...catalogo, order: index + 1 },
        available: true,
        backendId,
      };
    }
    return {
      model: modeloDesdeBackend(backendId, index + 1),
      available: true,
      backendId,
    };
  });
}

/**
 * Entrada de UI para un modelo que el catálogo local no conoce.
 *
 * Se usa el id del backend TAL CUAL como slug y nombre visible: inventar un
 * nombre "bonito" fue justo lo que rompió el chat al migrar de gateway (se
 * enviaba un modelo inexistente). Sin badges: no afirmamos capacidades que no
 * conocemos.
 */
function modeloDesdeBackend(backendId: string, order: number): UiModel {
  return {
    slug: backendId,
    displayName: backendId,
    description: "Modelo disponible en el gateway configurado.",
    badges: [],
    order,
    aliases: [backendId],
  };
}

/**
 * Get default model slug
 *
 * Given a backend default model name, find the corresponding UI slug.
 * Falls back to first catalog model if no match.
 *
 * @param backendDefaultName - Default model name from /api/models
 * @returns UI model slug
 */
export function getDefaultModelSlug(backendDefaultName: string | null): string {
  if (!backendDefaultName) return "turbo";

  // Si el catálogo no lo conoce, el slug ES el id del backend (coherente con
  // `buildModelList`): así el default del gateway queda seleccionable aunque
  // sea un modelo que el front nunca ha visto.
  const matched = findUiModelByBackendName(backendDefaultName);
  return matched?.slug || backendDefaultName;
}

/**
 * Validate if a slug exists in catalog
 */
export function isValidSlug(slug: string): boolean {
  return MODEL_CATALOG.some((m) => m.slug === slug);
}
