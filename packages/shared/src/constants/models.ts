/**
 * Constantes de modelos SAPTIVA compartidas entre frontend y backend
 */

export const SAPTIVA_MODELS = {
  CORTEX: 'SAPTIVA_CORTEX',
  TURBO: 'SAPTIVA_TURBO',
  GUARD: 'SAPTIVA_GUARD',
  OCR: 'SAPTIVA_OCR'
} as const

export type SaptivaModel = typeof SAPTIVA_MODELS[keyof typeof SAPTIVA_MODELS]

export const MODEL_DISPLAY_NAMES = {
  [SAPTIVA_MODELS.CORTEX]: 'Saptiva Cortex',
  [SAPTIVA_MODELS.TURBO]: 'Saptiva Turbo',
  [SAPTIVA_MODELS.GUARD]: 'Saptiva Guard',
  [SAPTIVA_MODELS.OCR]: 'Saptiva OCR'
} as const

export const MODEL_DESCRIPTIONS = {
  [SAPTIVA_MODELS.CORTEX]: 'Modelo principal para conversaciones generales y razonamiento complejo',
  [SAPTIVA_MODELS.TURBO]: 'Modelo optimizado para respuestas rápidas y tareas simples',
  [SAPTIVA_MODELS.GUARD]: 'Modelo especializado en moderación de contenido y seguridad',
  [SAPTIVA_MODELS.OCR]: 'Modelo para reconocimiento óptico de caracteres y análisis de imágenes'
} as const

export const DEFAULT_MODEL = SAPTIVA_MODELS.CORTEX

export const AVAILABLE_MODELS = [
  SAPTIVA_MODELS.CORTEX,
  SAPTIVA_MODELS.TURBO,
  SAPTIVA_MODELS.GUARD,
  SAPTIVA_MODELS.OCR
] as const