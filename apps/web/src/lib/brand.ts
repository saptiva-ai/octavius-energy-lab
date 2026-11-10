/**
 * Nombre del producto en la interfaz. La web decía "OctaviOS Chat" en el
 * historial y en el título de la pestaña (feedback round 1,
 * 2026-10-16, punto 11); el asistente se presenta como Energy Ontology Advisor
 * (backend `prompts/registry.yaml` y plugin `presentacion.nombre`).
 * Configurable por despliegue con NEXT_PUBLIC_PRODUCT_NAME.
 */
export const PRODUCT_NAME: string =
  process.env.NEXT_PUBLIC_PRODUCT_NAME?.trim() || "Energy Ontology Advisor";
