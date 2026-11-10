import type { ToolId } from "@/types/tools";
import { featureFlags } from "@/lib/feature-flags";

/**
 * Puente entre los tool-keys legacy del payload/store (snake_case, contrato
 * con el backend: `tools_enabled.*`) y los ToolId de la UI (kebab-case).
 *
 * UNA sola fuente de verdad (el mapa forward); la inversa se DERIVA, así no
 * pueden divergir. Un ToolId puede agrupar varios keys legacy (ej. `canvas`
 * agrupa `document_analysis` y `create_artifact`, que el backend gatea por
 * separado) → la inversa es 1→N (`toolIdToLegacyKeys`). El bug histórico:
 * la inversa manual devolvía solo `create_artifact`, dejando
 * `document_analysis` prendido al quitar el chip (el chip reaparecía).
 */

export type ToolKey =
  | "web_search"
  | "deep_research"
  | "code_analysis"
  | "document_analysis"
  | "create_artifact"
  | "retail_advisor";

const LEGACY_KEY_TO_TOOL_ID_MAP: Record<ToolKey, ToolId> = {
  web_search: "web-search",
  deep_research: "deep-research",
  code_analysis: "agent-mode",
  document_analysis: "canvas",
  create_artifact: "canvas",
  // El backend recibe `tools_enabled.retail_advisor` (gate del chat retail-advisor).
  retail_advisor: "retail-advisor",
};

// Inversa derivada (1 ToolId → N ToolKeys). Nunca editar a mano.
const TOOL_ID_TO_LEGACY_KEYS_MAP: Partial<Record<ToolId, ToolKey[]>> =
  Object.entries(LEGACY_KEY_TO_TOOL_ID_MAP).reduce(
    (acc, [key, id]) => {
      (acc[id] ??= []).push(key as ToolKey);
      return acc;
    },
    {} as Partial<Record<ToolId, ToolKey[]>>,
  );

export const KNOWN_TOOL_KEYS: ToolKey[] = Object.keys(
  LEGACY_KEY_TO_TOOL_ID_MAP,
) as ToolKey[];

export function legacyKeyToToolId(key: string): ToolId | undefined {
  return LEGACY_KEY_TO_TOOL_ID_MAP[key as ToolKey];
}

/** Todos los keys legacy de un ToolId (activar/desactivar un chip = TODOS). */
export function toolIdToLegacyKeys(id: ToolId): ToolKey[] {
  return TOOL_ID_TO_LEGACY_KEYS_MAP[id] ?? [];
}

/**
 * Tools activas POR DEFAULT en chats nuevos, declaradas por despliegue en
 * `NEXT_PUBLIC_DEFAULT_TOOLS` (keys o ids separados por comas, por ejemplo
 * "retail_advisor"). Sin la variable, `retail_advisor` arranca prendida si el
 * feature flag lo permite: sin la tool el LLM responde consultas de datos con
 * cifras inventadas (verificado en vivo 2026-07-13).
 */
export function defaultToolKeysFromEnv(
  value: string | undefined,
): ReadonlySet<ToolKey> {
  const declaradas = (value ?? "")
    .split(",")
    .map((item) => item.trim().replace(/-/g, "_"))
    .filter(Boolean);
  if (declaradas.length === 0) {
    return new Set(
      featureFlags.retailAdvisor ? (["retail_advisor"] as const) : [],
    );
  }
  return new Set(
    declaradas.filter((key): key is ToolKey =>
      KNOWN_TOOL_KEYS.includes(key as ToolKey),
    ),
  );
}

const DEFAULT_ON_TOOL_KEYS: ReadonlySet<ToolKey> = defaultToolKeysFromEnv(
  process.env.NEXT_PUBLIC_DEFAULT_TOOLS,
);

/**
 * Tools que el usuario no puede apagar. En Energy Ontology Advisor la herramienta de
 * datos va siempre: apagada, el chat respondía "la herramienta está
 * desactivada, actívala desde el compositor" (feedback round 1,
 * 2026-10-16, punto 10). Desde el 2026-10-19 tampoco pinta chip: la fija el
 * despliegue y el usuario no tiene nada que decidir.
 */
const LOCKED_TOOL_KEYS: ReadonlySet<ToolKey> = DEFAULT_ON_TOOL_KEYS;

/** ¿La tool (ToolId de la UI o key legacy del payload) está bloqueada en encendido? */
export function isLockedTool(idOrKey: string): boolean {
  if (LOCKED_TOOL_KEYS.has(idOrKey as ToolKey)) return true;
  return toolIdToLegacyKeys(idOrKey as ToolId).some((key) =>
    LOCKED_TOOL_KEYS.has(key),
  );
}

/** Tools seleccionadas que sí llevan chip en el compositor (las bloqueadas no). */
export function toolsConChipEnComposer<T extends string>(
  ids: readonly T[],
): T[] {
  return ids.filter((id) => !isLockedTool(id));
}

export function createDefaultToolsState(
  extraToolKeys: string[] = [],
): Record<string, boolean> {
  const baseKeys = [...KNOWN_TOOL_KEYS, ...extraToolKeys];
  return baseKeys.reduce<Record<string, boolean>>((acc, key) => {
    if (!(key in acc)) {
      acc[key] = DEFAULT_ON_TOOL_KEYS.has(key as ToolKey);
    }
    return acc;
  }, {});
}

export function normalizeToolsState(
  raw?: Record<string, boolean>,
): Record<string, boolean> {
  const extraKeys = raw ? Object.keys(raw) : [];
  const normalized = createDefaultToolsState(extraKeys);
  if (raw) {
    Object.entries(raw).forEach(([key, value]) => {
      normalized[key] = Boolean(value);
    });
  }
  // Un estado guardado de antes (localStorage o sesión) no apaga las bloqueadas.
  LOCKED_TOOL_KEYS.forEach((key) => {
    normalized[key] = true;
  });
  return normalized;
}
