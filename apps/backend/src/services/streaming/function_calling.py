"""Native (OpenAI-compatible) function-calling sobre las tools del plugin de dominio.

Patrón **decide → execute → narrate** (evita parsear tool_call deltas mid-stream):
  1. Llamada NO-streaming a `chat_completion(..., tools=<schemas>)` → el LLM decide.
  2. Si el LLM devuelve `tool_calls`, se ejecutan vía el plugin (RemoteMcpClient) y se
     anexan como mensajes `assistant`(tool_calls) + `tool`(result).
  3. Si el round 1 NO produjo ningún resultado de DATOS (ninguna llamada,
     metadata de catálogo tipo get_presets o solo errores), se concede UN round
     extra de decide — máximo 2 rounds, sin agentic-loop.
  4. El caller sigue con el path de streaming normal, que ahora narra sobre los
     mensajes aumentados (con grounding real del plugin).

"Resultado de datos" se detecta por la FORMA del contrato genérico
`AnalyticsResponse` (`metric_name`/`series`), nunca por nombres de tools: el
backend NO conoce el dominio, ofrece las tools descubiertas y ejecuta lo que el
LLM pida (regla anti-deuda #1). **Fail-safe**: cualquier error → devuelve los
mensajes sin cambios (o lo aumentado hasta ese punto) y el chat sigue normal.
"""

from __future__ import annotations

import difflib
import json
import re
from datetime import date
from typing import Any, Awaitable, Callable, Optional

import structlog

from ...core.fechas import hoy_cdmx
from ...mcp_integration.clients.domain_tools import DomainToolProvider

logger = structlog.get_logger(__name__)


MAX_DECIDE_ROUNDS = 2  # round extra SOLO si el round 1 no trajo datos (no loop)

# Aviso para la narración cuando las tools de datos FALLARON (no cuando el LLM
# decidió no usarlas): sin esto el LLM narra de memoria e inventa cifras
# (observado en vivo con el 421 de fastmcp — ver card guard-anti-alucinacion).
# Genérico: no menciona dominio ni tools concretas.
TOOLS_UNAVAILABLE_NOTICE = {
    "role": "system",
    "content": (
        "AVISO CRÍTICO: las herramientas de datos configuradas para esta "
        "conversación no están disponibles en este momento por un fallo "
        "técnico. NO cites cifras, métricas ni datos específicos de memoria. "
        "Informa brevemente que los datos no están disponibles ahora mismo y "
        "sugiere reintentar en unos momentos."
    ),
}

# Simétrico al anterior para el flanco "tool APAGADA" (no caída): sin este
# aviso el LLM responde consultas de la operación con cifras inventadas y un
# falso "llamando a la herramienta..." (reproducido en vivo 2026-07-13, card
# pill-retail-default-nudge). La restricción equivalente en el system prompt
# base NO basta: queda enterrada en un prompt largo; este mensaje va al FINAL
# del contexto, donde el modelo sí la respeta. Genérico: sin dominio ni tools.
DATA_TOOL_OFF_NOTICE = {
    "role": "system",
    "content": (
        "AVISO CRÍTICO: en esta conversación la herramienta de datos de la "
        "operación está DESACTIVADA. NO tienes acceso a ninguna métrica ni "
        "dato de la operación; NO cites cifras de memoria ni digas "
        "que estás llamando a una herramienta. Si el usuario pregunta por "
        "datos de la operación, responde que necesitas la herramienta de "
        "datos activada y sugiere activarla desde el compositor del chat."
    ),
}

# La narración se hace sin ofrecer tools. Hay modelos que, al ver la conversación
# terminar en resultados, intentan otra llamada y la escriben como texto
# (`<tool_call>...`), que le llegaba tal cual al usuario. Genérico: sin dominio.
NARRAR_SIN_TOOLS_NOTICE = {
    "role": "system",
    "content": (
        "Ya tienes los resultados de las herramientas. Redacta ahora la respuesta "
        "final para el usuario, en texto natural y en español, usando solo esos "
        "resultados. En este paso no hay herramientas disponibles: no escribas "
        "llamadas a herramientas, etiquetas <tool_call> ni JSON de argumentos."
    ),
}

# Instrucción SOLO para las llamadas "decide" (no se persiste en los mensajes
# que narran). Genérica: no menciona tools ni métricas del dominio. Cubre los
# dos fallos observados en vivo: (a) responder un follow-up con otro desglose
# extrapolando resultados de turnos anteriores en vez de re-consultar, y
# (b) preguntar al usuario en vez de actuar tras explorar el catálogo.
_NUDGE_DECIDE = {
    "role": "system",
    "content": (
        "Decide usando las herramientas disponibles. Si la solicitud más "
        "reciente puede responderse o verificarse con alguna de ellas, DEBES "
        "llamar la herramienta adecuada; no respondas de memoria ni omitas la "
        "llamada. Esto incluye solicitudes de cifras, listas, tendencias, "
        "riesgos y validaciones. EXCEPCIÓN: si la solicitud solo pide explicar, "
        "aclarar o interpretar algo que YA respondiste en esta conversación, y "
        "no pide un dato nuevo (otro periodo, filtro, desglose o entidad), NO "
        "llames herramientas: esa explicación se responde con lo que ya está "
        "en el contexto. Los resultados "
        "de herramientas de "
        "turnos ANTERIORES no responden una pregunta nueva con otro desglose, "
        "filtro, categoría o periodo — para cualquier variación llama la "
        "herramienta otra vez; NUNCA derives ni estimes cifras a partir de "
        "resultados previos. Si comparas entidades en varias llamadas de un "
        "mismo turno, usa el mismo periodo en todas; una comparación entre "
        "periodos se pide en UNA llamada con los argumentos de comparación de "
        "la herramienta, que calcula las ventanas. Si la solicitud pide dos "
        "medidas distintas (por ejemplo los más vendidos y su inventario), haz "
        "una llamada por medida en este mismo paso. Si la solicitud nombra qué "
        "medir (una métrica, tendencia, ranking, comparación, riesgo, "
        "categoría o artículo), consulta los datos con los valores por "
        "defecto de la herramienta. Solo si no hay NADA que medir, o una "
        "entidad admite más de una lectura y no puedes consultar sin "
        "resolverla, llama la herramienta de aclaración con las "
        "interpretaciones posibles en vez de adivinar. Si una herramienta devolvió opciones "
        "para que el usuario elija, no elijas tú: el turno termina ahí. Si "
        "una herramienta devolvió un error por un argumento faltante o mal "
        "escrito, corrígelo y vuelve a llamarla. Si descubriste un catálogo "
        "o presets, ejecuta la consulta ahora. "
        "En este paso NO escribas texto para el usuario: responde SOLO con "
        "la(s) llamada(s) a herramientas, con cada argumento COMPLETO "
        "(nombres de métrica y tienda enteros, nunca abreviados)."
    ),
}


# Mensajes previos del usuario que viajan como contexto (follow-ups como
# "y eso?" se entienden con lo que el usuario dijo antes).
CONTEXTO_USUARIO_MAX = 3


def _texto_de(contenido: Any) -> str:
    """Texto de un mensaje: str o lista de partes {"type": "text"}."""
    if isinstance(contenido, str):
        return contenido.strip()
    if isinstance(contenido, list):
        partes = [
            str(p.get("text", ""))
            for p in contenido
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return " ".join(p for p in partes if p).strip()
    return ""


def textos_del_usuario(
    messages: list[dict[str, Any]],
) -> tuple[Optional[str], list[str]]:
    """(último mensaje del usuario, hasta CONTEXTO_USUARIO_MAX previos, del más
    viejo al más nuevo). Solo palabras del usuario: nada del asistente."""
    textos = [
        t
        for t in (
            _texto_de(m.get("content")) for m in messages if m.get("role") == "user"
        )
        if t
    ]
    if not textos:
        return None, []
    return textos[-1], textos[:-1][-CONTEXTO_USUARIO_MAX:]


# Respuestas previas del chat que viajan como contexto: "¿cuánto se vende de
# ese?" nombra un producto que el chat mostró, no algo que el usuario
# escribió (examen v2, 2026-10-12). El plugin decide qué hacer con ellas.
CONTEXTO_ASISTENTE_MAX = 2


def textos_del_asistente(messages: list[dict[str, Any]]) -> list[str]:
    """Hasta CONTEXTO_ASISTENTE_MAX respuestas previas del chat con texto, de
    la más vieja a la más nueva. Las llamadas a tools no tienen texto."""
    textos = [
        t
        for t in (
            _texto_de(m.get("content"))
            for m in messages
            if m.get("role") == "assistant"
        )
        if t
    ]
    return textos[-CONTEXTO_ASISTENTE_MAX:]


def tools_que_declaran(schemas: list[dict[str, Any]], parametro: str) -> set[str]:
    """Nombres de tools cuyo schema declara `parametro`."""
    nombres: set[str] = set()
    for schema in schemas or []:
        funcion = schema.get("function", schema) if isinstance(schema, dict) else {}
        params = (funcion.get("parameters") or {}).get("properties") or {}
        if parametro in params and funcion.get("name"):
            nombres.add(str(funcion["name"]))
    return nombres


# Parecido mínimo para corregir un nombre de argumento contra el schema: un
# typo del modelo ("metrica_or_query", "tiendaa"), no otro parámetro.
_PARECIDO_ARGUMENTO = 0.9


def _parametros_de(schemas: list[dict[str, Any]], nombre: str) -> dict[str, Any]:
    for schema in schemas or []:
        funcion = schema.get("function", schema) if isinstance(schema, dict) else {}
        if funcion.get("name") == nombre:
            return dict(funcion.get("parameters") or {})
    return {}


def ajustar_argumentos(
    parametros: dict[str, Any], argumentos: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Corrige nombres de argumento casi idénticos a un parámetro declarado.

    Visto en el conjunto de desarrollo (2026-10-11): el modelo escribió
    `metrica_or_query` en los dos rounds y la tool rechazó la llamada entera.
    Solo renombra hacia un parámetro que no venga ya; un nombre sin parecido
    se deja tal cual para que el error vuelva al modelo. Genérico: solo usa
    el schema, no conoce el dominio.
    """
    declarados = list((parametros.get("properties") or {}).keys())
    salida = dict(argumentos)
    cambios: dict[str, str] = {}
    for clave in list(argumentos):
        if clave in declarados:
            continue
        libres = [p for p in declarados if p not in salida]
        parecido = difflib.get_close_matches(
            clave, libres, n=1, cutoff=_PARECIDO_ARGUMENTO
        )
        if parecido:
            salida[parecido[0]] = salida.pop(clave)
            cambios[clave] = parecido[0]
    return salida, cambios


def _nudge_perfil(ambito: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Aviso genérico, solo para `decide`, con el perfil del usuario autenticado.

    El backend no interpreta el ámbito (regla anti-deuda #1): lo muestra tal
    cual, como primer mensaje del decide, para que el modelo sepa quién
    pregunta (Compras no tiene tienda y no debe pedirla). Sin él, no llamaba
    ninguna tool en Compras (visto en vivo 2026-09-02). Va al INICIO y sin
    instrucciones sobre argumentos: anexado al final, junto al nudge, el
    modelo dejaba de llamar tools (eval de routing 1/6). El ámbito real se
    inyecta aparte y manda sobre cualquier argumento del LLM.
    """
    # El id de conversación es para la memoria del plugin, no para el decide.
    perfil = {k: v for k, v in (ambito or {}).items() if k != "conversacion"}
    if not perfil:
        return None
    return {
        "role": "system",
        "content": (
            "Perfil del usuario autenticado, aplicado por el backend en cada "
            f"herramienta: {json.dumps(perfil, ensure_ascii=False)}."
        ),
    }


def ambito_con_conversacion(
    ambito: Optional[dict[str, Any]], conversacion_id: Optional[str]
) -> Optional[dict[str, Any]]:
    """El ámbito del perfil más el id de la conversación, para que el plugin
    recuerde lo que mostró (FEAT memoria-de-conversacion, 2026-11-07). Sin
    perfil también viaja: la memoria no depende del rol."""
    if not conversacion_id:
        return ambito
    return {**(ambito or {}), "conversacion": str(conversacion_id)}


# Follow-up sin datos nuevos ("explícame", "¿por qué?"): el turno no produjo
# datos —el decide no llamó tools, o llamó y la consulta volvió vacía— y la
# conversación ya tiene una respuesta con cifras. Sin este aviso la narración
# inventaba causas ("el sistema no identificó refrescos"), pedía una marca o
# escribía una llamada a herramienta como texto (visto en vivo 2026-09-03, en
# local sin llamada y en producción con una llamada sin datos). Genérico: no
# nombra tools ni métricas.
FOLLOW_UP_SIN_DATOS_NOTICE = {
    "role": "system",
    "content": (
        "En este turno no se consultaron datos nuevos. Si el usuario pide "
        "explicar, aclarar o interpretar, responde a partir de tu respuesta "
        "anterior y de los resultados de herramientas que ya están en esta "
        "conversación: qué se midió, con qué alcance, filtros y periodo (con "
        "los mismos nombres que traen esos resultados, sin cambiarlos por un "
        "posesivo como 'tu'), cómo se calcula y qué destaca, citando esas "
        "cifras tal cual y sin repetir la tabla; las fechas en palabras ('30 "
        "de septiembre de 2026'), nunca como AAAA-MM-DD. Si pide un dato "
        "nuevo (otra medida, otro alcance, otro filtro u otro periodo) que no "
        "está en la conversación, no lo tienes: no afirmes que no existe ni "
        "que no hay datos, no ofrezcas buscar en otra base ni prometas una "
        "búsqueda; pide la precisión que falte (qué medir, con qué alcance, "
        "filtro o periodo) o di qué sí se puede consultar. No inventes "
        "causas, no expliques por qué una consulta no devolvió datos, no "
        "afirmes que algo 'no se identificó' ni que el sistema necesita otro "
        "dato, no pidas información que ya está en el contexto y NUNCA "
        "escribas una llamada a herramienta como texto. "
        "Habla en el lenguaje del usuario, sin jerga técnica: no menciones 'la consulta', 'la herramienta', 'el sistema no me entregó', 'esta prueba' ni nombres internos; di 'no tengo ese dato' y qué sí puedes darle. Si usas un término técnico de los resultados, explícalo en pocas palabras. "
    ),
}

# Primer turno sin consulta: no hay respuesta anterior que explicar. Con el
# aviso de seguimiento el narrador afirmó "No tengo datos para Centro" ante
# "los 5 refrescos más vendidos y su inventario" (sonda por OpenRouter,
# 2026-10-21, P1.4 del reporte de QA). Genérico: no nombra tools.
PRIMER_TURNO_SIN_CONSULTA_NOTICE = {
    "role": "system",
    "content": (
        "En este turno no se consultaron datos y es la primera pregunta de la "
        "conversación. Si el usuario pidió datos, di en una frase que no "
        "alcanzaste a consultarlo y propón hacer la pregunta por partes (una "
        "medida a la vez) o pide la precisión que falte; si solo saluda o "
        "conversa, contesta con naturalidad. No afirmes que no existe ni que no hay datos de "
        "lo que pidió, no ofrezcas buscar en otra base ni prometas una "
        "búsqueda, no inventes cifras ni causas y NUNCA escribas una llamada a "
        "herramienta como texto. "
        "Habla en el lenguaje del usuario, sin jerga técnica: no menciones 'la consulta', 'la herramienta', 'el sistema no me entregó', 'esta prueba' ni nombres internos; di 'no tengo ese dato' y qué sí puedes darle. Si usas un término técnico de los resultados, explícalo en pocas palabras. "
    ),
}

# Turno con resultados de datos: el narrador explica y da formato; la gráfica
# ya va en el panel (decisión de producto, 2026-10-15). Genérico: no nombra
# tools, métricas ni dominio.
NARRACION_DATOS_NOTICE = {
    "role": "system",
    "content": (
        "Este turno trae resultados de herramientas de datos; la gráfica, si "
        "la hay, ya se muestra en el panel. Si un resultado trae "
        "`aviso_usuario`, empieza la respuesta con ese texto tal cual: es una "
        "salvedad que el usuario debe leer antes de las cifras. Responde en "
        "markdown: primero una "
        "frase con la respuesta, la cifra principal y su alcance (dónde y "
        "cuándo) con los mismos nombres que trae el resultado, sin cambiarlos "
        "por un posesivo como 'tu'; después las cifras del "
        "resultado copiadas tal cual (nombres, números, unidades y periodo): "
        "en una tabla markdown cuando son varias filas comparables (un "
        "ranking, varios elementos o varios periodos) y en viñetas cortas "
        "cuando son pocas. Si un resultado trae `resumen_serie` (una serie "
        "larga en el tiempo), no pongas la serie en tabla: da el promedio, el "
        "mínimo y el máximo de ese resumen tal cual, con su fecha, y di que el "
        "detalle está en la gráfica. Si el resultado dice el periodo o la fecha de los "
        "datos, ciérralo con una línea que los diga, con las fechas en palabras "
        "('30 de septiembre de 2026') y nunca como AAAA-MM-DD. Conserva las "
        "conclusiones "
        "que ya trae el texto del resultado (cuánto concentra lo primero, el "
        "cambio contra otro periodo, el pico) y, cuando el resultado trae un "
        "porcentaje de cambio o un nivel de confianza por fila, ponlo en su "
        "propia columna o viñeta con el mismo valor; no agregues columnas, "
        "calificaciones ni niveles que el resultado no trae. Explica qué "
        "significa el "
        "resultado en una o dos frases con lo que muestran las cifras: no "
        "atribuyas causas que los resultados no traen (mercancía en bodega, "
        "flujo de clientes, clima, competencia); si el usuario pregunta por "
        "qué, di qué muestran las cifras y que la causa no está en los datos. "
        "No calcules escenarios que el resultado no trae (otro precio, un "
        "descuento, un 2x1, un margen nuevo, cuánto pedir): di que ese "
        "escenario no lo calculas y ofrece las cifras del resultado que sirven "
        "para decidirlo. "
        "Si al final ofreces otra consulta, que sea algo nuevo: no ofrezcas lo "
        "que ya diste en esta respuesta. Usa solo el alcance y los filtros que "
        "dice el resultado de este turno: no arrastres filtros de preguntas "
        "anteriores. Si el usuario pidió algo que los resultados de este turno "
        "no cubren (otro alcance, filtro o periodo), di que esa parte no se "
        "consultó y ofrece consultarla; no afirmes que no hay datos de eso. "
        "Si el usuario pide explicar, interpretar o el porqué de "
        "lo que ya respondiste, contesta eso con estas cifras y no repitas la "
        "respuesta anterior. No describas la gráfica punto por punto, no "
        "agregues cifras que no estén en los resultados y no copies el texto "
        "del resultado sin estructura. "
        "Habla en el lenguaje del usuario, sin jerga técnica: no menciones 'la consulta', 'la herramienta', 'el sistema no me entregó', 'esta prueba' ni nombres internos; di 'no tengo ese dato' y qué sí puedes darle. Si usas un término técnico de los resultados, explícalo en pocas palabras. "
    ),
}

# Un resultado del turno se declara literal (`grounding.narracion ==
# "literal"`, contrato genérico): su texto ya es la respuesta y se entrega tal
# cual. feedback de QA (2026-10-16, punto 13): el saludo del chat decía
# "datos en tiempo real" y "decisiones operativas basadas en datos precisos y
# accionables", nada de eso estaba en el texto del plugin.
NARRACION_LITERAL_NOTICE = {
    "role": "system",
    "content": (
        "El resultado de este turno ya es la respuesta para el usuario. "
        "Entrégalo tal cual, con sus mismas palabras: no agregues "
        "capacidades, promesas ni adjetivos que no estén en él, no digas que "
        "los datos son en tiempo real y no lo conviertas en lista ni tabla. "
        "Si el último mensaje del usuario está en otro idioma, tradúcelo "
        "completo a ese idioma sin agregar ni quitar nada."
    ),
}

# Alguna tool del turno devolvió `error`: su texto ya explica qué dato falta y
# a quién se pidió. Sin este aviso la narración lo resumía como "no tengo
# datos" y perdía la referencia de la solicitud (visto 2026-09-03: 1 de 3
# corridas de "¿qué está hoy sin existencia?" no citaba P-03). Genérico: no
# nombra dominio, tools ni identificadores.
HUECO_DECLARADO_NOTICE = {
    "role": "system",
    "content": (
        "Alguna consulta de este turno NO pudo responderse y su resultado "
        "explica el motivo. Empieza diciendo explícitamente qué no puedes "
        "responder y explica ese motivo (qué dato falta y a quién se pidió) "
        "con palabras sencillas de la operación, sin códigos, nombres de "
        "campos, identificadores internos ni formatos técnicos de fecha. No lo "
        "resumas como 'no tengo datos'. Después, si otro resultado del turno "
        "sí trajo datos, ofrécelo como alternativa dejando claro qué mide."
    ),
}

# Las consultas del turno NO trajeron datos: devolvieron error o piden una
# aclaración. Sin este aviso aplicaba el de follow-up, que pide citar las
# cifras anteriores, y la pregunta nueva se contestaba con los números de la
# anterior (P0-4 de la auditoría). Genérico: el host no conoce el dominio.
CONSULTA_FALLIDA_NOTICE = {
    "role": "system",
    "content": (
        "Las consultas de este turno no trajeron datos: devolvieron un error o "
        "piden una aclaración. Responde a la pregunta nueva diciendo eso y "
        "explica lo que indica el resultado (qué precisar o qué opciones hay) "
        "con palabras de la operación, sin códigos, nombres de campos ni "
        "formatos técnicos de fecha. NO repitas ni "
        "reutilices cifras de respuestas anteriores como si respondieran esta "
        "pregunta y NUNCA escribas una llamada a herramienta como texto."
    ),
}

# Alguna consulta del turno pide precisar algo al usuario (ruta clarify sin
# bandera reintentable). El modelo no elige por él: transmite la pregunta y
# las opciones. Genérico: el host no conoce el dominio (FEAT
# aclaracion-salida-valida, 2026-10-09).
ACLARACION_NOTICE = {
    "role": "system",
    "content": (
        "Una consulta de este turno necesita que el usuario precise algo antes "
        "de responder. Transmite esa pregunta y sus opciones, sin cambiar su "
        "sentido, en una respuesta breve y con palabras de la operación, sin "
        "códigos ni nombres de campos. Nombra cada opción tal cual viene y no "
        "la describas ni expliques con tus palabras: una descripción inventada "
        "puede decir otra cosa. No elijas por el usuario, no "
        "des cifras ni reutilices las de respuestas anteriores, y NUNCA "
        "escribas una llamada a herramienta como texto."
    ),
}

# Idioma de la respuesta (QA, P2.6: preguntó en inglés y contestó en
# español). Decisión del equipo (2026-10-21): el de la pregunta, con español
# por omisión. Va en cada aviso porque el aviso queda al final del contexto,
# en español junto a resultados en español, y ahí el narrador ignoraba la
# regla del system prompt. Genérico: no nombra dominio ni tools.
IDIOMA_RESPUESTA = (
    "Escribe la respuesta en el idioma del último mensaje del usuario, aunque "
    "sea un saludo corto ('Hi' es inglés); si no se distingue, en español. "
    "No traduzcas los nombres propios que traen los resultados. Los pesos son "
    "la moneda (MXN), no peso en kilos: en inglés, 'pesos' o 'MXN'."
)
for _aviso in (
    TOOLS_UNAVAILABLE_NOTICE,
    DATA_TOOL_OFF_NOTICE,
    FOLLOW_UP_SIN_DATOS_NOTICE,
    PRIMER_TURNO_SIN_CONSULTA_NOTICE,
    NARRACION_DATOS_NOTICE,
    NARRACION_LITERAL_NOTICE,
    HUECO_DECLARADO_NOTICE,
    CONSULTA_FALLIDA_NOTICE,
    ACLARACION_NOTICE,
):
    _aviso["content"] = f"{_aviso['content']} {IDIOMA_RESPUESTA}"

_NUDGE_RETRY_NO_CALL = {
    "role": "system",
    "content": (
        "Revisa tu decisión anterior: omitiste las llamadas a herramientas. "
        "Si la solicitud del usuario pide consultar, listar, explicar, graficar "
        "o validar información que cubre alguna herramienta disponible, llama "
        "ahora la herramienta adecuada. Devuelve una respuesta sin tool_calls "
        "únicamente si la petición es conversacional o ajena a todas las "
        "herramientas. En este paso responde SOLO con tool_calls cuando apliquen."
    ),
}

# Una corrección a la respuesta anterior abre con una negación. No interpreta
# el dominio: solo decide si se desconfía de un decide que, aun tras el
# reintento, no llamó herramientas (SIM-24: "no no, de todo el súper, no nomás
# refresco" quedó 2 de 3 veces en `no_calls`, 2026-11-07).
_NEGACION_INICIAL = re.compile(r"^\W*(no|nel|tampoco)\b", re.IGNORECASE)


def _es_correccion(texto: Optional[str]) -> bool:
    return bool(texto) and _NEGACION_INICIAL.match(texto.strip()) is not None


def llamada_forzada_por_correccion(
    pregunta: Optional[str],
    respuestas_previas: list[str],
    tools_de_datos: set[str],
) -> Optional[dict[str, Any]]:
    """La tool de datos que se llama sin argumentos del modelo cuando el decide
    no llamó nada ante una corrección del usuario en un seguimiento. El plugin
    completa la consulta desde su memoria de la conversación; aquí solo viajan
    las palabras del usuario. `None` si no es una corrección, si es el primer
    turno o si no hay exactamente una tool de datos."""
    if not respuestas_previas or not _es_correccion(pregunta):
        return None
    if len(tools_de_datos) != 1:
        return None
    return {"id": "correccion-1", "name": next(iter(tools_de_datos)), "arguments": {}}


def pill_datos_activo(
    request_tools: Optional[dict[str, Any]],
    session_tools: Optional[dict[str, Any]],
) -> bool:
    """¿El pill de la tool de datos está encendido por REQUEST *o* por SESIÓN?

    El frontend solo manda `tools_enabled` al activar el pill (primer
    mensaje); en follow-ups llega vacío y sin este merge la conversación
    perdía la tool de datos (y el LLM extrapolaba cifras del turno anterior —
    alucinación).
    """
    return any(
        (fuente or {}).get(alias)
        for fuente in (request_tools, session_tools)
        for alias in ("retail_advisor", "retail-advisor")
    )


async def augmentar_con_tools_de_dominio(
    *,
    settings: Any,
    saptiva_client: Any,
    messages: list[dict[str, Any]],
    model: str,
    request_tools: Optional[dict[str, Any]] = None,
    session_tools: Optional[dict[str, Any]] = None,
    user_id: Optional[str] = None,
    al_elegir: Optional[AlElegirTools] = None,
    conversacion_id: Optional[str] = None,
) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]], str]:
    """Paso decide → tool compartido por las DOS rutas del chat (streaming y
    no-streaming), para que la respuesta no dependa del transporte: misma
    condición de activación y mismos avisos anti-alucinación.

    `user_id` resuelve el ámbito del perfil (rol, tienda, categorías) que se
    inyecta en cada llamada a las tools de datos; el LLM no lo controla.

    Estados devueltos (además de los de `FunctionCallingOrchestrator.augment`):
    - "disabled": el deployment no ofrece function-calling; mensajes intactos.
    - "off": el deployment SÍ lo ofrece pero el pill está apagado — se anexa
      `DATA_TOOL_OFF_NOTICE` (sin él, el LLM contesta consultas de la
      operación con cifras inventadas).
    Con "failed" se anexa `TOOLS_UNAVAILABLE_NOTICE`: un fallo debe ser
    visible para el modelo, nunca silencioso.
    """
    if not getattr(settings, "retail_advisor_function_calling", False):
        return messages, None, "disabled"

    if not pill_datos_activo(request_tools, session_tools):
        return [*messages, DATA_TOOL_OFF_NOTICE], None, "off"

    # OJO: el step "decide" NO hereda la temperatura creativa de la sesión
    # (0.7 hace errática la elección de tools); usa el default determinista
    # del orquestador. La narración posterior sí corre con la de la sesión.
    from ..perfil_usuario import ambito_de_usuario

    augmented, tool_result, status = await FunctionCallingOrchestrator().augment(
        saptiva_client,
        messages,
        model=model,
        # Modelo dedicado al decide (Turbo emite args rotos según el
        # fraseo); con fallback interno al modelo de la sesión.
        decide_model=getattr(settings, "retail_advisor_decide_model", None),
        ambito=ambito_con_conversacion(
            await ambito_de_usuario(user_id), conversacion_id
        ),
        al_elegir=al_elegir,
    )
    aviso = aviso_del_turno(
        messages, augmented, status, got_data=tool_result is not None
    )
    if any(m.get("role") == "tool" for m in augmented[len(messages) :]):
        augmented = [*augmented, NARRAR_SIN_TOOLS_NOTICE]
    if aviso is not None:
        augmented = [*augmented, aviso]
    return augmented, tool_result, status


def aviso_del_turno(
    mensajes_originales: list[dict[str, Any]],
    mensajes_aumentados: list[dict[str, Any]],
    status: str,
    *,
    got_data: bool,
    hoy: Optional[date] = None,
) -> Optional[dict[str, Any]]:
    """`aviso_post_decide` con las señales de ESTE turno calculadas aquí. Lo
    usan el chat, el runner de ruteo, el holdout y el simulador: el examen
    sigue la misma ruta que producción y una señal nueva no se olvida en uno.

    Si los datos del turno son de hace días (`data_as_of` del contrato), se
    agrega la vigencia al aviso: el narrador presentaba datos del 30 de
    septiembre como "mañana, 7 de noviembre" (usuario simulado, 2026-11-06)."""
    aviso = aviso_post_decide(
        mensajes_originales,
        status,
        got_data=got_data,
        hueco_declarado=hubo_hueco_declarado(mensajes_originales, mensajes_aumentados),
        errores=errores_del_turno(mensajes_originales, mensajes_aumentados),
        aclaracion=hubo_aclaracion(mensajes_originales, mensajes_aumentados),
        literal=hubo_narracion_literal(mensajes_originales, mensajes_aumentados),
        repetido=resultado_repetido(mensajes_originales, mensajes_aumentados),
    )
    if not got_data or aviso is None:
        return aviso
    corte = _corte_de_los_datos(mensajes_originales, mensajes_aumentados)
    dias = ((hoy or hoy_cdmx()) - corte).days if corte else 0
    if dias < DIAS_DATOS_VIEJOS:
        return aviso
    vigencia = DATOS_VIEJOS_NOTICE_TEXTO.format(corte=corte.isoformat(), dias=dias)
    return {**aviso, "content": f"{aviso['content']}\n\n{vigencia}"}


# Desde cuántos días de diferencia entre el dato y hoy se avisa la vigencia.
DIAS_DATOS_VIEJOS = 3
DATOS_VIEJOS_NOTICE_TEXTO = (
    "Vigencia: los datos de este resultado llegan al {corte}, {dias} días antes "
    "de hoy. Si la pregunta habla de hoy, ayer, mañana o de ahora, dilo en la "
    "primera frase (los datos llegan al {corte}) y cita las fechas del "
    "resultado tal cual; nunca las presentes como de hoy ni de mañana. No "
    "inventes cantidades a pedir ni cifras que no estén en el resultado."
)


def _corte_de_los_datos(
    mensajes_originales: list[dict[str, Any]],
    mensajes_aumentados: list[dict[str, Any]],
) -> Optional[date]:
    """El `data_as_of` más reciente de los resultados de datos de ESTE turno."""
    fechas = []
    for mensaje in mensajes_aumentados[len(mensajes_originales) :]:
        if mensaje.get("role") != "tool":
            continue
        try:
            contenido = json.loads(mensaje.get("content") or "")
        except (ValueError, TypeError):
            continue
        if not _es_resultado_datos(contenido):
            continue
        try:
            fechas.append(
                date.fromisoformat(str(contenido.get("data_as_of") or "")[:10])
            )
        except ValueError:
            continue
    return max(fechas) if fechas else None


_CIFRA_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Un resultado se da por repetido solo con varias cifras ya dichas: un renglón
# ("¿por qué está en riesgo el primero?") repite su cifra pero trae la
# explicación nueva (g05 del listado, 2026-10-20).
MIN_CIFRAS_REPETIDAS = 3


def _cifras_del_texto(texto: str) -> list[float]:
    """Números escritos en un texto ("4,042" es 4042), sin importar el formato."""
    return [float(t.replace(",", "")) for t in _CIFRA_RE.findall(texto)]


def _ya_dicha(valor: float, dichas: list[float]) -> bool:
    # Tolerancia para el redondeo de la narración (pesos sin centavos).
    return any(abs(n - valor) <= max(0.5, abs(valor) * 0.0005) for n in dichas)


def resultado_repetido(
    mensajes_originales: list[dict[str, Any]],
    mensajes_aumentados: list[dict[str, Any]],
) -> bool:
    """¿Los resultados de datos de ESTE turno solo traen cifras que la última
    respuesta del asistente ya dijo? El decide repite la consulta ante
    "explícame" y el turno parece traer datos nuevos. Solo forma del contrato
    (`table_data[].value`) y números del texto, sin conocer el dominio."""
    previas = textos_del_asistente(mensajes_originales)
    dichas = _cifras_del_texto(previas[-1]) if previas else []
    if not dichas:
        return False
    hubo_datos = False
    for mensaje in mensajes_aumentados[len(mensajes_originales) :]:
        if mensaje.get("role") != "tool":
            continue
        try:
            contenido = json.loads(mensaje.get("content") or "")
        except (ValueError, TypeError):
            continue
        if not _es_resultado_datos(contenido):
            continue
        valores = []
        for fila in contenido.get("table_data") or []:
            try:
                valores.append(float(fila["value"]))
            except (KeyError, TypeError, ValueError):
                continue
        if len(valores) < MIN_CIFRAS_REPETIDAS or not all(
            _ya_dicha(v, dichas) for v in valores
        ):
            return False
        hubo_datos = True
    return hubo_datos


def _pide_aclaracion(result: Any) -> bool:
    """Resultado con `error` y ruta clarify que NO es reintentable: hay que
    preguntarle al usuario, no reintentar. Solo forma del contrato."""
    if not isinstance(result, dict) or not result.get("error"):
        return False
    router = (result.get("grounding") or {}).get("router") or {}
    return router.get("ruta") == "clarify" and not router.get("reintentable")


def hubo_narracion_literal(
    mensajes_originales: list[dict[str, Any]],
    mensajes_aumentados: list[dict[str, Any]],
) -> bool:
    """¿Algún resultado de ESTE turno se declara literal? Solo forma del
    contrato (`grounding.narracion == "literal"`), sin conocer el dominio."""
    for mensaje in mensajes_aumentados[len(mensajes_originales) :]:
        if mensaje.get("role") != "tool":
            continue
        try:
            contenido = json.loads(mensaje.get("content") or "")
        except (ValueError, TypeError):
            continue
        if not isinstance(contenido, dict) or contenido.get("error"):
            continue
        if (contenido.get("grounding") or {}).get("narracion") == "literal":
            return True
    return False


def hubo_aclaracion(
    mensajes_originales: list[dict[str, Any]],
    mensajes_aumentados: list[dict[str, Any]],
) -> bool:
    """¿Alguna tool de ESTE turno pidió precisar algo al usuario?"""
    for mensaje in mensajes_aumentados[len(mensajes_originales) :]:
        if mensaje.get("role") != "tool":
            continue
        try:
            contenido = json.loads(mensaje.get("content") or "")
        except (ValueError, TypeError):
            continue
        if _pide_aclaracion(contenido):
            return True
    return False


def hubo_hueco_declarado(
    mensajes_originales: list[dict[str, Any]],
    mensajes_aumentados: list[dict[str, Any]],
) -> bool:
    """¿Alguna tool de ESTE turno declaró que la pregunta NO se puede responder?

    Por la forma del contrato genérico, sin conocer el dominio: el resultado
    trae `error` y su `grounding.router.ruta` es "cannot_answer" (el dato no
    existe o no alcanza). Un error de aclaración ("clarify", argumentos mal
    formados) NO cuenta: suele venir de un intento fallido que otra llamada
    del mismo turno ya corrigió, y tratarlo como hueco tapaba la respuesta
    buena (visto 2026-09-03 con el ranking de refrescos).
    """
    for mensaje in mensajes_aumentados[len(mensajes_originales) :]:
        if mensaje.get("role") != "tool":
            continue
        try:
            contenido = json.loads(mensaje.get("content") or "")
        except (ValueError, TypeError):
            continue
        if not isinstance(contenido, dict) or not contenido.get("error"):
            continue
        router = (contenido.get("grounding") or {}).get("router") or {}
        if router.get("ruta") == "cannot_answer":
            return True
    return False


def errores_del_turno(
    mensajes_originales: list[dict[str, Any]],
    mensajes_aumentados: list[dict[str, Any]],
) -> dict[str, int]:
    """Mensajes `tool` de ESTE turno: cuántos hay, cuántos traen `error`,
    cuántos de esos son de infraestructura (excepción contenida como
    `tool_call_failed`) y cuántos trajeron contenido sin error que no es un
    resultado de datos (el catálogo de métricas, los presets)."""
    conteo = {"tools": 0, "con_error": 0, "infra": 0, "con_contenido": 0}
    for mensaje in mensajes_aumentados[len(mensajes_originales) :]:
        if mensaje.get("role") != "tool":
            continue
        conteo["tools"] += 1
        try:
            contenido = json.loads(mensaje.get("content") or "")
        except (ValueError, TypeError):
            continue
        error = contenido.get("error") if isinstance(contenido, dict) else None
        if error:
            conteo["con_error"] += 1
            if str(error).startswith("tool_call_failed"):
                conteo["infra"] += 1
        elif contenido and not _es_resultado_datos(contenido):
            conteo["con_contenido"] += 1
    return conteo


def aviso_post_decide(
    messages: list[dict[str, Any]],
    status: str,
    *,
    got_data: bool = False,
    hueco_declarado: bool = False,
    errores: Optional[dict[str, int]] = None,
    aclaracion: bool = False,
    literal: bool = False,
    repetido: bool = False,
) -> Optional[dict[str, Any]]:
    """Aviso de sistema que acompaña la narración según cómo terminó el decide.

    - "failed": guard anti-alucinación — el usuario activó la tool de datos y
      la infra falló; sin aviso el LLM narra de memoria (visto con el 421).
    - Alguna tool devolvió `error`: reproducir el motivo con sus referencias.
    - Turno SIN datos nuevos (el decide no llamó tools, o llamó y la consulta
      volvió vacía) con una respuesta previa del asistente: follow-up tipo
      "explícame"; narrar sobre lo ya dicho en vez de explicar el hueco.
    - `repetido`: el decide repitió la consulta anterior (mismas cifras); es
      el mismo seguimiento, no datos nuevos.
    Compartido con el eval de routing para reproducir la ruta real del chat
    (ver `aviso_del_turno`).
    """
    if status == "failed":
        return TOOLS_UNAVAILABLE_NOTICE
    if literal:
        return NARRACION_LITERAL_NOTICE
    if hueco_declarado:
        return HUECO_DECLARADO_NOTICE
    if not got_data and aclaracion:
        # Una tool pide precisar al usuario: se transmite, no se elige por él.
        return ACLARACION_NOTICE
    errores = errores or {}
    if not got_data and errores.get("con_error"):
        # P0-4: sin datos y con errores, nunca el aviso de follow-up (que pide
        # citar las cifras anteriores). Todas caídas por excepción = infra.
        if errores.get("infra") == errores.get("tools"):
            return TOOLS_UNAVAILABLE_NOTICE
        return CONSULTA_FALLIDA_NOTICE
    if not got_data and errores.get("con_contenido"):
        # Una tool trajo algo que no es un resultado de datos (el catálogo de
        # métricas ante "¿qué datos tienes?"): se narra sobre eso. El aviso de
        # seguimiento decía que no hubo nada nuevo y, sin cifras previas que
        # explicar, el narrador lo repetía al usuario (producción, 2026-10-15).
        return None
    hay_respuesta_previa = any(
        m.get("role") == "assistant" and m.get("content") for m in messages
    )
    # Sin llamada a tools el aviso va siempre, también en el primer turno:
    # "Inventario de refrescos en Centro" sin consulta terminaba en "No tengo
    # datos de inventario" (producción, 2026-10-20).
    if not got_data and status == "no_calls" and not hay_respuesta_previa:
        return PRIMER_TURNO_SIN_CONSULTA_NOTICE
    if not got_data and (
        status == "no_calls" or (status == "ok" and hay_respuesta_previa)
    ):
        return FOLLOW_UP_SIN_DATOS_NOTICE
    if got_data and repetido:
        # "Explícame" con la consulta repetida: con el aviso de datos nuevos
        # el narrador repetía la tabla y perdía la tienda (ruteo, 2026-10-20).
        return FOLLOW_UP_SIN_DATOS_NOTICE
    if got_data:
        return NARRACION_DATOS_NOTICE
    return None


def modelo_para_narrar(settings: Any, modelo_sesion: str, fc_status: str) -> str:
    """Modelo con el que narrar cuando la conversación es del flujo de datos.

    Un turno del copiloto de datos se REDACTA sobre lo que ya está en el
    contexto (resultados de tools de este turno o del anterior), y ahí un
    razonador estorba: gasta el presupuesto pensando y puede devolver
    contenido vacío (medido 2026-09-03: qwen3.6-27b tarda 15.7-23.8 s y falló
    una de nueve; gemma-4-26b narra en 2.3-3.1 s sin fallar).

    Aplica a todo el flujo con el pill encendido, incluido `no_calls`: un
    "explícame" no llama tools pero narra sobre el turno anterior, y dejarlo
    en el modelo de la sesión costaba 39.6 s en producción (visto 2026-09-03).
    Con el pill apagado (`off`) o sin function-calling (`disabled`) es
    conversación general y se respeta el modelo que eligió el usuario.
    """
    dedicado = getattr(settings, "retail_advisor_narration_model", None)
    if dedicado and fc_status not in ("off", "disabled"):
        return str(dedicado)
    return modelo_sesion


def narracion_directa_del_plugin(
    mensajes_originales: list[dict[str, Any]],
    mensajes_aumentados: list[dict[str, Any]],
    tool_result: Optional[dict[str, Any]],
    settings: Any = None,
) -> Optional[str]:
    """Texto listo del plugin cuando la segunda narración LLM es redundante.

    Solo con `settings.retail_advisor_direct_narration` verdadero. Desde el
    2026-10-15 el chat siempre explica con el LLM y con formato (decisión de
    producto) y `Settings` no declara ese campo, así que el atajo está
    apagado; reactivarlo es declarar el campo en `core/config.py`. Sin
    `settings` se conserva el atajo, para las pruebas del criterio. Si el
    turno ejecutó exactamente UNA tool con resultado de DATOS y ese
    resultado trae `response_text` no vacío, ese texto YA es la respuesta:
    en el contrato genérico `AnalyticsResponse` viene validado por el
    grounding del plugin o es su fallback determinista. Re-narrarlo con el
    LLM solo parafrasea las mismas cifras y cuesta ~15-30 s extra con
    modelos razonadores (card latencia-chat-retail-prediccion). Con varias
    tools de datos en el turno (comparaciones) la narración LLM SÍ aporta
    síntesis y se conserva.

    Si alguna tool del turno declaró que la pregunta no se puede responder
    (`error` con `grounding.router.ruta == "cannot_answer"`, p. ej. un dato
    que no vino en la entrega) la narración LLM también se conserva: hay que
    integrar lo que no se pudo responder con lo que sí.

    Detección SOLO por la forma del contrato (`response_text`, sin `error`,
    mensajes `tool` con forma de datos) — el backend sigue sin conocer el
    dominio (regla anti-deuda #1). Devuelve el texto a emitir o None si la
    narración LLM debe correr.
    """
    if settings is not None and not getattr(
        settings, "retail_advisor_direct_narration", False
    ):
        return None
    if not isinstance(tool_result, dict):
        return None
    texto = str(tool_result.get("response_text") or "").strip()
    if not texto or tool_result.get("error"):
        return None
    previas = [
        _texto_de(m.get("content"))
        for m in mensajes_originales
        if m.get("role") == "assistant" and m.get("content")
    ]
    if previas and previas[-1].strip() == texto:
        # El mismo texto que la respuesta anterior: el usuario pidió otra cosa
        # sobre esas cifras ("explícame") y el decide repitió la consulta.
        # Publicarlo directo repetía la respuesta letra por letra (producción,
        # 2026-10-15); que lo narre el LLM con la pregunta nueva.
        return None
    resultados_datos = 0
    hubo_error = False
    for mensaje in mensajes_aumentados[len(mensajes_originales) :]:
        if mensaje.get("role") != "tool":
            continue
        try:
            contenido = json.loads(mensaje.get("content") or "")
        except (ValueError, TypeError):
            continue
        if _es_resultado_datos(contenido):
            resultados_datos += 1
        elif isinstance(contenido, dict) and contenido.get("error"):
            router = (contenido.get("grounding") or {}).get("router") or {}
            hubo_error = hubo_error or router.get("ruta") == "cannot_answer"
    if hubo_error:
        # El turno mezcla una consulta que NO se pudo responder (dato no
        # entregado, filtro inválido) con otra que sí trajo datos: publicar
        # solo el texto de la segunda oculta la limitación. Visto 2026-09-03
        # con "¿qué está hoy sin existencia?": el plugin declaraba el hueco
        # (P-03) y la respuesta final mostraba únicamente el proxy.
        return None
    return texto if resultados_datos == 1 else None


# Tope del mensaje `tool` que lee el narrador. QA (2026-10-20, P0.1):
# "¿qué tan bien le atinan las alertas?" sin perfil devolvió 1,336 filas y
# 1,336 puntos (427 KB); el proveedor contestó HTTP 530 y el chat echó el
# system prompt. El resultado completo sigue yendo al panel (tool_result);
# el narrador ve el texto, el grounding y una muestra de filas y puntos.
LIMITE_MENSAJE_TOOL_CHARS = 60_000
_FILAS_MINIMAS_NARRADOR = 10


def contenido_para_narrar(result: Any, limite: int = LIMITE_MENSAJE_TOOL_CHARS) -> str:
    """JSON del resultado para el mensaje `tool`, recortado por tamaño: se
    reducen `table_data` y los puntos de `series` a la mitad hasta caber (con
    un piso de filas) y se declara el recorte en `recorte`. Genérico: solo
    la forma del contrato, sin conocer el dominio."""
    texto = json.dumps(result, ensure_ascii=False, default=str)
    if len(texto) <= limite or not isinstance(result, dict):
        return texto
    filas = list(result.get("table_data") or [])
    series = [dict(s) for s in (result.get("series") or []) if isinstance(s, dict)]
    puntos_total = max((len(s.get("points") or []) for s in series), default=0)
    n_filas, n_puntos = len(filas), puntos_total
    recortado = dict(result)
    while True:
        n_filas = max(_FILAS_MINIMAS_NARRADOR, n_filas // 2) if n_filas else 0
        n_puntos = max(_FILAS_MINIMAS_NARRADOR, n_puntos // 2) if n_puntos else 0
        recortado["table_data"] = filas[:n_filas]
        recortado["series"] = [
            {**s, "points": list(s.get("points") or [])[:n_puntos]} for s in series
        ]
        recortado["recorte"] = {
            "table_data": {
                "mostradas": len(recortado["table_data"]),
                "total": len(filas),
            },
            "series": {"mostrados": n_puntos if series else 0, "total": puntos_total},
        }
        texto = json.dumps(recortado, ensure_ascii=False, default=str)
        tope = (
            n_filas <= _FILAS_MINIMAS_NARRADOR and n_puntos <= _FILAS_MINIMAS_NARRADOR
        )
        if len(texto) <= limite or tope:
            if len(texto) > limite:
                logger.warning(
                    "function_calling.tool_message_sigue_grande", chars=len(texto)
                )
            else:
                logger.info(
                    "function_calling.tool_message_recortado",
                    chars=len(texto),
                    filas=len(filas),
                    puntos=puntos_total,
                )
            return texto


def _puntos_de(result: dict[str, Any]) -> int:
    """Total de puntos de las series de un AnalyticsResponse (riqueza del chart)."""
    series = result.get("series") or []
    return sum(len(s.get("points") or []) for s in series if isinstance(s, dict))


def _es_resultado_datos(result: Any) -> bool:
    """¿El resultado tiene forma del contrato genérico AnalyticsResponse?

    Distingue datos consultados (metric_name/series, regla #2 del plugin) de la
    metadata de catálogo (get_presets/get_available_metrics) y de errores, sin
    conocer nombres de tools (regla anti-deuda #1).
    """
    return (
        isinstance(result, dict)
        and not result.get("error")
        and ("metric_name" in result or "series" in result)
    )


def _extract_tool_calls(response: Any) -> list[dict[str, Any]]:
    """Normaliza `choices[0].message.tool_calls` (OpenAI) a dicts simples."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return []
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message", {}) if isinstance(first, dict) else {}
    raw_calls = message.get("tool_calls") or []
    calls: list[dict[str, Any]] = []
    for tc in raw_calls:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function", {}) or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (ValueError, TypeError):
                args = {}
        calls.append(
            {
                "id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "arguments": args or {},
            }
        )
    return calls


# Ids que puede llevar el evento de espera: nombres de tool, métricas y
# dimensiones del catálogo. Lo que no tiene forma de id (texto libre del
# usuario en `metric_or_query`, una dimensión inventada) no sale del backend.
_ID_DE_CATALOGO = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

AlElegirTools = Callable[[list[dict[str, Any]]], Awaitable[None]]


def _id_o_none(valor: Any) -> Optional[str]:
    if isinstance(valor, str) and _ID_DE_CATALOGO.match(valor):
        return valor
    return None


def resumen_de_tools(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lo que la web necesita para elegir el indicador de espera (tema de la
    consulta): tool, métrica y dimensión, solo si tienen forma de id."""
    resumen = []
    for call in calls:
        args = call.get("arguments") or {}
        resumen.append(
            {
                "tool": call.get("name", ""),
                "metrica": _id_o_none(args.get("metrica"))
                or _id_o_none(args.get("metric_or_query")),
                "dimension": _id_o_none(args.get("dimension")),
            }
        )
    return resumen


class FunctionCallingOrchestrator:
    """Orquesta un round de function-calling nativo contra el plugin de dominio."""

    def __init__(self, provider: Optional[DomainToolProvider] = None) -> None:
        self._provider = provider or DomainToolProvider()

    async def augment(
        self,
        saptiva_client: Any,
        messages: list[dict[str, Any]],
        *,
        model: str,
        temperature: float = 0.0,
        # 2048 y no 512: el modelo a veces narra preámbulo antes del tool_call
        # y 512 cortaba el JSON de argumentos a media palabra ('mu',
        # 'disponibi' — visto en vivo 2026-07-13 con Turbo). La llamada es
        # no-streaming y acotada; el costo extra es marginal.
        max_tokens: int = 2048,
        # Modelo dedicado para el decide (card decide-robusto): el
        # function-calling de Turbo emite args vacíos/truncados según el
        # fraseo; Ops los resolvió en vivo. La narración NO usa este modelo.
        decide_model: Optional[str] = None,
        # Ámbito del perfil del usuario (rol, tienda, categorías). Se inyecta
        # en las tools que declaran el parámetro `ambito`, pisando cualquier
        # valor que el LLM hubiera puesto: el modelo no decide el permiso.
        ambito: Optional[dict[str, Any]] = None,
        # Aviso en cuanto el decide elige tools, antes de ejecutarlas: la web
        # cambia el indicador de espera según el tema (resumen_de_tools).
        al_elegir: Optional[AlElegirTools] = None,
    ) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]], str]:
        """Devuelve (mensajes aumentados, último resultado de DATOS crudo, estado).

        El estado le permite al caller distinguir el fallo de infra de la
        decisión legítima de no usar tools (para inyectar
        `TOOLS_UNAVAILABLE_NOTICE` solo en el primero):
        - "ok": se ejecutó al menos un round completo de tools (con o sin
          datos — los mensajes `tool`, incluso de error, son grounding real).
        - "no_calls": el LLM decidió no llamar tools (turno conversacional).
        - "failed": infra rota — sin schemas descubiertos (el plugin no
          respondió el discovery) o excepción antes de completar un round.

        El segundo elemento es el dict `AnalyticsResponse` tal cual lo devolvió
        el plugin (antes de serializarse a texto para el mensaje `tool`), para
        que el caller lo adjunte a metadata/canvas sin tener que re-parsear el
        contenido del mensaje. Solo resultados con forma de contrato
        (`metric_name`/`series`) se promueven — la metadata de catálogo
        (get_presets, etc.) queda en los mensajes `tool` pero NO en el canvas.
        `None` si no hubo tool_calls o ninguna trajo datos.

        Rounds: máximo `MAX_DECIDE_ROUNDS`. El round 2 solo ocurre si el round
        1 no produjo ningún resultado de datos (el LLM exploró el catálogo o
        falló la tool) — así el LLM puede actuar con lo que descubrió en vez de
        devolver una no-respuesta. Cero rounds extra en los paths que ya
        funcionaban en uno.

        Nunca lanza: ante cualquier fallo devuelve `(messages, None, "failed")`,
        o lo aumentado hasta el último round COMPLETO si el fallo fue después
        (fail-safe: nunca se regresa un `assistant(tool_calls)` sin sus
        mensajes `tool` correspondientes).
        """
        estable = list(messages)  # último estado consistente (rounds completos)
        last_result: Optional[dict[str, Any]] = None
        hubo_calls = False
        try:
            schemas = await self._provider.tool_schemas()
            if not schemas:
                # El caller solo invoca augment() con la tool de dominio
                # ACTIVADA en la sesión: discovery vacío = plugin caído (el
                # provider se traga RemoteMcpError y devuelve []), no "no hay
                # tools". Señalarlo para que la narración no invente datos.
                logger.warning("function_calling.no_schemas_discovered")
                return messages, None, "failed"

            modelo_decide = decide_model or model
            from ..perfil_usuario import tools_con_ambito

            acotadas = tools_con_ambito(schemas) if ambito else set()
            nudge_perfil = _nudge_perfil(ambito)
            # Las palabras del usuario las pone el host, no el modelo: el
            # plugin valida contra ellas qué se pidió (gemma no las copiaba).
            pregunta, contexto = textos_del_usuario(messages)
            con_pregunta = tools_que_declaran(schemas, "pregunta_usuario")
            con_contexto = tools_que_declaran(schemas, "contexto_usuario")
            respuestas = textos_del_asistente(messages)
            con_respuestas = tools_que_declaran(schemas, "contexto_asistente")
            reintento_sin_calls = False
            for round_num in range(1, MAX_DECIDE_ROUNDS + 1):
                # Fase "decide": llamada no-streaming ofreciendo las tools, con
                # el nudge anexado SOLO a esta llamada (nunca a la narración).
                nudge = _NUDGE_RETRY_NO_CALL if reintento_sin_calls else _NUDGE_DECIDE
                decide_messages = [*estable, nudge]
                if nudge_perfil is not None:
                    decide_messages.insert(0, nudge_perfil)
                try:
                    decide = await saptiva_client.chat_completion(
                        messages=decide_messages,
                        model=modelo_decide,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                        tools=schemas,
                    )
                except Exception:
                    if modelo_decide == model:
                        raise  # sin fallback posible: fail-safe exterior
                    # El modelo dedicado falló (p.ej. 404 del proveedor):
                    # degradar al modelo de la sesión para ESTE y los
                    # siguientes rounds, no perder las tools por config.
                    logger.warning(
                        "function_calling.decide_model_fallback",
                        decide_model=modelo_decide,
                        fallback=model,
                    )
                    modelo_decide = model
                    decide = await saptiva_client.chat_completion(
                        messages=decide_messages,
                        model=modelo_decide,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                        tools=schemas,
                    )
                calls = _extract_tool_calls(decide)
                if not calls:
                    if round_num == 1:
                        # Qwen puede narrar aun con el contrato explícito de
                        # decide (observado en los fraseos de la demo). Un solo
                        # reintento separa esa omisión transitoria de una
                        # decisión conversacional legítima; nunca se fuerza una
                        # tool concreta ni se parsea el dominio en el backend.
                        reintento_sin_calls = True
                        continue
                    forzada = llamada_forzada_por_correccion(
                        pregunta, respuestas, con_respuestas
                    )
                    if forzada is None:
                        break
                    # El decide se negó dos veces ante una corrección del
                    # usuario: se llama la tool de datos solo con sus palabras
                    # y el plugin resuelve contra su memoria (SIM-24).
                    logger.info(
                        "function_calling.correccion_forzada", tool=forzada["name"]
                    )
                    calls = [forzada]

                if al_elegir is not None:
                    try:
                        await al_elegir(resumen_de_tools(calls))
                    except Exception as exc:  # noqa: BLE001 - nunca rompe el turno
                        logger.warning(
                            "function_calling.aviso_espera_fallido",
                            error_class=type(exc).__name__,
                        )

                augmented = list(estable)
                augmented.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": c["id"],
                                "type": "function",
                                "function": {
                                    "name": c["name"],
                                    "arguments": json.dumps(
                                        c["arguments"], ensure_ascii=False
                                    ),
                                },
                            }
                            for c in calls
                        ],
                    }
                )
                hubo_aclaracion_en_round = False
                for call in calls:
                    argumentos, renombrados = ajustar_argumentos(
                        _parametros_de(schemas, call["name"]),
                        dict(call["arguments"] or {}),
                    )
                    if renombrados:
                        logger.info(
                            "function_calling.argumentos_corregidos",
                            tool=call["name"],
                            cambios=renombrados,
                        )
                    if call["name"] in acotadas:
                        # El ámbito del perfil manda sobre lo que emita el LLM.
                        argumentos["ambito"] = ambito
                    if pregunta and call["name"] in con_pregunta:
                        argumentos["pregunta_usuario"] = pregunta
                    if call["name"] in con_contexto:
                        argumentos["contexto_usuario"] = contexto
                    if call["name"] in con_respuestas:
                        argumentos["contexto_asistente"] = respuestas
                    try:
                        result = await self._provider.call(call["name"], argumentos)
                    except Exception as exc:  # noqa: BLE001 — contener por call
                        # Un call fallido (ej. kwarg inválido inventado por el
                        # LLM) NO aborta el round: se regresa como resultado de
                        # error para que el round extra pueda auto-corregir
                        # (visto en vivo: categoria= en una tool sin ese parámetro).
                        logger.warning(
                            "function_calling.tool_call_error_contained",
                            tool=call["name"],
                            error=str(exc),
                        )
                        result = {"error": f"tool_call_failed: {exc}"}
                    if _pide_aclaracion(result):
                        hubo_aclaracion_en_round = True
                    if _es_resultado_datos(result):
                        # Se promueve al canvas el resultado MÁS RICO del
                        # turno (más puntos), no el último: cuando el LLM
                        # compara con una llamada por entidad, la última
                        # suele ser la más pobre (visto en vivo 2026-07-13:
                        # el chart salía solo con la tienda control).
                        if last_result is None or _puntos_de(result) >= _puntos_de(
                            last_result
                        ):
                            last_result = result
                    augmented.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "name": call["name"],
                            "content": contenido_para_narrar(result),
                        }
                    )
                estable = augmented
                hubo_calls = True

                logger.info(
                    "function_calling.tools_executed",
                    round=round_num,
                    count=len(calls),
                    names=[c["name"] for c in calls],
                    got_data=last_result is not None,
                )
                if last_result is not None:
                    break  # ya hay datos: no se necesita otro round
                if hubo_aclaracion_en_round:
                    # Una tool pide precisar al usuario: el turno termina aquí.
                    # Reintentar "con la más cercana" era el vicio medido el
                    # 2026-10-09 (10 de 14 ambiguas respondidas con cifras).
                    break

            if not hubo_calls:
                return messages, None, "no_calls"
            return estable, last_result, "ok"

        except Exception as exc:  # noqa: BLE001 — fail-safe: nunca romper el chat
            logger.warning(
                "function_calling.failed_fallback",
                error=str(exc),
                kept_rounds=hubo_calls,
            )
            # Con rounds completos previos hay grounding real → "ok"; sin
            # ninguno, la narración iría a ciegas → "failed" (aviso).
            if hubo_calls:
                return estable, last_result, "ok"
            return messages, None, "failed"


def anexo_de_ambito(texto: str, tool_result: Optional[dict[str, Any]]) -> Optional[str]:
    """Lo que hay que anexar al texto narrado: la línea de ámbito del plugin
    (`grounding.ambito_texto`) si el texto aún no la trae. La arma el código
    del plugin desde los filtros ejecutados; el narrador nunca la ve
    (FEAT memoria-de-conversacion, 2026-11-07)."""
    linea = str(
        ((tool_result or {}).get("grounding") or {}).get("ambito_texto") or ""
    ).strip()
    if not linea or linea in (texto or ""):
        return None
    return f"\n\n{linea}"


def respuesta_con_ambito(respuesta: Any, tool_result: Optional[dict[str, Any]]) -> None:
    """Anexa la línea de ámbito al contenido de una respuesta no streaming
    (dict u objeto, como los devuelve el cliente)."""
    choices = getattr(respuesta, "choices", None) or []
    if not choices:
        return
    primero = choices[0]
    mensaje = (
        primero.get("message")
        if isinstance(primero, dict)
        else getattr(primero, "message", None)
    )
    if mensaje is None:
        return
    actual = (
        mensaje.get("content")
        if isinstance(mensaje, dict)
        else getattr(mensaje, "content", None)
    )
    anexo = anexo_de_ambito(str(actual or ""), tool_result)
    if anexo is None:
        return
    nuevo = f"{actual or ''}{anexo}"
    if isinstance(mensaje, dict):
        mensaje["content"] = nuevo
    else:
        mensaje.content = nuevo
