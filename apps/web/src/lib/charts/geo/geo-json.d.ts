/** Assets geográficos empaquetados (GeoJSON local, sin tiles externos).
 * Declaración genérica: tsc no necesita tipar las 32 geometrías. */
declare module "*.geo.json" {
  const value: Record<string, unknown>;
  export default value;
}
