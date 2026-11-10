/**
 * Contratos de datos del backend (regla R2: contrato antes que feature).
 *
 * Punto único donde el frontend modela lo que el backend REALMENTE envía.
 * Cuando se adopte generación por esquema (OpenAPI/zod), reemplaza el
 * contenido de estos módulos manteniendo el mismo layout.
 */
export * from "./analytics";
export * from "./message-metadata";
