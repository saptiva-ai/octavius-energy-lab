import { PASOS_PENSANDO, PASOS_REDACTANDO, esperaDeConsulta } from "../espera-por-consulta";

// Equipo (2026-10-21): la burbuja de espera sigue los pasos reales del turno,
// en orden: pensando (antes de que el decide elija), consultando (con el tema
// de la tool) y redactando (ya hay datos). El backend avisa cada paso con el
// evento `status`; aquí se traduce a tema, frase para lectores de pantalla y
// mensajes en orden.
describe("esperaDeConsulta", () => {
  const consultando = (
    t: string,
    metrica: string | null = null,
    dimension: string | null = null,
  ) => ({ fase: "consultando", tools: [{ tool: t, metrica, dimension }] });

  it("sin aviso del backend: pensando, con sus pasos en orden", () => {
    const espera = esperaDeConsulta(undefined);
    expect(espera).toMatchObject({ tema: "generico", frase: "Pensando" });
    expect(espera.frases).toBe(PASOS_PENSANDO);
    expect(PASOS_PENSANDO[0]).toBe("Saptivating…");
    expect(PASOS_PENSANDO).toContain("Carling…");
    expect(PASOS_PENSANDO).toContain("Leyendo tu pregunta…");
  });

  it("venta: nombra la medida que se consulta", () => {
    const ventas = esperaDeConsulta(consultando("retail_analytics", "venta_hora"));
    expect(ventas).toMatchObject({ tema: "ventas", frase: "Consultando ventas" });
    expect(ventas.frases[0]).toBe("Consultando la venta…");
    expect(ventas.frases).toContain("Pasando por caja 7…");
    expect(esperaDeConsulta(consultando("retail_analytics", "utilidad_bruta")).frases[0]).toBe(
      "Consultando la utilidad bruta…",
    );
  });

  it("venta por tienda: ranking que nombra la dimensión", () => {
    const ranking = esperaDeConsulta(consultando("retail_analytics", "venta_hora", "tienda"));
    expect(ranking).toMatchObject({ tema: "ranking", frase: "Comparando tiendas" });
    expect(ranking.frases[0]).toBe("Comparando tiendas…");
    expect(ranking.frases).toContain("Armando el podio…");
    expect(esperaDeConsulta(consultando("retail_analytics", null, "categoria")).frase).toBe(
      "Comparando categorías",
    );
  });

  it("métricas de inventario: inventario, aunque vengan por tienda, con la medida", () => {
    const inventario = esperaDeConsulta(consultando("retail_analytics", "faltante", "tienda"));
    expect(inventario).toMatchObject({ tema: "inventario", frase: "Revisando inventario" });
    expect(inventario.frases[0]).toBe("Revisando los productos sin existencia…");
    expect(inventario.frases).toContain("Contando latas…");
    for (const m of ["disponibilidad", "inventario_mes", "dias_sin_venta"]) {
      expect(esperaDeConsulta(consultando("retail_analytics", m)).tema).toBe("inventario");
    }
  });

  it("alertas, quiebre y pronóstico: riesgo, con pasos de cada tarea", () => {
    expect(esperaDeConsulta(consultando("alerta_quiebre_probable")).frases[0]).toBe(
      "Revisando las alertas…",
    );
    expect(esperaDeConsulta(consultando("predecir_demanda")).frases[0]).toBe(
      "Calculando el pronóstico…",
    );
    expect(esperaDeConsulta(consultando("retail_analytics", "venta_perdida"))).toMatchObject({
      tema: "riesgo",
      frase: "Buscando riesgos",
    });
    expect(esperaDeConsulta(consultando("retail_analytics", "venta_perdida")).frases[0]).toBe(
      "Calculando la venta perdida…",
    );
  });

  it("definiciones, presentación y catálogo: ayuda, cada una con su tarea", () => {
    expect(esperaDeConsulta(consultando("retail_definicion")).frases[0]).toBe(
      "Buscando en el glosario…",
    );
    expect(esperaDeConsulta(consultando("retail_presentacion")).frases[0]).toBe(
      "Repasando lo que sé hacer…",
    );
    expect(esperaDeConsulta(consultando("retail_catalogo")).frases[0]).toBe(
      "Revisando el catálogo…",
    );
    for (const t of ["retail_definicion", "retail_presentacion", "retail_catalogo"]) {
      expect(esperaDeConsulta(consultando(t))).toMatchObject({ tema: "ayuda", frase: "Un momento" });
    }
  });

  it("redactando: conserva el tema de la consulta y pasa a los pasos de redacción", () => {
    const espera = esperaDeConsulta({
      fase: "redactando",
      tools: [{ tool: "retail_analytics", metrica: "faltante", dimension: null }],
    });
    expect(espera).toMatchObject({ tema: "inventario", frase: "Redactando la respuesta" });
    expect(espera.frases).toBe(PASOS_REDACTANDO);
    expect(PASOS_REDACTANDO[0]).toBe("Redactando la respuesta…");

    expect(esperaDeConsulta({ fase: "redactando", tools: [] }).tema).toBe("generico");
  });

  // Equipo (2026-10-21): muchas más frases, primero las de la tarea y luego
  // graciosas; con una cada 2.5 s, ocho o más cubren una espera de 20 s.
  it("cada paso trae al menos ocho mensajes distintos, terminados en puntos suspensivos", () => {
    const estados = [
      undefined,
      consultando("retail_analytics", "venta_hora"),
      consultando("retail_analytics", "venta_hora", "tienda"),
      consultando("retail_analytics", "faltante"),
      consultando("alerta_quiebre_probable"),
      consultando("retail_definicion"),
      { fase: "redactando", tools: [] },
    ];
    for (const estado of [
      ...estados,
      consultando("predecir_demanda"),
      consultando("retail_analytics", "venta_perdida"),
      consultando("retail_presentacion"),
      consultando("retail_catalogo"),
    ]) {
      const { frases } = esperaDeConsulta(estado);
      expect(frases.length).toBeGreaterThanOrEqual(8);
      expect(new Set(frases).size).toBe(frases.length);
      for (const paso of frases) expect(paso).toMatch(/…$/);
    }
  });

  it("una tool desconocida no rompe: pensando", () => {
    expect(esperaDeConsulta(consultando("algo_nuevo")).tema).toBe("generico");
    expect(esperaDeConsulta({ fase: "consultando", tools: [] }).tema).toBe("generico");
  });
});
