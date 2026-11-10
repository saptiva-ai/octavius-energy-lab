/**
 * Model Catalog - Canonical UI model definitions
 *
 * This catalog defines the production-style UI representation for all models.
 * It is decoupled from backend model names/IDs to handle inconsistent casing and naming.
 *
 * Design principles:
 * - Each model has a stable `slug` used as the internal UI identifier
 * - Backend model names are mapped to catalog entries via fuzzy matching
 * - Catalog entries include displayName, description, badges for rich UI
 * - `aliases` support multiple backend name variations (case-insensitive)
 */

export type ModelBadge = 'CORE' | 'REASONING' | 'CHAT' | 'FAST' | 'EXPERIMENTAL'

export type UiModel = {
  slug: string
  displayName: string
  description: string
  badges: ModelBadge[]
  order: number
  aliases: string[]
}

/**
 * Canonical model catalog for UI rendering
 *
 * IMPORTANT: Backend model IDs are NOT changed. This catalog only affects UI display.
 * The mapping layer (modelMap.ts) handles translating between backend names and catalog entries.
 */
export const MODEL_CATALOG: UiModel[] = [
  {
    slug: 'turbo',
    displayName: 'Saptiva Turbo',
    description: 'Rápido y eficiente para conversaciones generales.',
    badges: ['CORE', 'FAST'],
    order: 1,
    aliases: [
      'Saptiva Turbo',
      'saptiva turbo',
      'saptiva_turbo',
      'SAPTIVA_TURBO',
      'turbo',
    ],
  },
  {
    slug: 'cortex',
    displayName: 'Saptiva Cortex',
    description: 'Razonamiento profundo y análisis detallado.',
    badges: ['CORE', 'REASONING'],
    order: 2,
    aliases: [
      'Saptiva Cortex',
      'saptiva cortex',
      'saptiva_cortex',
      'SAPTIVA_CORTEX',
      'cortex',
    ],
  },
  {
    slug: 'ops',
    displayName: 'Saptiva Ops',
    description: 'Tareas operativas y respuestas concisas.',
    badges: ['CORE', 'FAST', 'CHAT'],
    order: 3,
    aliases: [
      'Saptiva Ops',
      'saptiva ops',
      'saptiva_ops',
      'SAPTIVA_OPS',
      'ops',
    ],
  },
  {
    slug: 'legacy',
    displayName: 'Saptiva Legacy',
    description: 'Compatibilidad con SDK avanzado y herramientas legacy.',
    badges: ['CORE', 'EXPERIMENTAL'],
    order: 4,
    aliases: [
      'Saptiva Legacy',
      'saptiva legacy',
      'saptiva_legacy',
      'SAPTIVA_LEGACY',
      'legacy',
    ],
  },
]

/**
 * Get model by slug
 */
export function getModelBySlug(slug: string): UiModel | undefined {
  return MODEL_CATALOG.find((m) => m.slug === slug)
}

/**
 * Get all models sorted by order
 */
export function getAllModels(): UiModel[] {
  return [...MODEL_CATALOG].sort((a, b) => a.order - b.order)
}

/**
 * Badge color configuration for UI rendering
 */
export const BADGE_STYLES: Record<ModelBadge, { bg: string; text: string; border: string }> = {
  CORE: {
    bg: 'bg-primary/10',
    text: 'text-primary',
    border: 'border-primary/30',
  },
  REASONING: {
    bg: 'bg-purple-500/10',
    text: 'text-purple-600 dark:text-purple-400',
    border: 'border-purple-500/30',
  },
  CHAT: {
    bg: 'bg-blue-500/10',
    text: 'text-blue-600 dark:text-blue-400',
    border: 'border-blue-500/30',
  },
  FAST: {
    bg: 'bg-green-500/10',
    text: 'text-green-600 dark:text-green-400',
    border: 'border-green-500/30',
  },
  EXPERIMENTAL: {
    bg: 'bg-orange-500/10',
    text: 'text-orange-600 dark:text-orange-400',
    border: 'border-orange-500/30',
  },
}