"""
Sanitizador de texto para respuestas del modelo.

Este módulo provee funciones para limpiar rótulos y encabezados no deseados
de las respuestas generadas por los modelos de lenguaje.
"""

import re
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


# Lista de palabras clave de secciones (sin decoración)
SECTION_KEYWORDS_ES = [
    "resumen",
    "respuesta",
    "desarrollo",
    "supuestos",
    "suposiciones",
    "consideraciones",
    "fuentes",
    "referencias",
    "siguientes pasos",
    "próximos pasos",
    "pasos siguientes",
]

SECTION_KEYWORDS_EN = [
    "summary",
    "response",
    "answer",
    "development",
    "assumptions",
    "considerations",
    "sources",
    "references",
    "next steps",
]

ALL_SECTION_KEYWORDS = SECTION_KEYWORDS_ES + SECTION_KEYWORDS_EN


def is_section_heading(line: str) -> bool:
    """
    Determina si una línea es un encabezado de sección.

    Reconoce patrones como:
    - **Resumen:**
    - **Resumen**:
    - Resumen:
    - ## Resumen
    - ## Resumen:
    - **Summary:**
    - Summary:

    Args:
        line: Línea a evaluar

    Returns:
        True si la línea es un encabezado de sección
    """
    # Limpiar la línea de espacios
    stripped = line.strip()
    if not stripped:
        return False

    # Remover markdown headers (##) del inicio
    working_line = re.sub(r"^#{1,6}\s*", "", stripped)

    # Remover negritas de markdown (**texto** o **texto:**)
    # Patrones: **Palabra:** o **Palabra**:
    working_line = re.sub(r"^\*\*(.*?)\*\*:?", r"\1", working_line)
    working_line = re.sub(r"^\*\*(.*?):?\*\*", r"\1", working_line)

    # Remover dos puntos finales
    working_line = working_line.rstrip(":").strip()

    # Convertir a minúsculas para comparación case-insensitive
    normalized = working_line.lower().strip()

    # Verificar si coincide con alguna palabra clave
    return normalized in ALL_SECTION_KEYWORDS


def strip_section_headings(text: str, debug: bool = False) -> str:
    """
    Elimina encabezados de sección del texto manteniendo el contenido.

    Esta función remueve líneas que contengan únicamente rótulos de sección
    como "Resumen:", "**Respuesta:**", "## Fuentes", etc., tanto en español
    como en inglés.

    Args:
        text: Texto a sanitizar
        debug: Si True, agrega comentarios HTML invisibles con información de debug

    Returns:
        Texto sanitizado sin encabezados de sección

    Examples:
        >>> strip_section_headings("**Resumen:**\\nContenido importante\\n\\n**Fuentes:**\\nFuente 1")
        'Contenido importante\\n\\nFuente 1'

        >>> strip_section_headings("## Resumen\\nTexto\\n\\nSiguientes pasos:\\nAcción 1")
        'Texto\\n\\nAcción 1'
    """
    if not text:
        return text

    original_text = text
    removed_headings = []

    # Procesar línea por línea
    lines = text.split("\n")
    cleaned_lines = []

    for i, line in enumerate(lines):
        # Verificar si la línea es un encabezado de sección
        if is_section_heading(line):
            if debug:
                removed_headings.append((i, line.strip()))
            logger.debug(
                "Stripped section heading", line_number=i, heading=line.strip()
            )
            # No agregar esta línea
        else:
            # Agregar líneas que no son encabezados
            cleaned_lines.append(line)

    # Unir líneas limpiadas
    cleaned_text = "\n".join(cleaned_lines)

    # Eliminar múltiples líneas vacías consecutivas (más de 2)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    # Eliminar espacios en blanco al inicio y final
    cleaned_text = cleaned_text.strip()

    # Agregar comentarios de debug si está habilitado
    if debug and removed_headings:
        debug_info = (
            "<!-- DEBUG: Removed headings: "
            + ", ".join(f"L{num}: '{heading}'" for num, heading in removed_headings)
            + " -->\n"
        )
        cleaned_text = debug_info + cleaned_text

    # Log si se hicieron cambios
    if cleaned_text != original_text:
        logger.info(
            "Sanitized text",
            original_length=len(original_text),
            cleaned_length=len(cleaned_text),
            headings_removed=len(removed_headings) if debug else "unknown",
        )

    return cleaned_text


def normalize_markdown_formatting(text: str) -> str:
    """
    Normaliza el formato de markdown para asegurar renderizado correcto.

    BUG-11 FIX: El LLM a veces genera markdown malformado sin espacios.
    Esta función aplica correcciones conservadoras que no rompen markdown válido.

    Correcciones:
    1. Espacio después de puntuación (coma, punto y coma, dos puntos)
    2. Limpieza de asteriscos duplicados (****  → **)
    3. Limpieza de espacios excesivos

    Args:
        text: Texto con markdown potencialmente malformado

    Returns:
        Texto con markdown normalizado

    Examples:
        >>> normalize_markdown_formatting("valor,siguiente")
        'valor, siguiente'

        >>> normalize_markdown_formatting("****duplicado****")
        '**duplicado**'
    """
    if not text:
        return text

    result = text

    # Fix 1: Add space after punctuation if followed by word (not already spaced)
    # Pattern: ,word → , word (but not inside numbers like 1,000)
    # Only apply after comma/semicolon/colon followed by letter
    result = re.sub(r"([,;:])([a-zA-ZáéíóúüñÁÉÍÓÚÜÑ])", r"\1 \2", result)

    # Fix 2: Reduce runs of 4+ asterisks to ** (malformed bold)
    # Pattern: ****text**** → **text**
    result = re.sub(r"\*{4,}", "**", result)

    # Fix 3: Clean up excessive spaces (more than 2 consecutive)
    result = re.sub(r"  +", " ", result)

    return result


def strip_sql_from_response(text: str) -> str:
    """
    Remueve bloques de código SQL de la respuesta del chat.

    BUG-06 FIX: El SQL solo debe mostrarse en el panel canvas, no en el chat.
    Esta función es un filtro de seguridad por si el LLM incluye SQL a pesar
    de las instrucciones en el prompt.

    Args:
        text: Texto que puede contener bloques SQL

    Returns:
        Texto sin bloques SQL

    Examples:
        >>> strip_sql_from_response("Aquí está el resultado:\\n```sql\\nSELECT * FROM x\\n```\\nListo.")
        'Aquí está el resultado:\\n\\nListo.'
    """
    if not text:
        return text

    result = text

    # Remove SQL code blocks (```sql ... ```)
    result = re.sub(r"```sql\s*\n.*?\n```", "", result, flags=re.DOTALL | re.IGNORECASE)

    # Remove generic code blocks that look like SQL (contain SELECT, FROM, WHERE)
    def is_sql_block(match):
        content = match.group(1).upper()
        sql_keywords = ["SELECT", "FROM", "WHERE", "JOIN", "INSERT", "UPDATE", "DELETE"]
        return any(kw in content for kw in sql_keywords)

    # Find code blocks and check if they're SQL
    code_block_pattern = r"```\w*\s*\n(.*?)\n```"
    matches = list(re.finditer(code_block_pattern, result, flags=re.DOTALL))
    for match in reversed(matches):  # Reverse to preserve indices
        if is_sql_block(match):
            result = result[: match.start()] + result[match.end() :]
            logger.info("Stripped SQL code block from response")

    # Remove inline SQL mentions like "La consulta SQL fue: SELECT..."
    result = re.sub(
        r"(?:La consulta|El query|SQL utilizado|Consulta SQL)[^.]*(?:SELECT|INSERT|UPDATE|DELETE)[^.]*\.",
        "",
        result,
        flags=re.IGNORECASE,
    )

    # Remove multi-line SQL blocks introduced by phrases like "La consulta SQL utilizada fue:"
    # Pattern: intro phrase + newlines + SQL statement ending with semicolon
    result = re.sub(
        r"(?:La consulta SQL utilizada fue|La consulta utilizada fue|"
        r"La consulta SQL fue|El query utilizado fue|"
        r"Consulta SQL utilizada|SQL utilizado fue)[:\s]*\n+"
        r"(?:SELECT|INSERT|UPDATE|DELETE)[\s\S]*?;",
        "",
        result,
        flags=re.IGNORECASE,
    )

    # Remove orphaned SQL introduction phrases (if SQL was already removed elsewhere)
    result = re.sub(
        r"(?:La consulta SQL utilizada fue|La consulta utilizada fue|"
        r"La consulta SQL fue|El query utilizado fue|"
        r"Consulta SQL utilizada|SQL utilizado fue)[:\s]*",
        "",
        result,
        flags=re.IGNORECASE,
    )

    # Clean up multiple newlines left by removals
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


def strip_chain_of_thought(text: str) -> str:
    """
    Remove chain-of-thought reasoning patterns that leaked into the response.

    BUG-2026-01-30: The model sometimes exposes internal reasoning in English
    even when the user asks in Spanish. This function strips common patterns.

    Patterns detected:
    - "Okay, let's see..." / "Let me think..."
    - "Wait, but..." / "Hmm, actually..."
    - "The user is asking..." / "The question is about..."
    - "Let me check..." / "I need to..."

    Args:
        text: Text that may contain chain-of-thought reasoning

    Returns:
        Text with reasoning patterns removed

    Examples:
        >>> strip_chain_of_thought("Okay, let's see. The value is 20%.")
        'The value is 20%.'
    """
    if not text:
        return text

    result = text

    # Patterns that indicate chain-of-thought reasoning (case insensitive)
    # Each pattern matches a COMPLETE sentence ending in period
    # Use [^.]{0,80} to limit match scope and prevent over-consumption
    cot_patterns = [
        # Opening reasoning phrases (must be at start of text)
        r"^(?:Okay|Ok|Alright),?\s*(?:let'?s?\s*see|so|now)[.,]?\s*",
        r"^(?:Let me|I'll|I need to)\s+(?:think|check|see|verify|look|analyze)[^.]{0,80}\.\s*",
        r"^(?:Hmm|Hm|Well),?\s*(?:actually|let me|I think)[^.]{0,80}\.\s*",
        r"^(?:Wait|Hold on),?\s*(?:but|let me|actually)[^.]{0,80}\.\s*",
        r"^On second thought[^.]{0,80}\.\s*",
        # Meta-commentary about the user/question (standalone sentences)
        r"(?:^|\.\s+)(?:The user is asking|The question is about|They want to know)[^.]{0,80}\.\s*",
        r"(?:^|\.\s+)(?:The user wants|They're asking|The request is)[^.]{0,80}\.\s*",
        # Internal verification phrases (at sentence start)
        r"(?:^|\.\s+)(?:Let me (?:check|verify|confirm|look at))[^.]{0,80}\.\s*",
        r"(?:^|\.\s+)(?:I need to (?:check|verify|look at) (?:the|this))[^.]{0,80}\.\s*",
        # Wait, but pattern (at sentence start)
        r"(?:^|\.\s+)Wait,?\s+but[^.]{0,80}\.\s*",
        # Self-referential reasoning
        r"(?:^|\.\s+)(?:In (?:my|the) previous response)[^.]{0,80}\.\s*",
        r"(?:^|\.\s+)(?:As I mentioned|As I said)[^.]{0,80}\.\s*",
    ]

    for pattern in cot_patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE | re.MULTILINE)

    # Clean up multiple spaces and newlines
    result = re.sub(r"  +", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = result.strip()

    if result != text:
        logger.info(
            "Stripped chain-of-thought reasoning",
            original_length=len(text),
            cleaned_length=len(result),
        )

    return result


def sanitize_response_content(
    content: Optional[str], enable_sanitization: bool = True, debug: bool = False
) -> Optional[str]:
    """
    Sanitiza el contenido de respuesta del modelo.

    Esta es la función principal que debe ser llamada para procesar
    respuestas antes de guardarlas o mostrarlas al usuario.

    Args:
        content: Contenido a sanitizar (puede ser None)
        enable_sanitization: Si False, retorna el contenido sin modificar
        debug: Si True, habilita modo debug con comentarios HTML

    Returns:
        Contenido sanitizado o None si el input es None

    Examples:
        >>> sanitize_response_content("**Resumen:**\\nHola mundo")
        'Hola mundo'

        >>> sanitize_response_content(None)
        None

        >>> sanitize_response_content("Texto", enable_sanitization=False)
        'Texto'
    """
    if content is None:
        return None

    if not enable_sanitization:
        logger.debug("Sanitization disabled, returning original content")
        return content

    # BUG-2026-01-30 FIX: Strip chain-of-thought reasoning first
    without_cot = strip_chain_of_thought(content)

    # BUG-11 FIX: Normalize markdown formatting
    normalized = normalize_markdown_formatting(without_cot)

    # BUG-06 FIX: Remove SQL from chat responses
    without_sql = strip_sql_from_response(normalized)

    return strip_section_headings(without_sql, debug=debug)
