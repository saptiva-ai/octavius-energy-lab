/**
 * Lo que dice el indicador de espera según el paso del turno (equipo,
 * 2026-10-21): "en orden y relacionado con la tarea". El backend manda el
 * evento `status` en cada paso:
 * - sin aviso todavía: pensando (el decide no ha elegido);
 * - `consultando`: el decide eligió la tool; el tema y los pasos nombran la
 *   tarea (la medida, la dimensión, la tool);
 * - `redactando`: ya hay datos y el modelo escribe; conserva el tema.
 * Cada paso trae mensajes en orden que la burbuja avanza uno tras otro.
 */

export type TemaEspera =
  | "generico"
  | "ventas"
  | "ranking"
  | "inventario"
  | "riesgo"
  | "ayuda";

export interface ToolElegida {
  tool: string;
  metrica?: string | null;
  dimension?: string | null;
}

export interface EstadoEspera {
  fase: string;
  tools: ToolElegida[];
}

export interface Espera {
  tema: TemaEspera;
  /** Lo que se anuncia a lectores de pantalla; una vez por paso. */
  frase: string;
  /** Lo que se ve: los mensajes del paso, en orden. */
  frases: readonly string[];
}

// Primero los de la tarea; después se mezclan los graciosos (equipo,
// 2026-10-21: "unas interesantes, relacionadas con el tema, otras menos pero
// sí graciosas"). Uno cada 2.5 s: diez cubren una espera de 25 s sin repetir.
export const PASOS_PENSANDO: readonly string[] = [
  "Saptivating…",
  "Leyendo tu pregunta…",
  "Entendiendo qué necesitas…",
  "Eligiendo la herramienta…",
  "Carling…",
  "Preguntándole al gerente…",
  "Buscando un carrito sin rueda chueca…",
  "Afinando la calculadora…",
  "Calentando la báscula…",
  "Ya casi sale…",
];

export const PASOS_REDACTANDO: readonly string[] = [
  "Redactando la respuesta…",
  "Revisando las cifras…",
  "Acomodando los números…",
  "Poniendo los acentos…",
  "Quitando lo que sobra…",
  "Dándole formato…",
  "Imprimiendo el ticket…",
  "Engrapando la nota…",
  "Ya casi…",
];

const PENSANDO: Espera = { tema: "generico", frase: "Pensando", frases: PASOS_PENSANDO };

const TOOLS_DE_ALERTAS = new Set([
  "alerta_quiebre_probable",
  "detectar_alertas",
  "evaluar_alertas",
  "quiebre_y_venta",
]);

const TOOLS_DE_PRONOSTICO = new Set(["predecir_faltante_hoy", "predecir_demanda"]);

// Medidas del catálogo del plugin (config/retail_advisor.yaml) con el nombre
// que va en "Consultando …", "Revisando …" o "Calculando …".
const MEDIDAS_DE_VENTA: Record<string, string> = {
  venta_hora: "la venta",
  utilidad_bruta: "la utilidad bruta",
  margen_bruto: "el margen bruto",
  pvp_vigente: "los precios",
};

const MEDIDAS_DE_INVENTARIO: Record<string, string> = {
  disponibilidad: "la disponibilidad",
  dias_sin_venta: "los días sin venta",
  confiabilidad_inventario: "la confiabilidad del inventario",
  faltante: "los productos sin existencia",
  recibo_mercancia: "los recibos de mercancía",
  capacidad_anaquel: "la capacidad de anaquel",
  transitos: "la mercancía en tránsito",
  movimientos_inventario: "los movimientos de inventario",
  inventario_mes: "las existencias",
};

const MEDIDAS_DE_RIESGO: Record<string, string> = {
  tasa_quiebre_probable: "el quiebre probable",
  venta_perdida: "la venta perdida",
};

const COMPARANDO: Record<string, string> = {
  tienda: "tiendas",
  categoria: "categorías",
  articulo: "artículos",
  region: "regiones",
};

function consultando(elegida: ToolElegida): Espera {
  const { tool, metrica, dimension } = elegida;

  if (tool === "retail_definicion") {
    return {
      tema: "ayuda",
      frase: "Un momento",
      frases: [
        "Buscando en el glosario…",
        "Leyendo la definición…",
        "Revisando cómo se calcula…",
        "Subrayando lo importante…",
        "Quitándole lo técnico…",
        "Hojeando el diccionario…",
        "Desempolvando el manual…",
        "Ya casi…",
      ],
    };
  }
  if (tool === "retail_presentacion") {
    return {
      tema: "ayuda",
      frase: "Un momento",
      frases: [
        "Repasando lo que sé hacer…",
        "Juntando los datos disponibles…",
        "Revisando la fecha de corte…",
        "Contando tiendas y categorías…",
        "Ensayando la presentación…",
        "Planchando la camisa…",
        "Practicando el saludo…",
        "Ya casi…",
      ],
    };
  }
  if (tool === "retail_catalogo") {
    return {
      tema: "ayuda",
      frase: "Un momento",
      frases: [
        "Revisando el catálogo…",
        "Recorriendo categorías…",
        "Contando presentaciones…",
        "Leyendo etiquetas…",
        "Separando la Coca de la Coca Sin Azúcar…",
        "Buscando el código de barras…",
        "Acomodando el exhibidor…",
        "Ya casi…",
      ],
    };
  }
  if (TOOLS_DE_ALERTAS.has(tool)) {
    return {
      tema: "riesgo",
      frase: "Buscando riesgos",
      frases: [
        "Revisando las alertas…",
        "Cruzando la demanda de 28 días…",
        "Buscando huecos en el anaquel…",
        "Calculando el riesgo de mañana…",
        "Oliendo faltantes…",
        "Preguntándole al proveedor…",
        "Consultando la bola de cristal…",
        "Leyendo el ticket de mañana…",
        "Ya casi…",
      ],
    };
  }
  if (TOOLS_DE_PRONOSTICO.has(tool)) {
    return {
      tema: "riesgo",
      frase: "Buscando riesgos",
      frases: [
        "Calculando el pronóstico…",
        "Revisando las semanas anteriores…",
        "Viendo la tendencia…",
        "Revisando si cae en quincena…",
        "Consultando la bola de cristal…",
        "Leyendo el ticket de mañana…",
        "Preguntándole al calendario…",
        "Ya casi…",
      ],
    };
  }
  if (tool !== "retail_analytics" && tool !== "run_preset") return PENSANDO;

  if (metrica && MEDIDAS_DE_RIESGO[metrica]) {
    return {
      tema: "riesgo",
      frase: "Buscando riesgos",
      frases: [
        `Calculando ${MEDIDAS_DE_RIESGO[metrica]}…`,
        "Cruzando demanda y existencias…",
        "Buscando huecos en el anaquel…",
        "Sumando lo que no se vendió…",
        "Oliendo faltantes…",
        "Consultando la bola de cristal…",
        "Contando los carritos vacíos…",
        "Ya casi…",
      ],
    };
  }
  if (metrica && MEDIDAS_DE_INVENTARIO[metrica]) {
    return {
      tema: "inventario",
      frase: "Revisando inventario",
      frases: [
        `Revisando ${MEDIDAS_DE_INVENTARIO[metrica]}…`,
        "Cruzando inventario con ventas…",
        "Recorriendo pasillos…",
        "Revisando el anaquel…",
        "Subiendo a la bodega…",
        "Contando latas…",
        "Buscando la caja que nadie etiquetó…",
        "Moviendo el diablito…",
        "Bajando del tapanco…",
        "Ya casi…",
      ],
    };
  }
  if (dimension && COMPARANDO[dimension]) {
    const cuales = COMPARANDO[dimension];
    return {
      tema: "ranking",
      frase: `Comparando ${cuales}`,
      frases: [
        `Comparando ${cuales}…`,
        "Juntando las cifras de cada una…",
        "Ordenando de mayor a menor…",
        "Midiendo quién vendió más…",
        "Repartiendo medallas…",
        "Armando el podio…",
        "Revisando la foto finish…",
        "Puliendo los trofeos…",
        "Ya casi…",
      ],
    };
  }
  const medida = (metrica && MEDIDAS_DE_VENTA[metrica]) || "la venta";
  return {
    tema: "ventas",
    frase: "Consultando ventas",
    frases: [
      `Consultando ${medida}…`,
      "Abriendo los tickets del periodo…",
      "Sumando caja por caja…",
      "Separando devoluciones…",
      "Cuadrando el corte…",
      "Pasando por caja 7…",
      "Contando la morralla…",
      "Pidiendo precio en caja 3…",
      "Revisando que no falte ni un peso…",
      "Ya casi…",
    ],
  };
}

export function esperaDeConsulta(estado: EstadoEspera | undefined): Espera {
  const elegida = estado?.tools?.[0];
  if (estado?.fase === "redactando") {
    const tema = elegida ? consultando(elegida).tema : "generico";
    return { tema, frase: "Redactando la respuesta", frases: PASOS_REDACTANDO };
  }
  if (!elegida) return PENSANDO;
  return consultando(elegida);
}
